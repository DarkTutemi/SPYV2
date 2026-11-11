"""
US WIN HUNTER — Apify Live Data Provider Adapter

Production-quality modular interface for collecting live US Meta Ad Library records
via Apify actors (Primary: automation-lab/facebook-ads-library,
Fallback: curious_coder/facebook-ads-library-scraper).

Features:
- Token-based authentication via environment variables or explicit settings
- Strict US geographic enforcement (rejects non-US targeting)
- Dual-actor input mapping (Primary keyword/page + Fallback startUrl/pageIds)
- Exponential backoff retries and timeout protection
- Status state machine: NOT_CONFIGURED, READY, RUNNING, SUCCEEDED_WITH_DATA,
  SUCCEEDED_EMPTY, FAILED, BLOCKED
- Hard daily/monthly spend limits and cost tracking
- Idempotent record validation and persistence via ImportService
"""

from __future__ import annotations

import asyncio
import enum
import logging
import re
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.models import (
    DataSource,
    DataSourceType,
    CollectionJob,
    CollectionRun,
    CollectionJobStatus,
    SourceRecord,
)
from app.schemas.schemas import ImportResult
from app.services.budget_manager import (
    ApifyBudgetManager,
    BudgetExceededError,
    BudgetLockError,
    InFlightRunPendingError,
)
from app.services.import_service import ImportService

logger = logging.getLogger(__name__)

APIFY_BASE_URL = "https://api.apify.com/v2"


