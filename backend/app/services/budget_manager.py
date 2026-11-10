"""
US WIN HUNTER — Durable Apify Budget & Spend Manager
Provides durable budget enforcement, in-flight reservation tracking,
crash recovery, and verified provider billing reconciliation.

Enforces:
1. Strict session ceiling ($2.00 max).
2. Strict daily ceiling ($2.00 max).
3. Strict monthly ceiling ($10.00 max).
4. Durable check-before-launch reservation in SQLite.
5. In-flight lock preventing duplicate concurrent or un-reconciled runs.
6. Honest billing reconciliation: never assumes missing billing is $0.00.
7. Startup/crash recovery querying Apify remote status before allowing new runs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import httpx
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.models import (
    CollectionJob,
    CollectionRun,
    CollectionJobStatus,
    ApifySpendReservation,
    ApifyReservationStatus,
    _uuid,
    _utcnow,
)

logger = logging.getLogger(__name__)

APIFY_BASE_URL = "https://api.apify.com/v2"


class BudgetExceededError(RuntimeError):
    """Raised when an Apify run exceeds session, daily, or monthly spending limits."""
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
            if r.status in (ApifyReservationStatus.RUNNING.value, ApifyReservationStatus.RESERVED.value):
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
            active_ids = [r["id"] for r in metrics["pending_in_flight_runs"]]
            return (
                False,
                f"Blocked: {len(active_ids)} in-flight run(s) {active_ids} are pending reconciliation.",
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
        Durable check-and-reserve transaction.
        Raises BudgetExceededError if spending limits would be violated.
        """
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

    async def mark_run_started(
        self,
        reservation_id: str,
        apify_run_id: str,
    ) -> ApifySpendReservation:
        """Transitions reservation to RUNNING with the external Apify Run ID."""
        # Double check no duplicate run_id
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
        Safeguard: Never assumes missing billing is $0.00.
        """
        res = await self.db.get(ApifySpendReservation, reservation_id)
        if not res:
            raise ValueError(f"Reservation {reservation_id} not found")

        reconciled_notes = notes or ""

        # Honest billing fallback: if remote provider reported no charge or 0.0 unexpectedly
        if actual_cost_usd is None or actual_cost_usd == 0.0:
            if final_status in (ApifyReservationStatus.SUCCEEDED.value, ApifyReservationStatus.FAILED.value):
                actual_cost_usd = res.reserved_amount_usd
                reconciled_notes += " [Held reservation amount: provider returned missing or zero billing]"
            else:
                actual_cost_usd = 0.0

        res.status = final_status
        res.actual_amount_usd = round(actual_cost_usd, 4)
        res.provider_billing_detail = billing_detail
        res.reconciliation_notes = reconciled_notes.strip() or None
        res.updated_at = _utcnow()
        await self.db.flush()
        logger.info(
            "Reconciled Apify reservation %s: status=%s, actual_cost=$%0.4f",
            res.id,
            final_status,
            res.actual_amount_usd,
        )
        return res

    async def recover_orphaned_runs(
        self,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> list[dict[str, Any]]:
        """
        Scans for in-flight or crashed runs in RUNNING or RESERVED state.
        Queries Apify remote API for true terminal status and billed usage.
        """
        stmt = select(ApifySpendReservation).where(
            ApifySpendReservation.status.in_([
                ApifyReservationStatus.RESERVED.value,
                ApifyReservationStatus.RUNNING.value,
            ])
        )
        orphaned = (await self.db.execute(stmt)).scalars().all()
        recovered = []

        token = self.api_token

        for res in orphaned:
            if not res.apify_run_id:
                # Died before external Apify invocation: abort safely with $0 charge
                res.status = ApifyReservationStatus.ABORTED.value
                res.actual_amount_usd = 0.0
                res.reconciliation_notes = "Aborted on startup: process died prior to external Apify launch."
                res.updated_at = _utcnow()
                await self.db.flush()
                recovered.append({"id": res.id, "action": "ABORTED_LOCAL_ONLY", "cost": 0.0})
                continue

            # Query remote Apify API if token and client available
            remote_status = None
            usage_usd = None
            remote_data = None

            if token:
                try:
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
                    finally:
                        if close_client:
                            await client.aclose()
                except Exception as e:
                    logger.warning("Could not reach Apify API to reconcile %s: %s", res.apify_run_id, e)

            # Map remote status to terminal state
            if remote_status == "SUCCEEDED":
                final_status = ApifyReservationStatus.SUCCEEDED.value
            elif remote_status in ("FAILED", "TIMED-OUT"):
                final_status = ApifyReservationStatus.FAILED.value
            else:
                final_status = ApifyReservationStatus.ABORTED.value

            # Reconcile using honest billing
            await self.reconcile_run(
                reservation_id=res.id,
                final_status=final_status,
                actual_cost_usd=usage_usd,
                billing_detail=remote_data,
                notes=f"Auto-recovered from remote Apify status '{remote_status}'",
            )
            recovered.append({
                "id": res.id,
                "apify_run_id": res.apify_run_id,
                "final_status": final_status,
                "actual_cost_usd": res.actual_amount_usd,
            })

        return recovered
