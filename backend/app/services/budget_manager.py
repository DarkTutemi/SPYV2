"""
US WIN HUNTER — Durable Apify Budget & Spend Manager
Provides durable budget enforcement, in-flight reservation tracking,
atomic serialization locking, crash recovery, and verified provider billing reconciliation.

Enforces:
1. Strict session ceiling ($2.00 max).
2. Strict daily ceiling ($2.00 max).
3. Strict monthly ceiling ($10.00 max).
4. Atomic database-level check-and-reserve serialization lock in SQLite.
5. In-flight lock preventing duplicate concurrent or un-reconciled runs.
6. Honest billing reconciliation: never assumes missing billing is $0.00.
7. Ambiguous launch crash detection: preserves reservation if crash occurred post-dispatch attempt.
8. Safe recovery: never aborts unresolved remote runs (HTTP 500, RUNNING, unknown status -> NEEDS_RECONCILIATION).
9. Polling timeout protection: holds reservation and blocks future paid runs until read-only reconciliation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import httpx
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.models import (
    CollectionJob,
    CollectionRun,
    CollectionJobStatus,
    ApifySpendReservation,
    ApifyReservationStatus,
    ApifyBudgetLock,
    _uuid,
    _utcnow,
)

logger = logging.getLogger(__name__)

APIFY_BASE_URL = "https://api.apify.com/v2"

# Statuses that represent active or unresolved financial commitment
UNRESOLVED_STATUSES = (
    ApifyReservationStatus.RESERVED.value,
    ApifyReservationStatus.LAUNCH_ATTEMPTED.value,
    ApifyReservationStatus.RUNNING.value,
    ApifyReservationStatus.NEEDS_RECONCILIATION.value,
)

TERMINAL_STATUSES = (
    ApifyReservationStatus.SUCCEEDED.value,
    ApifyReservationStatus.FAILED.value,
    ApifyReservationStatus.ABORTED.value,
)


class BudgetExceededError(RuntimeError):
    """Raised when an Apify run exceeds session, daily, or monthly spending limits."""
    pass


class BudgetLockError(BudgetExceededError):
    """Raised when database serialization lock cannot be acquired, failing closed to refuse reservation."""
    pass


class InFlightRunPendingError(RuntimeError):
    """Raised when an un-reconciled in-flight run is still active."""
    pass


class ApifyBudgetManager:
    """Production-grade durable spending manager for Apify provider calls."""

    def __init__(
        self,
        db: AsyncSession,
        api_token: Optional[str] = None,
        session_ceiling_usd: Optional[float] = None,
        daily_budget_usd: Optional[float] = None,
        monthly_budget_usd: Optional[float] = None,
    ):
        self.db = db
        settings = get_settings()
        self.api_token = (
            api_token if api_token is not None else (settings.apify_api_token or "")
        ).strip()

        # Spend caps
        self.session_ceiling_usd = (
            session_ceiling_usd
            if session_ceiling_usd is not None
            else getattr(settings, "apify_session_ceiling_usd", 2.00)
        )
        self.daily_budget_usd = (
            daily_budget_usd
            if daily_budget_usd is not None
            else settings.apify_daily_budget_usd
        )
        self.monthly_budget_usd = (
            monthly_budget_usd
            if monthly_budget_usd is not None
            else settings.apify_monthly_budget_usd
        )

    async def _acquire_db_lock(self, session_id: str = "default_session") -> None:
        """
        Acquires SQLite write serialization lock via exclusive UPDATE on the lock table.
        Prevents race conditions between concurrent worker processes attempting budget check-and-reserve.
        FAILS CLOSED: If lock table is missing or locking fails, raises BudgetLockError to refuse reservation.
        """
        try:
            # Check table existence (SQLite check)
            tbl_check = await self.db.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='apify_budget_locks'")
            )
            if not tbl_check.scalar_one_or_none():
                raise BudgetLockError(
                    "Database budget lock table 'apify_budget_locks' does not exist. Failing closed to refuse reservation."
                )

            # Upsert/Update lock row 1 to force immediate write lock acquisition
            await self.db.execute(
                text(
                    "INSERT INTO apify_budget_locks (lock_id, locked_by, locked_at) "
                    "VALUES (1, :who, :now) "
                    "ON CONFLICT(lock_id) DO UPDATE SET locked_by = :who, locked_at = :now"
                ),
                {"who": session_id, "now": _utcnow()},
            )
            await self.db.flush()
        except BudgetLockError:
            raise
        except Exception as e:
            logger.error("Failed to acquire database budget lock: %s. Refusing reservation (fail-closed).", e)
            raise BudgetLockError(f"Failed to acquire database budget lock: {e}") from e

    async def get_spend_metrics(self, session_id: str = "default_session") -> dict[str, Any]:
        """
        Calculates authoritative spend across durable reservations and historical collection runs.
        Safeguard: Never assumes missing billing is $0.00.
        """
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # 1. Query reservations
        res_stmt = select(ApifySpendReservation)
        reservations_all = (await self.db.execute(res_stmt)).scalars().all()

        session_spend = 0.0
        daily_spend = 0.0
        monthly_spend = 0.0
        pending_runs = []

        seen_apify_ids = set()

        for r in reservations_all:
            if r.apify_run_id:
                seen_apify_ids.add(r.apify_run_id)

            # Determine cost for this reservation
            if r.status in UNRESOLVED_STATUSES:
                cost = r.reserved_amount_usd
                pending_runs.append({
                    "id": r.id,
                    "apify_run_id": r.apify_run_id,
                    "actor_id": r.actor_id,
                    "status": r.status,
                    "reserved_usd": r.reserved_amount_usd,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                })
            elif r.actual_amount_usd is not None:
                cost = r.actual_amount_usd
            else:
                # Conservative fallback: if missing actual billing, use reserved amount
                cost = r.reserved_amount_usd

            # Session attribution
            if r.session_id == session_id:
                session_spend += cost

            # Time-based attribution
            created_tz = (
                r.created_at if r.created_at and r.created_at.tzinfo
                else (r.created_at.replace(tzinfo=timezone.utc) if r.created_at else now)
            )
            if created_tz >= start_of_day:
                daily_spend += cost
            if created_tz >= start_of_month:
                monthly_spend += cost

        # 2. Reconcile with historical collection_runs not in apify_spend_reservations
        runs_stmt = select(CollectionRun).join(CollectionJob).filter(
            CollectionJob.job_type.in_(["apify_live", "catalog_scrape", "product_scrape", "trends_scrape", "social_scrape"])
        )
        historical_runs = (await self.db.execute(runs_stmt)).scalars().all()

        for cr in historical_runs:
            if cr.id in seen_apify_ids:
                continue

            # Calculate cost
            run_cost = 0.0
            if cr.errors and isinstance(cr.errors, dict) and "actual_cost_usd" in cr.errors:
                run_cost = float(cr.errors["actual_cost_usd"])
            elif cr.records_fetched and cr.records_fetched > 0:
                run_cost = round(cr.records_fetched * 0.0012, 4)
            else:
                # Minimum floor for executed run if unknown
                run_cost = 0.01

            run_started_tz = (
                cr.started_at if cr.started_at and cr.started_at.tzinfo
                else (cr.started_at.replace(tzinfo=timezone.utc) if cr.started_at else None)
            )

            if run_started_tz:
                if run_started_tz >= start_of_day:
                    daily_spend += run_cost
                if run_started_tz >= start_of_month:
                    monthly_spend += run_cost

        return {
            "session_id": session_id,
            "session_spend_usd": round(session_spend, 4),
            "session_ceiling_usd": self.session_ceiling_usd,
            "session_remaining_usd": round(max(0.0, self.session_ceiling_usd - session_spend), 4),
            "daily_spend_usd": round(daily_spend, 4),
            "daily_budget_usd": self.daily_budget_usd,
            "daily_remaining_usd": round(max(0.0, self.daily_budget_usd - daily_spend), 4),
            "monthly_spend_usd": round(monthly_spend, 4),
            "monthly_budget_usd": self.monthly_budget_usd,
            "monthly_remaining_usd": round(max(0.0, self.monthly_budget_usd - monthly_spend), 4),
            "pending_in_flight_runs": pending_runs,
        }

    async def check_budget_availability(
        self,
        requested_reservation_usd: float,
        session_id: str = "default_session",
    ) -> tuple[bool, str, dict[str, Any]]:
        """
        Strict preflight budget gate.
        Returns (is_allowed, reason, metrics).
        """
        metrics = await self.get_spend_metrics(session_id=session_id)

        # Block if un-reconciled in-flight runs exist
        if len(metrics["pending_in_flight_runs"]) > 0:
            active_ids = [f"{r['id']}:{r['status']}" for r in metrics["pending_in_flight_runs"]]
            return (
                False,
                f"Blocked: {len(active_ids)} in-flight or unresolved run(s) {active_ids} are pending reconciliation.",
                metrics,
            )

        # Block if session ceiling would be exceeded
        if metrics["session_spend_usd"] + requested_reservation_usd > self.session_ceiling_usd:
            return (
                False,
                (
                    f"Session budget ceiling of ${self.session_ceiling_usd:.2f} exceeded. "
                    f"Current: ${metrics['session_spend_usd']:.4f}, Requested: ${requested_reservation_usd:.4f}."
                ),
                metrics,
            )

        # Block if daily budget would be exceeded
        if metrics["daily_spend_usd"] + requested_reservation_usd > self.daily_budget_usd:
            return (
                False,
                (
                    f"Daily budget of ${self.daily_budget_usd:.2f} exceeded. "
                    f"Current: ${metrics['daily_spend_usd']:.4f}, Requested: ${requested_reservation_usd:.4f}."
                ),
                metrics,
            )

        # Block if monthly budget would be exceeded
        if metrics["monthly_spend_usd"] + requested_reservation_usd > self.monthly_budget_usd:
            return (
                False,
                (
                    f"Monthly budget of ${self.monthly_budget_usd:.2f} exceeded. "
                    f"Current: ${metrics['monthly_spend_usd']:.4f}, Requested: ${requested_reservation_usd:.4f}."
                ),
                metrics,
            )

        return True, "Budget check passed.", metrics

    async def create_reservation(
        self,
        actor_id: str,
        reserved_amount_usd: float,
        input_payload: Optional[dict] = None,
        session_id: str = "default_session",
    ) -> ApifySpendReservation:
        """
        Durable atomic check-and-reserve transaction.
        Acquires DB lock before evaluation to prevent concurrency races.
        Raises BudgetExceededError if spending limits would be violated.
        """
        # 1. Acquire DB serialization lock
        await self._acquire_db_lock(session_id=session_id)

        # 2. Check budget availability inside lock
        is_allowed, reason, metrics = await self.check_budget_availability(
            requested_reservation_usd=reserved_amount_usd,
            session_id=session_id,
        )
        if not is_allowed:
            logger.error("Apify budget reservation rejected: %s", reason)
            raise BudgetExceededError(reason)

        reservation = ApifySpendReservation(
            id=_uuid(),
            actor_id=actor_id,
            session_id=session_id,
            reserved_amount_usd=reserved_amount_usd,
            status=ApifyReservationStatus.RESERVED.value,
            input_payload=input_payload,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        self.db.add(reservation)
        await self.db.flush()
        logger.info(
            "Created Apify spend reservation %s for %s ($%0.4f)",
            reservation.id,
            actor_id,
            reserved_amount_usd,
        )
        return reservation

    async def mark_launch_attempted(
        self,
        reservation_id: str,
    ) -> ApifySpendReservation:
        """
        Durable pre-dispatch state: marks that HTTP invocation is about to be sent.
        Protects against crash-after-start ambiguity (A3).
        """
        res = await self.db.get(ApifySpendReservation, reservation_id)
        if not res:
            raise ValueError(f"Reservation {reservation_id} not found")

        res.status = ApifyReservationStatus.LAUNCH_ATTEMPTED.value
        res.launch_attempted_at = _utcnow()
        res.updated_at = _utcnow()
        await self.db.flush()
        return res

    async def mark_run_started(
        self,
        reservation_id: str,
        apify_run_id: str,
    ) -> ApifySpendReservation:
        """Transitions reservation to RUNNING with the external Apify Run ID."""
        dup_check = await self.db.execute(
            select(ApifySpendReservation).where(
                ApifySpendReservation.apify_run_id == apify_run_id,
                ApifySpendReservation.id != reservation_id,
            )
        )
        if dup_check.scalar_one_or_none():
            raise RuntimeError(f"Apify run ID {apify_run_id} is already tracked by another reservation!")

        res = await self.db.get(ApifySpendReservation, reservation_id)
        if not res:
            raise ValueError(f"Reservation {reservation_id} not found")

        res.status = ApifyReservationStatus.RUNNING.value
        res.apify_run_id = apify_run_id
        res.updated_at = _utcnow()
        await self.db.flush()
        return res

    async def mark_polling_timeout(
        self,
        reservation_id: str,
        apify_run_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> ApifySpendReservation:
        """
        Handles local polling window expiration safely (A4).
        Does NOT convert to FAILED, does NOT release budget.
        Transitions to NEEDS_RECONCILIATION, holding full reservation amount.
        """
        res = await self.db.get(ApifySpendReservation, reservation_id)
        if not res:
            raise ValueError(f"Reservation {reservation_id} not found")

        if apify_run_id:
            res.apify_run_id = apify_run_id
        res.status = ApifyReservationStatus.NEEDS_RECONCILIATION.value
        res.reconciliation_notes = (
            (notes or "Polling window expired while remote Actor still running")
            + " [Held full reservation amount; requires subsequent read-only reconciliation]"
        )
        res.updated_at = _utcnow()
        await self.db.flush()
        logger.warning(
            "Reservation %s timed out polling. Set to NEEDS_RECONCILIATION holding $%0.4f",
            res.id,
            res.reserved_amount_usd,
        )
        return res

    async def reconcile_run(
        self,
        reservation_id: str,
        final_status: str,
        actual_cost_usd: Optional[float] = None,
        billing_detail: Optional[dict] = None,
        notes: Optional[str] = None,
    ) -> ApifySpendReservation:
        """
        Finalizes an Apify run with verified billing.
        Safeguards:
        - Never assumes missing billing is $0.00.
        - Accepts $0.00 ONLY if explicit confirmed zero charge / free tier is present.
        - Non-terminal statuses (e.g. NEEDS_RECONCILIATION) preserve full reservation amount.
        """
        res = await self.db.get(ApifySpendReservation, reservation_id)
        if not res:
            raise ValueError(f"Reservation {reservation_id} not found")

        reconciled_notes = notes or ""
        detail = billing_detail or {}

        # Check for authoritative explicit zero charge confirmation (A6.9)
        explicit_zero_confirmed = (
            detail.get("explicit_zero_charge_confirmed") is True
            or detail.get("is_free_tier") is True
            or (detail.get("pricingInfo", {}).get("pricingModel") == "FREE")
        )

        if final_status in TERMINAL_STATUSES:
            if actual_cost_usd is not None and actual_cost_usd > 0:
                cost = actual_cost_usd
            elif actual_cost_usd == 0.0 and explicit_zero_confirmed:
                cost = 0.0
                reconciled_notes += " [Explicit verified zero-charge confirmed by provider]"
            elif final_status == ApifyReservationStatus.FAILED.value and not res.apify_run_id and (
                not res.launch_attempted_at
                or detail.get("definitive_client_rejection") is True
                or (isinstance(detail.get("http_status"), int) and 400 <= detail.get("http_status") < 500)
            ):
                # Pre-launch failure or definitive client-side rejection (e.g. 400, 401, 403, 404, 422 where no run was created)
                cost = 0.0
                reconciled_notes += " [Definitive client-side rejection: provider confirmed no run created]"
            else:
                # Conservative fallback: hold reservation amount so zero dollars leak
                cost = res.reserved_amount_usd
                reconciled_notes += " [Held reservation amount: provider returned missing or unconfirmed zero billing]"
        else:
            # Non-terminal or ambiguous state (e.g. NEEDS_RECONCILIATION)
            cost = res.reserved_amount_usd
            reconciled_notes += " [Held full reservation: run is non-terminal / requires reconciliation]"

        res.status = final_status
        res.actual_amount_usd = round(cost, 4)
        res.provider_billing_detail = detail
        res.reconciliation_notes = reconciled_notes.strip() or None
        res.updated_at = _utcnow()
        await self.db.flush()
        logger.info(
            "Reconciled Apify reservation %s: status=%s, cost=$%0.4f (%s)",
            res.id,
            final_status,
            res.actual_amount_usd,
            res.reconciliation_notes,
        )
        return res

    async def recover_orphaned_runs(
        self,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> list[dict[str, Any]]:
        """
        Scans for in-flight or crashed runs in unresolved state (A2, A3).
        Safeguards:
        - If crash happened after launch attempt without run ID -> NEEDS_RECONCILIATION (held budget).
        - If remote status is RUNNING, READY, unknown, HTTP 500, or error -> NEEDS_RECONCILIATION (held budget).
        - Only authoritatively terminal Apify runs (SUCCEEDED, FAILED, ABORTED, TIMED-OUT) are finalized.
        """
        stmt = select(ApifySpendReservation).where(
            ApifySpendReservation.status.in_(UNRESOLVED_STATUSES)
        )
        orphaned = (await self.db.execute(stmt)).scalars().all()
        recovered = []

        token = self.api_token

        for res in orphaned:
            if not res.apify_run_id:
                if res.status == ApifyReservationStatus.LAUNCH_ATTEMPTED.value:
                    # Ambiguous crash post-dispatch (A3):
                    # Request may have reached Apify before local crash. DO NOT abort or zero out!
                    res.status = ApifyReservationStatus.NEEDS_RECONCILIATION.value
                    res.reconciliation_notes = (
                        "Ambiguous crash post-dispatch: launch was attempted but apify_run_id was not persisted. "
                        "Held full reservation amount pending manual or actor run reconciliation."
                    )
                    res.updated_at = _utcnow()
                    await self.db.flush()
                    recovered.append({
                        "id": res.id,
                        "action": "HELD_AMBIGUOUS_START",
                        "status": res.status,
                        "reserved_cost": res.reserved_amount_usd,
                    })
                    continue
                else:
                    # Clean pre-launch failure: reservation was created but launch was never attempted
                    res.status = ApifyReservationStatus.ABORTED.value
                    res.actual_amount_usd = 0.0
                    res.reconciliation_notes = "Aborted on startup: reservation was never dispatched."
                    res.updated_at = _utcnow()
                    await self.db.flush()
                    recovered.append({
                        "id": res.id,
                        "action": "ABORTED_PRE_DISPATCH",
                        "status": res.status,
                        "cost": 0.0,
                    })
                    continue

            # Reservation has apify_run_id: query remote Apify API
            remote_status = None
            usage_usd = None
            remote_data = None
            http_error = False

            if token:
                close_client = False
                client = http_client
                if client is None:
                    client = httpx.AsyncClient(timeout=15.0)
                    close_client = True

                try:
                    resp = await client.get(
                        f"{APIFY_BASE_URL}/actor-runs/{res.apify_run_id}",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if resp.status_code == 200:
                        data = resp.json().get("data", {})
                        remote_status = data.get("status")
                        usage_usd = data.get("usageTotalUsd")
                        remote_data = data
                    else:
                        http_error = True
                        logger.warning(
                            "Apify API returned HTTP %s while recovering run %s",
                            resp.status_code,
                            res.apify_run_id,
                        )
                except Exception as e:
                    http_error = True
                    logger.warning("Could not reach Apify API to reconcile %s: %s", res.apify_run_id, e)
                finally:
                    if close_client:
                        await client.aclose()

            # Handle recovery outcome strictly (A2):
            if http_error or remote_status is None:
                # HTTP error / network timeout: DO NOT abort or zero out! Keep reservation active!
                res.status = ApifyReservationStatus.NEEDS_RECONCILIATION.value
                res.reconciliation_notes = f"Recovery attempt failed (HTTP error/network timeout). Preserved full reservation ${res.reserved_amount_usd:.4f}."
                res.updated_at = _utcnow()
                await self.db.flush()
                recovered.append({
                    "id": res.id,
                    "apify_run_id": res.apify_run_id,
                    "action": "HELD_API_ERROR",
                    "status": res.status,
                    "cost": res.reserved_amount_usd,
                })
                continue

            if remote_status in ("RUNNING", "READY"):
                # Remote run is still active: DO NOT abort or zero out!
                res.status = ApifyReservationStatus.RUNNING.value
                res.reconciliation_notes = f"Remote Actor is still active on Apify (status={remote_status}). Preserved full reservation ${res.reserved_amount_usd:.4f}."
                res.updated_at = _utcnow()
                await self.db.flush()
                recovered.append({
                    "id": res.id,
                    "apify_run_id": res.apify_run_id,
                    "action": "STILL_ACTIVE",
                    "status": res.status,
                    "cost": res.reserved_amount_usd,
                })
                continue

            # Terminal states:
            if remote_status == "SUCCEEDED":
                final_status = ApifyReservationStatus.SUCCEEDED.value
            elif remote_status in ("FAILED", "TIMED-OUT"):
                final_status = ApifyReservationStatus.FAILED.value
            elif remote_status == "ABORTED":
                final_status = ApifyReservationStatus.ABORTED.value
            else:
                # Unknown remote status string: do not assume terminal, keep in NEEDS_RECONCILIATION
                res.status = ApifyReservationStatus.NEEDS_RECONCILIATION.value
                res.reconciliation_notes = f"Unknown remote Apify status '{remote_status}'. Preserved reservation ${res.reserved_amount_usd:.4f}."
                res.updated_at = _utcnow()
                await self.db.flush()
                recovered.append({
                    "id": res.id,
                    "apify_run_id": res.apify_run_id,
                    "action": "HELD_UNKNOWN_STATUS",
                    "status": res.status,
                    "cost": res.reserved_amount_usd,
                })
                continue

            # Authoritatively terminal: reconcile with honest billing
            await self.reconcile_run(
                reservation_id=res.id,
                final_status=final_status,
                actual_cost_usd=usage_usd,
                billing_detail=remote_data,
                notes=f"Auto-recovered from authoritative remote Apify status '{remote_status}'",
            )
            recovered.append({
                "id": res.id,
                "apify_run_id": res.apify_run_id,
                "action": "FINALIZED_TERMINAL",
                "final_status": final_status,
                "actual_cost_usd": res.actual_amount_usd,
            })

        return recovered