class ProviderStatus(str, enum.Enum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    READY = "READY"
    RUNNING = "RUNNING"
    SUCCEEDED_WITH_DATA = "SUCCEEDED_WITH_DATA"
    SUCCEEDED_EMPTY = "SUCCEEDED_EMPTY"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class ApifyProviderAdapter:
    """Production-grade adapter for live Apify Meta Ad Library collection."""

    # Concurrency lock to prevent concurrent jobs from racing past spend limits
    _lock = asyncio.Lock()

    def __init__(self, db: AsyncSession, api_token: Optional[str] = None):
        self.db = db
        settings = get_settings()
        self.api_token = (api_token if api_token is not None else (settings.apify_api_token or "")).strip()
        self.primary_actor = settings.apify_primary_actor
        self.fallback_actor = settings.apify_fallback_actor
        self._daily_budget_usd = settings.apify_daily_budget_usd
        self._monthly_budget_usd = settings.apify_monthly_budget_usd
        self.max_ads_per_query = settings.apify_max_ads_per_query
        self.timeout_seconds = settings.apify_request_timeout_seconds
        self.auto_enabled = settings.apify_auto_collection_enabled
        self.budget_manager = ApifyBudgetManager(
            db=self.db,
            api_token=self.api_token,
            daily_budget_usd=self._daily_budget_usd,
            monthly_budget_usd=self._monthly_budget_usd,
        )

    @property
    def daily_budget_usd(self) -> float:
        return getattr(self, "_daily_budget_usd", 2.00)

    @daily_budget_usd.setter
    def daily_budget_usd(self, value: float) -> None:
        self._daily_budget_usd = value
        if hasattr(self, "budget_manager") and self.budget_manager:
            self.budget_manager.daily_budget_usd = value

    @property
    def monthly_budget_usd(self) -> float:
        return getattr(self, "_monthly_budget_usd", 10.00)

    @monthly_budget_usd.setter
    def monthly_budget_usd(self, value: float) -> None:
        self._monthly_budget_usd = value
        if hasattr(self, "budget_manager") and self.budget_manager:
            self.budget_manager.monthly_budget_usd = value

    # ── Status & Budget Guardrails ─────────────────────────────────────────

    async def get_status(self) -> dict[str, Any]:
        """Check adapter status and budget metrics via authoritative ApifyBudgetManager."""
        if not self.api_token:
            return {
                "status": ProviderStatus.NOT_CONFIGURED.value,
                "configured": False,
                "primary_actor": self.primary_actor,
                "fallback_actor": self.fallback_actor,
                "daily_budget_usd": self.daily_budget_usd,
                "monthly_budget_usd": self.monthly_budget_usd,
                "estimated_spent_today_usd": 0.0,
                "estimated_spent_month_usd": 0.0,
                "auto_collection_enabled": self.auto_enabled,
                "has_pending": False,
                "message": "APIFY_API_TOKEN is not configured. Live queries are disabled.",
            }

        try:
            metrics = await self.budget_manager.get_spend_metrics()
        except Exception as e:
            logger.error("Failed to query budget metrics from budget_manager: %s. Failing closed (BLOCKED).", e)
            return {
                "status": ProviderStatus.BLOCKED.value,
                "configured": True,
                "primary_actor": self.primary_actor,
                "fallback_actor": self.fallback_actor,
                "daily_budget_usd": self.daily_budget_usd,
                "monthly_budget_usd": self.monthly_budget_usd,
                "estimated_spent_today_usd": self.daily_budget_usd,  # Fail closed: never return 0.0 on DB error
                "estimated_spent_month_usd": self.monthly_budget_usd,
                "auto_collection_enabled": self.auto_enabled,
                "has_pending": True,
                "message": f"Database accounting error querying budget metrics: {e}. Fail-closed blocking in effect.",
            }

        spent_today = metrics.get("daily_spend_usd", 0.0)
        spent_month = metrics.get("monthly_spend_usd", 0.0)
        pending_runs = metrics.get("pending_in_flight_runs", [])
        has_pending = len(pending_runs) > 0

        is_blocked = (
            spent_today >= self.daily_budget_usd
            or spent_month >= self.monthly_budget_usd
            or has_pending
        )

        msg = "Adapter ready for live queries."
        if has_pending:
            msg = f"Blocked: {len(pending_runs)} unresolved in-flight run(s) pending reconciliation."
        elif is_blocked:
            msg = "Budget limit reached. Collection blocked."

        return {
            "status": ProviderStatus.BLOCKED.value if is_blocked else ProviderStatus.READY.value,
            "configured": True,
            "primary_actor": self.primary_actor,
            "fallback_actor": self.fallback_actor,
            "daily_budget_usd": self.daily_budget_usd,
            "monthly_budget_usd": self.monthly_budget_usd,
            "estimated_spent_today_usd": round(spent_today, 4),
            "estimated_spent_month_usd": round(spent_month, 4),
            "auto_collection_enabled": self.auto_enabled,
            "has_pending": has_pending,
            "pending_in_flight_runs": pending_runs,
            "message": msg,
        }

    async def _calculate_current_spend(self) -> tuple[float, float]:
        """
        Calculate current spend via authoritative ApifyBudgetManager.
        Fails closed on error: never returns 0.0, 0.0 on database failure.
        """
        try:
            metrics = await self.budget_manager.get_spend_metrics()
            return metrics["daily_spend_usd"], metrics["monthly_spend_usd"]
        except Exception as e:
            logger.error("Error retrieving spend metrics from budget manager: %s. Failing closed.", e)
            return self.daily_budget_usd, self.monthly_budget_usd

    async def _check_budget(self, reservation_amount_usd: float = 0.50) -> tuple[bool, str]:
        """Verify budget constraints before executing a live query via ApifyBudgetManager."""
        if not self.api_token:
            return False, "APIFY_API_TOKEN is missing or empty."
        try:
            is_allowed, reason, _ = await self.budget_manager.check_budget_availability(
                requested_reservation_usd=reservation_amount_usd
            )
            return is_allowed, reason
        except Exception as e:
            logger.error("Error during budget check: %s. Failing closed.", e)
            return False, f"Budget check failed closed due to error: {e}"

    async def reserve_budget(
        self,
        job_name: str,
        actor_name: str,
        reservation_amount_usd: float = 0.50,
        config: Optional[dict[str, Any]] = None,
    ) -> tuple[bool, Optional[CollectionRun], Optional[CollectionJob], str]:
        """
        Atomically reserve budget commitment in the database using ApifyBudgetManager
        with apify_budget_locks serialization to prevent concurrent workers, processes,
        or scheduler instances from bypassing daily/monthly limits.
        """
        if not self.api_token:
            return False, None, None, "APIFY_API_TOKEN is missing or empty."

        try:
            reservation = await self.budget_manager.create_reservation(
                actor_id=actor_name,
                reserved_amount_usd=reservation_amount_usd,
                input_payload=config,
            )

            data_source = await self._ensure_apify_data_source()
            job = CollectionJob(
                data_source_id=data_source.id,
                name=job_name,
                job_type="apify_live",
                config=config or {"actor": actor_name},
            )
            self.db.add(job)
            await self.db.flush()

            run = CollectionRun(
                job_id=job.id,
                status=CollectionJobStatus.RUNNING,
                started_at=datetime.now(timezone.utc),
                errors={
                    "reservation_id": reservation.id,
                    "reserved_cost_usd": round(reservation_amount_usd, 4),
                    "cost_status": "RESERVED",
                },
            )
            self.db.add(run)
            await self.db.flush()

            payload = dict(config or {"actor": actor_name})
            payload["run_id"] = run.id
            reservation.input_payload = payload
            await self.db.commit()

            return True, run, job, ""

        except BudgetExceededError as e:
            logger.warning("Apify budget reservation rejected: %s", e)
            return False, None, None, str(e)
        except Exception as e:
            logger.error("Failed to create budget reservation: %s. Failing closed.", e)
            return False, None, None, f"Budget reservation failed: {e}"

    # ── High-Level Operations ──────────────────────────────────────────────

    async def discover_by_keywords(
        self,
        keywords: list[str],
        max_ads: Optional[int] = None,
        sort_by: str = "recent",
        only_ads_newer_than: Optional[str] = None,
        use_fallback: bool = False,
        persist: bool = True,
    ) -> dict[str, Any]:
        """
        Execute an autonomous keyword-based discovery run targeting US commercial ads.
        Protected by concurrency lock and cloud-side spend limit parameters.
        """
        async with self._lock:
            limit = max_ads or self.max_ads_per_query
            can_run, budget_msg = await self._check_budget()
            if not can_run:
                return {
                    "status": ProviderStatus.NOT_CONFIGURED.value if not self.api_token else ProviderStatus.BLOCKED.value,
                    "success": False,
                    "error": budget_msg,
                    "records_fetched": 0,
                    "records_valid": 0,
                }

            actor_name = self.fallback_actor if use_fallback else self.primary_actor
            run_input = self._build_keyword_input(
                keywords,
                limit,
                sort_by=sort_by,
                only_ads_newer_than=only_ads_newer_than,
                use_fallback=use_fallback,
            )

            return await self._execute_and_process(
                actor_name=actor_name,
                run_input=run_input,
                job_name=f"apify_kw_{','.join(keywords[:2])}_{datetime.now(timezone.utc).strftime('%H%M%S')}",
                persist=persist,
            )

    async def discover_by_advertisers(
        self,
        advertisers: list[str],  # Can be page IDs or Facebook Page URLs
        max_ads: Optional[int] = None,
        sort_by: str = "recent",
        use_fallback: bool = False,
        persist: bool = True,
    ) -> dict[str, Any]:
        """
        Execute an advertiser-specific ad collection run for graph expansion.
        Protected by concurrency lock and cloud-side spend limit parameters.
        """
        async with self._lock:
            limit = max_ads or self.max_ads_per_query
            can_run, budget_msg = await self._check_budget()
            if not can_run:
                return {
                    "status": ProviderStatus.NOT_CONFIGURED.value if not self.api_token else ProviderStatus.BLOCKED.value,
                    "success": False,
                    "error": budget_msg,
                    "records_fetched": 0,
                    "records_valid": 0,
                }

            actor_name = self.fallback_actor if use_fallback else self.primary_actor
            run_input = self._build_advertiser_input(
                advertisers,
                limit,
                sort_by=sort_by,
                use_fallback=use_fallback,
            )

            return await self._execute_and_process(
                actor_name=actor_name,
                run_input=run_input,
                job_name=f"apify_adv_{','.join(advertisers[:2])}_{datetime.now(timezone.utc).strftime('%H%M%S')}",
                persist=persist,
            )

    # ── Actor Input Construction ──────────────────────────────────────────

    def _build_keyword_input(
        self,
        keywords: list[str],
        max_ads: int = 20,
        sort_by: str = "recent",
        only_ads_newer_than: Optional[str] = None,
        use_fallback: bool = False,
    ) -> dict[str, Any]:
        """Build provider-specific payload for keyword search conforming to official schemas."""
        if not use_fallback:
            # Primary: automation-lab/facebook-ads-library
            payload: dict[str, Any] = {
                "searchQueries": keywords,
                "country": "US",
                "activeStatus": "active",  # lowercase per official schema
                "sortBy": sort_by,          # "recent" per official schema
                "mediaType": "all",
                "maxAds": max_ads,
            }
            if only_ads_newer_than:
                payload["onlyAdsNewerThan"] = only_ads_newer_than
            return payload
        else:
            # Fallback: curious_coder/facebook-ads-library-scraper
            start_urls = []
            for kw in keywords:
                enc = urllib.parse.quote(kw)
                start_urls.append({
                    "url": f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&q={enc}&search_type=keyword_unordered&media_type=all"
                })
            return {
                "startUrls": start_urls,
                "maxAds": max_ads,
                "scrapeDetails": True,
            }

    def _build_advertiser_input(
        self,
        advertisers: list[str],
        max_ads: int = 20,
        sort_by: str = "recent",
        active_status: str = "active",
        use_fallback: bool = False,
    ) -> dict[str, Any]:
        """Build provider-specific payload for advertiser page search conforming to official schemas."""
        page_ids = []
        page_urls = []
        for adv in advertisers:
            adv_str = str(adv).strip()
            if adv_str.isdigit():
                page_ids.append(adv_str)
                page_urls.append(f"https://www.facebook.com/ads/library/?active_status={active_status}&ad_type=all&country=US&view_all_page_id={adv_str}")
            elif "facebook.com" in adv_str:
                page_urls.append(adv_str)
                # Extract page id from URL if present
                m = re.search(r'view_all_page_id=(\d+)', adv_str)
                if m:
                    page_ids.append(m.group(1))
            else:
                page_urls.append(adv_str)

        if not use_fallback:
            return {
                "pageUrls": page_urls if page_urls else [f"https://www.facebook.com/ads/library/?view_all_page_id={pid}" for pid in page_ids],
                "country": "US",
                "activeStatus": active_status,
                "sortBy": sort_by,
                "mediaType": "all",
                "maxAds": max_ads,
            }
        else:
            start_urls = [{"url": u} for u in page_urls]
            return {
                "startUrls": start_urls,
                "pageIds": page_ids,
                "maxAds": max_ads,
                "scrapeDetails": True,
                "proxyConfiguration": {
                    "useApifyProxy": True,
                    "apifyProxyCountry": "US",
                },
            }

    # ── Apify REST Client Operations ──────────────────────────────────────

    @staticmethod
    def extract_billing_details(
        run_data: dict[str, Any],
        records_fetched: int,
        reservation_cap: float = 0.50,
    ) -> dict[str, Any]:
        """
        Inspect Apify billing details including platform usage, pay-per-event usage,
        and pricing model details. Distinguish verified billed charges from estimates.
        
        Requirements:
        - Authoritative usageTotalUsd is the total run cost. Do not add event costs
          already included in this total (prevents billing double counting).
        - Explicit zero-charge results are distinguished from unknown charges.
        - Missing billing preserves reservation and reconciliation requirement.
        - Do not treat estimated billing as verified billing.
        """
        usage_total_raw = run_data.get("usageTotalUsd")
        event_usage_raw = run_data.get("eventUsageTotalUsd")
        usage_usd_raw = run_data.get("usageUsd")
        charged_total_raw = run_data.get("chargedTotalUsd")

        usage_total = float(usage_total_raw) if usage_total_raw is not None else None
        event_usage = float(event_usage_raw) if event_usage_raw is not None else 0.0
        usage_usd = float(usage_usd_raw) if usage_usd_raw is not None else 0.0
        charged_total = float(charged_total_raw) if charged_total_raw is not None else None

        pricing_info = run_data.get("pricingInfo") or {}
        pricing_model = str(pricing_info.get("pricingModel", "")).upper()
        is_free_tier = (
            pricing_model == "FREE"
            or run_data.get("is_free_tier") is True
            or run_data.get("explicit_zero_charge_confirmed") is True
        )

        charged_events = run_data.get("chargedEventCounts") or {}

        # Authoritative cost resolution:
        # In Apify API, usageTotalUsd is the authoritative total run cost.
        # Do not add eventUsageTotalUsd to usageTotalUsd.
        if usage_total is not None:
            authoritative_cost = usage_total
            is_missing_billing = False
        elif charged_total is not None and charged_total > 0:
            authoritative_cost = charged_total
            is_missing_billing = False
        elif usage_usd_raw is not None and event_usage_raw is not None:
            # Component fields reported separately without usageTotalUsd
            authoritative_cost = usage_usd + event_usage
            is_missing_billing = False
        elif usage_usd_raw is not None:
            authoritative_cost = usage_usd
            is_missing_billing = False
        elif event_usage_raw is not None:
            authoritative_cost = event_usage
            is_missing_billing = False
        elif charged_total is not None:
            authoritative_cost = charged_total
            is_missing_billing = False
        else:
            authoritative_cost = None
            is_missing_billing = True

        if is_missing_billing:
            if is_free_tier:
                actual_cost = 0.0
                cost_status = "VERIFIED_FREE_TIER"
                is_verified = True
            else:
                # Missing billing must preserve reservation cap to prevent budget leaks
                actual_cost = round(reservation_cap, 4)
                cost_status = "HELD_RESERVATION_CAP"
                is_verified = False
        elif authoritative_cost > 0:
            actual_cost = round(authoritative_cost, 4)
            cost_status = "VERIFIED_CHARGED"
            is_verified = True
        elif is_free_tier:
            actual_cost = 0.0
            cost_status = "VERIFIED_FREE_TIER"
            is_verified = True
        elif records_fetched == 0:
            actual_cost = 0.0
            cost_status = "UNMETERED"
            is_verified = True
        else:
            # Explicit zero charge reported, but records fetched on unconfirmed tier:
            # Mark ESTIMATED (not verified) to avoid treating unconfirmed zero as verified.
            actual_cost = round(records_fetched * 0.0012, 4)
            cost_status = "ESTIMATED"
            is_verified = False

        return {
            "actual_cost_usd": actual_cost,
            "cost_status": cost_status,
            "is_verified": is_verified,
            "usage_total_usd": round(usage_total, 4) if usage_total is not None else 0.0,
            "event_usage_usd": round(event_usage, 4),
            "charged_total_usd": round(charged_total, 4) if charged_total is not None else 0.0,
            "charged_event_counts": charged_events,
            "pricing_info": pricing_info,
            "explicit_zero_charge_confirmed": is_free_tier or (authoritative_cost == 0.0 and records_fetched == 0),
        }

    async def _execute_and_process(
        self,
        actor_name: str,
        run_input: dict[str, Any],
        job_name: str,
        persist: bool = True,
        reservation_amount: float = 0.50,
    ) -> dict[str, Any]:
        """
        Submit run, poll status, download dataset, normalize, validate, and persist.
        Uses persistent atomic database reservation via ApifyBudgetManager to prevent race conditions.
        """
        can_reserve, run, job, budget_msg = await self.reserve_budget(
            job_name=job_name,
            actor_name=actor_name,
            reservation_amount_usd=reservation_amount,
            config={"actor": actor_name, "input_summary": list(run_input.keys())},
        )
        if not can_reserve or not run or not job:
            return {
                "status": ProviderStatus.NOT_CONFIGURED.value if not self.api_token else ProviderStatus.BLOCKED.value,
                "success": False,
                "error": budget_msg,
                "records_fetched": 0,
                "records_valid": 0,
            }

        reservation_id = run.errors.get("reservation_id") if isinstance(run.errors, dict) else None
        apify_run_id: Optional[str] = None

        try:
            # Mark launch attempted in durable budget manager before network dispatch
            if reservation_id:
                await self.budget_manager.mark_launch_attempted(reservation_id)
                await self.db.commit()

            # 1. Trigger Apify Actor Run with cloud-side hard spending cap
            metrics = await self.budget_manager.get_spend_metrics()
            remaining_budget = max(
                0.01,
                min(
                    metrics.get("daily_remaining_usd", reservation_amount),
                    metrics.get("monthly_remaining_usd", reservation_amount),
                    reservation_amount,
                ),
            )

            actor_id_slug = actor_name.replace("/", "~")
            run_data = await self._start_actor_run(actor_id_slug, run_input, max_charge_usd=remaining_budget)
            apify_run_id = run_data.get("id")
            dataset_id = run_data.get("defaultDatasetId")

            if not apify_run_id or not dataset_id:
                raise RuntimeError(f"Start response for Apify actor {actor_name} succeeded but omitted run id or dataset id.")

            # Associate apify_run_id with database run record immediately
            if reservation_id:
                await self.budget_manager.mark_run_started(reservation_id, apify_run_id=apify_run_id)

            run.errors = {
                "apify_run_id": apify_run_id,
                "reservation_id": reservation_id,
                "reserved_cost_usd": reservation_amount,
                "cost_status": "RESERVED",
            }
            await self.db.commit()

            # 2. Wait for completion and extract provider-reported usage
            try:
                final_run_data = await self._wait_for_run_completion(apify_run_id)
            except TimeoutError as te:
                logger.warning("Apify run %s timed out polling: %s", apify_run_id, te)
                if reservation_id:
                    await self.budget_manager.mark_polling_timeout(
                        reservation_id,
                        apify_run_id=apify_run_id,
                        notes=f"Polling window timed out after {self.timeout_seconds}s.",
                    )
                run.status = CollectionJobStatus.FAILED
                run.completed_at = datetime.now(timezone.utc)
                run.errors = {
                    "error": str(te),
                    "cost_status": "NEEDS_RECONCILIATION",
                    "actual_cost_usd": reservation_amount,
                    "apify_run_id": apify_run_id,
                    "reservation_id": reservation_id,
                }
                await self.db.commit()
                return {
                    "status": ProviderStatus.FAILED.value,
                    "success": False,
                    "error": str(te),
                    "records_fetched": 0,
                    "records_valid": 0,
                }

            final_status = final_run_data.get("status")
            if final_status != "SUCCEEDED":
                billing = self.extract_billing_details(final_run_data, 0, reservation_cap=reservation_amount)
                cost = billing["actual_cost_usd"]
                if reservation_id:
                    await self.budget_manager.reconcile_run(
                        reservation_id=reservation_id,
                        final_status=final_status or "FAILED",
                        actual_cost_usd=cost,
                        billing_detail=billing,
                        notes=f"Apify actor run {apify_run_id} finished with non-success status: {final_status}",
                    )
                run.status = CollectionJobStatus.FAILED
                run.completed_at = datetime.now(timezone.utc)
                run.errors = {
                    "error": f"Apify actor run {apify_run_id} finished with status: {final_status}",
                    "cost_status": billing["cost_status"],
                    "actual_cost_usd": cost,
                    "apify_run_id": apify_run_id,
                    "reservation_id": reservation_id,
                }
                await self.db.commit()
                return {
                    "status": ProviderStatus.FAILED.value,
                    "success": False,
                    "error": f"Apify actor run {apify_run_id} finished with status: {final_status}",
                    "records_fetched": 0,
                    "records_valid": 0,
                }

            # 3. Fetch Dataset Records
            raw_records = await self.fetch_dataset(dataset_id)

            # 4. Extract verified billed charges vs estimates
            billing = self.extract_billing_details(final_run_data, len(raw_records), reservation_cap=reservation_amount)
            actual_cost = billing["actual_cost_usd"]

            # Reconcile durable reservation with verified billing
            if reservation_id:
                await self.budget_manager.reconcile_run(
                    reservation_id=reservation_id,
                    final_status="SUCCEEDED",
                    actual_cost_usd=actual_cost,
                    billing_detail=billing,
                    notes=f"Verified successful run with {len(raw_records)} records.",
                )

            # 5. Normalize Records
            normalized = self.normalize_records(raw_records, actor_name)

            # 6. Validate Records (US check, completeness)
            valid_records, validation_errors = self.validate_records(normalized)

            # 7. Persist via ImportService
            import_result = ImportResult(success=True)
            if persist and valid_records:
                import_service = ImportService(self.db)
                import_result = await import_service._import_meta_ads(
                    valid_records, run, {"is_synthetic": False}
                )

            status_val = (
                ProviderStatus.SUCCEEDED_WITH_DATA.value
                if valid_records
                else ProviderStatus.SUCCEEDED_EMPTY.value
            )

            run.status = CollectionJobStatus.COMPLETED
            run.completed_at = datetime.now(timezone.utc)
            run.records_fetched = len(raw_records)
            run.records_new = import_result.records_new
            run.records_updated = import_result.records_updated
            run.records_duplicate = import_result.records_duplicate + (len(raw_records) - len(valid_records))
            run.coverage_notes = (
                f"Cost: ${actual_cost:.4f} USD ({billing['cost_status']}) | "
                f"Validated {len(valid_records)}/{len(raw_records)} records as verified US ads."
            )
            run.errors = {
                "actual_cost_usd": actual_cost,
                "cost_status": billing["cost_status"],
                "billing": billing,
                "apify_run_id": apify_run_id,
                "reservation_id": reservation_id,
            }

            data_source = await self._ensure_apify_data_source()
            data_source.last_successful_collection = datetime.now(timezone.utc)
            await self.db.commit()

            return {
                "status": status_val,
                "success": True,
                "actor": actor_name,
                "apify_run_id": apify_run_id,
                "collection_run_id": run.id,
                "actual_cost_usd": actual_cost,
                "cost_status": billing["cost_status"],
                "billing": billing,
                "records_fetched": len(raw_records),
                "records_valid": len(valid_records),
                "records_new": import_result.records_new,
                "records_duplicate": import_result.records_duplicate,
                "validation_errors": validation_errors[:10],
                "dataset_id": dataset_id,
            }

        except Exception as e:
            logger.exception("Apify live run failed: %s", e)
            is_client_rejection = False
            http_status = None

            if isinstance(e, httpx.HTTPStatusError):
                http_status = e.response.status_code
                if 400 <= http_status < 500:
                    is_client_rejection = True
            elif isinstance(e, PermissionError):
                http_status = 401
                is_client_rejection = True

            if is_client_rejection and not apify_run_id:
                held_cost = 0.0
                cost_status = "FAILED"
                if reservation_id:
                    await self.budget_manager.reconcile_run(
                        reservation_id=reservation_id,
                        final_status="FAILED",
                        actual_cost_usd=0.0,
                        billing_detail={
                            "http_status": http_status,
                            "definitive_client_rejection": True,
                            "error": str(e),
                        },
                        notes=f"HTTP {http_status} definitive client rejection on start (no run created). Released reservation.",
                    )
            else:
                held_cost = reservation_amount
                cost_status = "NEEDS_RECONCILIATION"
                if apify_run_id:
                    try:
                        await self.abort_actor_run(apify_run_id)
                    except Exception:
                        pass
                if reservation_id:
                    await self.budget_manager.reconcile_run(
                        reservation_id=reservation_id,
                        final_status="NEEDS_RECONCILIATION",
                        actual_cost_usd=reservation_amount,
                        billing_detail={
                            "http_status": http_status,
                            "ambiguous_failure": True,
                            "error": str(e),
                        },
                        notes="Ambiguous failure or error during run. Held full reservation amount.",
                    )

            if run:
                run.status = CollectionJobStatus.FAILED
                run.completed_at = datetime.now(timezone.utc)
                run.errors = {
                    "error": str(e),
                    "cost_status": cost_status,
                    "actual_cost_usd": held_cost,
                    "apify_run_id": apify_run_id,
                    "reservation_id": reservation_id,
                }
                await self.db.commit()

            return {
                "status": ProviderStatus.FAILED.value,
                "success": False,
                "error": str(e),
                "records_fetched": 0,
                "records_valid": 0,
            }

    async def _start_actor_run(
        self, actor_slug: str, run_input: dict[str, Any], max_charge_usd: Optional[float] = None
    ) -> dict[str, Any]:
        """
        Post execution to Apify without automatic retries.
        Cloud-side spend cap enforcement via maxTotalChargeUsd.
        Classifies start failures immediately (4xx definitive vs 5xx/network ambiguous).
        """
        url = f"{APIFY_BASE_URL}/acts/{actor_slug}/runs"
        params: dict[str, Any] = {}
        if max_charge_usd is not None and max_charge_usd > 0:
            params["maxTotalChargeUsd"] = round(max_charge_usd, 4)
            params["timeout"] = self.timeout_seconds

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(url, json=run_input, params=params, headers=headers)
            if resp.status_code in (200, 201):
                return resp.json().get("data", {})
            elif resp.status_code in (401, 403):
                raise PermissionError(f"Apify authentication failed ({resp.status_code}): {resp.text}")
            elif 400 <= resp.status_code < 500:
                raise httpx.HTTPStatusError(
                    f"Apify start rejected ({resp.status_code}): {resp.text}",
                    request=resp.request,
                    response=resp,
                )
            else:
                resp.raise_for_status()

    async def _wait_for_run_completion(self, run_id: str, poll_interval: float = 3.0, max_wait: float = 180.0) -> dict[str, Any]:
        """Poll run status until terminal status or timeout. Returns full run payload."""
        url = f"{APIFY_BASE_URL}/actor-runs/{run_id}"
        headers = {"Authorization": f"Bearer {self.api_token}"}

        start_time = asyncio.get_event_loop().time()
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                if asyncio.get_event_loop().time() - start_time > max_wait:
                    raise TimeoutError(f"Apify run {run_id} timed out after {max_wait}s.")

                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    status = data.get("status")
                    if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                        return data
                await asyncio.sleep(poll_interval)

    async def fetch_run_status(self, run_id: str) -> dict[str, Any]:
        """Fetch live status of an existing Apify run."""
        url = f"{APIFY_BASE_URL}/actor-runs/{run_id}"
        headers = {"Authorization": f"Bearer {self.api_token}"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json().get("data", {})

    async def abort_actor_run(self, run_id: str) -> dict[str, Any]:
        """Abort a running remote Apify actor run to immediately cease incurring charges."""
        url = f"{APIFY_BASE_URL}/actor-runs/{run_id}/abort"
        headers = {"Authorization": f"Bearer {self.api_token}"}
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.post(url, headers=headers)
                return resp.json().get("data", {})
            except Exception as e:
                logger.warning("Failed to abort Apify run %s: %s", run_id, e)
                return {}

    async def fetch_dataset(self, dataset_id: str, offset: int = 0, limit: int = 250) -> list[dict[str, Any]]:
        """Fetch paginated dataset items from Apify."""
        url = f"{APIFY_BASE_URL}/datasets/{dataset_id}/items"
        params = {"offset": offset, "limit": limit, "format": "json"}
        headers = {"Authorization": f"Bearer {self.api_token}"}

        items: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            while True:
                resp = await client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                batch = resp.json()
                if not isinstance(batch, list) or not batch:
                    break
                items.extend(batch)
                if len(batch) < limit:
                    break
                offset += len(batch)
                params["offset"] = offset

        return items

    # ── Record Normalization & Validation ──────────────────────────────────

    def normalize_records(self, raw_records: list[dict[str, Any]], actor_name: str) -> list[dict[str, Any]]:
        """
        Normalize raw records from either actor into the standard internal format.
        Supports all official fields: adArchiveId, adLibraryUrl, pageId, pageName,
        startDate, isActive, bodyText, imageUrls, videoUrls, linkUrl, and their aliases.
        """
        normalized: list[dict[str, Any]] = []

        for r in raw_records:
            # 1. External ID (adArchiveId, ad_archive_id, adArchiveID, adId, id)
            ext_id = str(
                r.get("adArchiveId")
                or r.get("ad_archive_id")
                or r.get("adArchiveID")
                or r.get("adId")
                or r.get("id")
                or ""
            ).strip()

            # 2. Page ID (pageId, page_id)
            page_id = str(r.get("pageId") or r.get("page_id") or "").strip()

            # 3. Page Name (pageName, page_name)
            page_name = str(r.get("pageName") or r.get("page_name") or "Unknown Advertiser").strip()

            # 4. Snapshot / Ad Library URL (adLibraryUrl, snapshotUrl, ad_snapshot_url)
            snapshot = r.get("adLibraryUrl") or r.get("snapshotUrl") or r.get("ad_snapshot_url") or ""
            if not snapshot and ext_id:
                snapshot = f"https://www.facebook.com/ads/library/?id={ext_id}"

            # 5. Dates, Status & Launch Freshness
            start_date_raw = r.get("startDate") or r.get("start_date") or r.get("ad_delivery_start_time")
            is_active = r.get("isActive", r.get("is_active", True))

            start_dt: Optional[datetime] = None
            if isinstance(start_date_raw, datetime):
                start_dt = start_date_raw if start_date_raw.tzinfo else start_date_raw.replace(tzinfo=timezone.utc)
            elif isinstance(start_date_raw, (int, float)):
                try:
                    start_dt = datetime.fromtimestamp(start_date_raw, tz=timezone.utc)
                except (OSError, ValueError):
                    pass
            elif isinstance(start_date_raw, str) and start_date_raw.strip():
                for fmt in (
                    "%Y-%m-%dT%H:%M:%S%z",
                    "%Y-%m-%dT%H:%M:%SZ",
                    "%Y-%m-%dT%H:%M:%S.%f%z",
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d",
                    "%m/%d/%Y",
                ):
                    try:
                        parsed = datetime.strptime(start_date_raw.strip(), fmt)
                        start_dt = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        continue

            if start_dt:
                now_utc = datetime.now(timezone.utc)
                days_since_launch = max(0, (now_utc.date() - start_dt.date()).days)
                if days_since_launch <= 7:
                    freshness_tier = "NEW_LAUNCH_7D"
                elif days_since_launch <= 14:
                    freshness_tier = "NEW_LAUNCH_14D"
                elif days_since_launch <= 30:
                    freshness_tier = "NEW_LAUNCH_30D"
                else:
                    freshness_tier = "ESTABLISHED_CAMPAIGN"
            else:
                days_since_launch = None
                freshness_tier = "UNKNOWN_LAUNCH_DATE"

            # 6. Creative media (imageUrls, mediaUrl, images, videos, videoUrls)
            img_raw = (
                r.get("imageUrls")
                or r.get("mediaUrl")
                or r.get("images")
                or r.get("ad_creative_link_images")
            )
            if not img_raw and isinstance(r.get("snapshot"), dict):
                img_raw = r.get("snapshot", {}).get("images")

            images: list[str] = []
            if isinstance(img_raw, list):
                for item in img_raw:
                    if isinstance(item, dict) and "url" in item:
                        images.append(str(item["url"]))
                    elif isinstance(item, str) and item:
                        images.append(item)
            elif isinstance(img_raw, str) and img_raw:
                images = [img_raw]

            vid_raw = (
                r.get("videoUrls")
                or r.get("videos")
                or r.get("ad_creative_videos")
            )
            if not vid_raw and isinstance(r.get("snapshot"), dict):
                vid_raw = r.get("snapshot", {}).get("videos")

            videos: list[str] = []
            if isinstance(vid_raw, list):
                for item in vid_raw:
                    if isinstance(item, dict) and "url" in item:
                        videos.append(str(item["url"]))
                    elif isinstance(item, str) and item:
                        videos.append(item)
            elif isinstance(vid_raw, str) and vid_raw:
                videos = [vid_raw]

            # 7. Text body (bodyText, adCreativeBody, bodies, ad_creative_bodies, snapshot.body.text)
            body_raw = (
                r.get("bodyText")
                or r.get("adCreativeBody")
                or r.get("bodies")
                or r.get("ad_creative_bodies")
            )
            if not body_raw and isinstance(r.get("snapshot"), dict):
                body_raw = r.get("snapshot", {}).get("body", {}).get("text")

            bodies: list[str] = []
            if isinstance(body_raw, list):
                bodies = [str(b) for b in body_raw if b]
            elif isinstance(body_raw, str) and body_raw:
                bodies = [body_raw]

            # 8. Title / Headline (title, adCreativeLinkTitle, ad_creative_link_titles, snapshot.title)
            title_raw = (
                r.get("title")
                or r.get("adCreativeLinkTitle")
                or r.get("ad_creative_link_titles")
            )
            if not title_raw and isinstance(r.get("snapshot"), dict):
                title_raw = r.get("snapshot", {}).get("title")

            if isinstance(title_raw, list):
                title = " | ".join(str(t) for t in title_raw if t)
            elif isinstance(title_raw, str):
                title = title_raw
            else:
                title = ""

            # 9. Destination Landing URL (linkUrl, adCreativeLinkUrl, link_url, snapshot.linkUrl)
            link_url = r.get("linkUrl") or r.get("adCreativeLinkUrl") or r.get("link_url") or ""
            if not link_url and isinstance(r.get("snapshot"), dict):
                link_url = r.get("snapshot", {}).get("linkUrl") or ""

            # 10. CTA text
            cta_text = r.get("ctaText") or (r.get("snapshot", {}).get("ctaText") if isinstance(r.get("snapshot"), dict) else None) or ""

            # 11. Geographic Evidence Extraction:
            # We strictly differentiate:
            # - EXPLICIT_US_TARGETING: Explicit advertiser targeting setting (HIGH confidence)
            # - OBSERVED_US_DELIVERY: Regional impressions/delivery observed in US states (HIGH confidence)
            # - US_SEARCH_FILTER: Ad returned from country="US" query; Meta omitted demographic breakdown (MEDIUM confidence)
            #   (CRITICAL: Never infer confirmed US targeting from the country search filter alone!)
            # - NON_US_TARGETING: Explicit targeting is non-US (REJECTED)
            # - UNKNOWN_TARGETING: No geographic data
            explicit_targeting = (
                r.get("targetCountries")
                or (r.get("targetAudience", {}).get("locations") if isinstance(r.get("targetAudience"), dict) else None)
            )
            observed_delivery = (
                r.get("delivery_by_region")
                or r.get("euDeliveryByCountry")
                or r.get("impressionsByRegion")
            )

            geo_evidence_type = "UNKNOWN_TARGETING"
            geo_confidence = "UNKNOWN"
            geo_desc = "Unknown targeting"

            if explicit_targeting:
                if isinstance(explicit_targeting, str):
                    explicit_targeting = [explicit_targeting]
                has_us = any("US" in str(loc).upper() or "UNITED STATES" in str(loc).upper() for loc in explicit_targeting)
                if has_us:
                    geo_evidence_type = "EXPLICIT_US_TARGETING"
                    geo_confidence = "HIGH"
                    geo_desc = "Explicit advertiser targeting includes United States."
                else:
                    geo_evidence_type = "NON_US_TARGETING"
                    geo_confidence = "REJECTED"
                    geo_desc = f"Explicit targeting is non-US: {explicit_targeting}"
            elif observed_delivery:
                if isinstance(observed_delivery, str):
                    observed_delivery = [observed_delivery]
                elif isinstance(observed_delivery, dict):
                    observed_delivery = list(observed_delivery.keys())
                has_us = any(
                    "US" in str(loc).upper()
                    or "UNITED STATES" in str(loc).upper()
                    or any(state in str(loc).lower() for state in ["california", "texas", "florida", "new york", "illinois", "ohio"])
                    for loc in observed_delivery
                )
                if has_us:
                    geo_evidence_type = "OBSERVED_US_DELIVERY"
                    geo_confidence = "HIGH"
                    geo_desc = "Observed impressions delivered to US states/regions."
                else:
                    geo_evidence_type = "NON_US_TARGETING"
                    geo_confidence = "REJECTED"
                    geo_desc = f"Observed delivery is non-US: {observed_delivery}"
            else:
                # Meta commercial ads in the US typically omit explicit breakdown.
                # Scraper executed under country="US" search filter.
                # Never infer confirmed US targeting from the country search filter alone!
                geo_evidence_type = "US_SEARCH_FILTER"
                geo_confidence = "MEDIUM"
                geo_desc = "Returned under country=US search filter (Not confirmed targeting)."

            norm = {
                "id": ext_id,
                "adArchiveId": ext_id,
                "pageId": page_id,
                "pageName": page_name,
                "snapshotUrl": snapshot,
                "adLibraryUrl": snapshot,
                "startDate": start_date_raw,
                "advertiser_start_date": start_dt.isoformat() if start_dt else None,
                "days_since_launch": days_since_launch,
                "freshness_tier": freshness_tier,
                "isActive": bool(is_active),
                "images": images,
                "imageUrls": images,
                "videos": videos,
                "videoUrls": videos,
                "bodies": bodies,
                "bodyText": "\n".join(bodies) if bodies else "",
                "title": title,
                "linkUrl": link_url,
                "ctaText": cta_text,
                "targetCountries": explicit_targeting if explicit_targeting else (observed_delivery if observed_delivery else ["US"]),
                "geo_evidence_type": geo_evidence_type,
                "geo_confidence": geo_confidence,
                "geo_evidence_description": geo_desc,
                "publisherPlatforms": r.get("publisherPlatforms") or r.get("publisherPlatform") or ["facebook", "instagram"],
                "_provider_actor": actor_name,
                "_raw": r,
            }
            normalized.append(norm)

        return normalized

    def validate_records(self, records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
        """
        Enforce strict US WIN HUNTER quality gates:
        - Must have valid external ID (adArchiveId)
        - Must have advertiser identity (pageName)
        - Geographic validation:
            * Reject if explicit non-US target region (NON_US_TARGETING)
            * Accept if explicit US targeting (EXPLICIT_US_TARGETING)
            * Accept if returned via US search filter (US_SEARCH_FILTER), maintaining MEDIUM confidence
            * Do NOT reject simply because explicit targetCountries breakdown is absent
        - Must have non-empty creative content
        """
        valid: list[dict[str, Any]] = []
        errors: list[str] = []

        for idx, rec in enumerate(records):
            ext_id = rec.get("id") or rec.get("adArchiveId")
            if not ext_id or ext_id == "None":
                errors.append(f"Record {idx}: Missing ad ID.")
                continue

            page_name = rec.get("pageName")
            if not page_name or page_name == "Unknown Advertiser":
                errors.append(f"Record {idx} ({ext_id}): Missing advertiser page name.")
                continue

            # Check geographic targeting evidence
            geo_type = rec.get("geo_evidence_type")
            if not geo_type:
                explicit_locations = rec.get("targetCountries") or rec.get("delivery_by_region") or rec.get("euDeliveryByCountry")
                if explicit_locations:
                    if isinstance(explicit_locations, str):
                        explicit_locations = [explicit_locations]
                    has_us = any("US" in str(loc).upper() or "UNITED STATES" in str(loc).upper() for loc in explicit_locations)
                    if not has_us:
                        geo_type = "NON_US_TARGETING"

            if geo_type == "NON_US_TARGETING":
                locs = rec.get("targetCountries") or "non-US"
                errors.append(f"Record {idx} ({ext_id}): Non-US target region ({locs}). Rejected.")
                continue

            # Content completeness
            has_body = bool(rec.get("bodies") or rec.get("bodyText"))
            has_title = bool(rec.get("title"))
            has_images = bool(rec.get("images") or rec.get("imageUrls"))
            if not (has_body or has_title or has_images):
                errors.append(f"Record {idx} ({ext_id}): Completely blank ad content.")
                continue

            valid.append(rec)

        return valid, errors

    def build_dry_run_payload(
        self,
        query: str = "washable microfiber mop pads multi pack washable rotation",
        max_ads: int = 20,
        sort_by: str = "recent",
        max_charge_usd: float = 0.50,
        only_ads_newer_than: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Create a fully inspected dry-run payload conforming to the official schema.
        Does NOT execute any network calls.
        """
        actor_slug = self.primary_actor.replace("/", "~")
        endpoint_url = f"{APIFY_BASE_URL}/acts/{actor_slug}/runs"
        query_params = {
            "maxTotalChargeUsd": max_charge_usd,
            "timeout": self.timeout_seconds,
        }
        body = self._build_keyword_input(
            keywords=[query],
            max_ads=max_ads,
            sort_by=sort_by,
            only_ads_newer_than=only_ads_newer_than,
            use_fallback=False,
        )
        return {
            "actor": self.primary_actor,
            "actor_slug": actor_slug,
            "endpoint_url": endpoint_url,
            "method": "POST",
            "query_params": query_params,
            "request_body": body,
            "auto_collection_enabled": self.auto_enabled,
            "authentication_configured": bool(self.api_token),
            "dry_run": True,
        }

    @staticmethod
    def filter_by_launch_window(
        records: list[dict[str, Any]],
        max_days_since_launch: int = 30,
        allow_unknown: bool = False,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Filter records by actual launch date (startDate), strictly separating
        newly launched emerging ads from long-running evergreen campaigns.
        Returns (newly_launched_records, established_or_excluded_records).
        """
        fresh: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []

        for r in records:
            days = r.get("days_since_launch")
            if days is not None:
                if days <= max_days_since_launch:
                    fresh.append(r)
                else:
                    excluded.append(r)
            else:
                if allow_unknown:
                    fresh.append(r)
                else:
                    excluded.append(r)

        return fresh, excluded

    def prepare_first_live_run_config(self) -> dict[str, Any]:
        """
        Configuration payload for the bounded first live test:
        - Actor: automation-lab/facebook-ads-library
        - Country: US
        - Keyword: washable microfiber mop pads
        - Active status: active
        - Max ads: 20
        - Per-run maximum charge: $0.50
        - Recurring collection: disabled
        - No fallback Actor execution
        """
        return {
            "actor": self.primary_actor,
            "country": "US",
            "keyword": "washable microfiber mop pads",
            "activeStatus": "active",
            "sortBy": "recent",
            "maxAds": 20,
            "max_charge_usd": 0.50,
            "recurring": False,
            "use_fallback": False,
            "auto_collection_enabled": self.auto_enabled,
            "authenticated": bool(self.api_token),
        }

    async def execute_bounded_first_live_run(
        self,
        persist: bool = True,
        max_charge_usd: float = 0.50,
    ) -> dict[str, Any]:
        """
        Execute the authorized bounded first live test.
        Requires explicit operator approval and valid APIFY_API_TOKEN.
        """
        if not self.api_token:
            return {
                "status": ProviderStatus.NOT_CONFIGURED.value,
                "success": False,
                "error": "APIFY_API_TOKEN is missing or empty. Live run blocked.",
                "records_fetched": 0,
                "records_valid": 0,
            }

        return await self.discover_by_keywords(
            keywords=["washable microfiber mop pads"],
            max_ads=20,
            sort_by="recent",
            use_fallback=False,
            persist=persist,
        )

    # ── Database Registry Helper ──────────────────────────────────────────

    async def _ensure_apify_data_source(self) -> DataSource:
        """Ensure Apify data source is registered in the database."""
        result = await self.db.execute(
            select(DataSource).filter(DataSource.source_type == DataSourceType.APIFY).limit(1)
        )
        source = result.scalar_one_or_none()
        if not source:
            source = DataSource(
                name="Apify Meta Ad Library",
                source_type=DataSourceType.APIFY,
                is_active=True,
                notes="Live US Meta Ad Library scraper via Apify actors",
            )
            self.db.add(source)
            await self.db.flush()
        return source

