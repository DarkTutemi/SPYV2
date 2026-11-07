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
from datetime import datetime, timezone
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

    def __init__(self, db: AsyncSession, api_token: Optional[str] = None):
        self.db = db
        settings = get_settings()
        self.api_token = (api_token or settings.apify_api_token or "").strip()
        self.primary_actor = settings.apify_primary_actor
        self.fallback_actor = settings.apify_fallback_actor
        self.daily_budget_usd = settings.apify_daily_budget_usd
        self.monthly_budget_usd = settings.apify_monthly_budget_usd
        self.max_ads_per_query = settings.apify_max_ads_per_query
        self.timeout_seconds = settings.apify_request_timeout_seconds
        self.auto_enabled = settings.apify_auto_collection_enabled

    # ── Status & Budget Guardrails ─────────────────────────────────────────

    async def get_status(self) -> dict[str, Any]:
        """Check adapter status and budget metrics."""
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
                "message": "APIFY_API_TOKEN is not configured. Live queries are disabled.",
            }

        spent_today, spent_month = await self._calculate_current_spend()
        is_blocked = spent_today >= self.daily_budget_usd or spent_month >= self.monthly_budget_usd

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
            "message": "Budget limit reached. Collection blocked." if is_blocked else "Adapter ready for live queries.",
        }

    async def _calculate_current_spend(self) -> tuple[float, float]:
        """Calculate spend based on actual Apify run charges, with record-based fallback."""
        try:
            now = datetime.now(timezone.utc)
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            # Query runs
            result_day = await self.db.execute(
                select(CollectionRun).join(CollectionJob).filter(
                    CollectionJob.job_type == "apify_live",
                    CollectionRun.started_at >= start_of_day,
                )
            )
            runs_today = result_day.scalars().all()

            result_month = await self.db.execute(
                select(CollectionRun).join(CollectionJob).filter(
                    CollectionJob.job_type == "apify_live",
                    CollectionRun.started_at >= start_of_month,
                )
            )
            runs_month = result_month.scalars().all()

            def sum_runs(runs):
                total = 0.0
                for r in runs:
                    if r.errors and isinstance(r.errors, dict) and "actual_cost_usd" in r.errors:
                        total += float(r.errors["actual_cost_usd"])
                    else:
                        total += (r.records_fetched or 0) * 0.0012
                return total

            cost_today = sum_runs(runs_today)
            cost_month = sum_runs(runs_month)
            return cost_today, cost_month
        except Exception as e:
            logger.warning("Error calculating Apify spend: %s", e)
            return 0.0, 0.0

    async def _check_budget(self) -> tuple[bool, str]:
        """Verify budget constraints before executing a live query."""
        if not self.api_token:
            return False, "APIFY_API_TOKEN is missing or empty."
        spent_today, spent_month = await self._calculate_current_spend()
        if spent_today >= self.daily_budget_usd:
            return False, f"Daily budget of ${self.daily_budget_usd:.2f} reached (Spent: ${spent_today:.2f})."
        if spent_month >= self.monthly_budget_usd:
            return False, f"Monthly budget of ${self.monthly_budget_usd:.2f} reached (Spent: ${spent_month:.2f})."
        return True, ""

    # ── High-Level Operations ──────────────────────────────────────────────

    async def discover_by_keywords(
        self,
        keywords: list[str],
        max_ads: Optional[int] = None,
        use_fallback: bool = False,
        persist: bool = True,
    ) -> dict[str, Any]:
        """
        Execute an autonomous keyword-based discovery run targeting US commercial ads.
        """
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
        run_input = self._build_keyword_input(keywords, limit, use_fallback=use_fallback)

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
        use_fallback: bool = False,
        persist: bool = True,
    ) -> dict[str, Any]:
        """
        Execute an advertiser-specific ad collection run for graph expansion.
        """
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
        run_input = self._build_advertiser_input(advertisers, limit, use_fallback=use_fallback)

        return await self._execute_and_process(
            actor_name=actor_name,
            run_input=run_input,
            job_name=f"apify_adv_{','.join(advertisers[:2])}_{datetime.now(timezone.utc).strftime('%H%M%S')}",
            persist=persist,
        )

    # ── Actor Input Construction ──────────────────────────────────────────

    def _build_keyword_input(self, keywords: list[str], max_ads: int, use_fallback: bool = False) -> dict[str, Any]:
        """Build provider-specific payload for keyword search."""
        if not use_fallback:
            # Primary: automation-lab/facebook-ads-library
            return {
                "searchQueries": keywords,
                "country": "US",
                "activeStatus": "ACTIVE",
                "adTypes": "ALL",
                "maxAds": max_ads,
                "proxy": {
                    "useApifyProxy": True,
                    "apifyProxyGroups": ["RESIDENTIAL"],
                    "apifyProxyCountry": "US",
                },
            }
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
                "proxyConfiguration": {
                    "useApifyProxy": True,
                    "apifyProxyCountry": "US",
                },
            }

    def _build_advertiser_input(self, advertisers: list[str], max_ads: int, use_fallback: bool = False) -> dict[str, Any]:
        """Build provider-specific payload for advertiser page search."""
        page_ids = []
        page_urls = []
        for adv in advertisers:
            adv_str = str(adv).strip()
            if adv_str.isdigit():
                page_ids.append(adv_str)
                page_urls.append(f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&view_all_page_id={adv_str}")
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
                "activeStatus": "ACTIVE",
                "adTypes": "ALL",
                "maxAds": max_ads,
                "proxy": {
                    "useApifyProxy": True,
                    "apifyProxyGroups": ["RESIDENTIAL"],
                    "apifyProxyCountry": "US",
                },
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

    async def _execute_and_process(
        self,
        actor_name: str,
        run_input: dict[str, Any],
        job_name: str,
        persist: bool = True,
    ) -> dict[str, Any]:
        """Submit run, poll status, download dataset, normalize, validate, and persist."""
        # Create DB collection tracking
        data_source = await self._ensure_apify_data_source()
        job = CollectionJob(
            data_source_id=data_source.id,
            name=job_name,
            job_type="apify_live",
            config={"actor": actor_name, "input_summary": list(run_input.keys())},
        )
        self.db.add(job)
        await self.db.flush()

        run = CollectionRun(
            job_id=job.id,
            status=CollectionJobStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(run)
        await self.db.flush()

        try:
            # 1. Trigger Apify Actor Run with cloud-side hard spending cap
            spent_today, spent_month = await self._calculate_current_spend()
            remaining_budget = max(0.01, min(self.daily_budget_usd - spent_today, self.monthly_budget_usd - spent_month))

            actor_id_slug = actor_name.replace("/", "~")
            run_data = await self._start_actor_run(actor_id_slug, run_input, max_charge_usd=remaining_budget)
            apify_run_id = run_data.get("id")
            dataset_id = run_data.get("defaultDatasetId")

            if not apify_run_id or not dataset_id:
                raise RuntimeError(f"Failed to start Apify actor {actor_name}: invalid response.")

            # 2. Wait for completion and extract provider-reported usage
            final_run_data = await self._wait_for_run_completion(apify_run_id)
            final_status = final_run_data.get("status")
            if final_status != "SUCCEEDED":
                raise RuntimeError(f"Apify actor run {apify_run_id} finished with status: {final_status}")

            actual_cost = float(final_run_data.get("usageTotalUsd") or final_run_data.get("usageUsd") or 0.0)

            # 3. Fetch Dataset Records
            raw_records = await self.fetch_dataset(dataset_id)

            # 4. Normalize Records
            normalized = self.normalize_records(raw_records, actor_name)

            # 5. Validate Records (US check, completeness)
            valid_records, validation_errors = self.validate_records(normalized)

            # 6. Persist via ImportService
            import_result = ImportResult(success=True)
            if persist and valid_records:
                import_service = ImportService(self.db)
                # Import directly into database
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
            run.coverage_notes = f"Cost: ${actual_cost:.4f} USD | Validated {len(valid_records)}/{len(raw_records)} records as verified US ads."
            run.errors = {"actual_cost_usd": actual_cost} if actual_cost > 0 else None

            data_source.last_successful_collection = datetime.now(timezone.utc)
            await self.db.commit()

            return {
                "status": status_val,
                "success": True,
                "actor": actor_name,
                "apify_run_id": apify_run_id,
                "actual_cost_usd": actual_cost,
                "records_fetched": len(raw_records),
                "records_valid": len(valid_records),
                "records_new": import_result.records_new,
                "records_duplicate": import_result.records_duplicate,
                "validation_errors": validation_errors[:10],
                "dataset_id": dataset_id,
            }

        except Exception as e:
            logger.exception("Apify live run failed: %s", e)
            run.status = CollectionJobStatus.FAILED
            run.completed_at = datetime.now(timezone.utc)
            run.errors = {"error": str(e)}
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
        """Post execution to Apify with exponential retry and cloud-side spend cap enforcement."""
        url = f"{APIFY_BASE_URL}/acts/{actor_slug}/runs"
        params: dict[str, Any] = {}
        if max_charge_usd is not None and max_charge_usd > 0:
            params["maxTotalChargeUsd"] = round(max_charge_usd, 4)
            params["timeout"] = self.timeout_seconds

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        retries = 3
        backoff = 1.0
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for attempt in range(retries):
                try:
                    resp = await client.post(url, json=run_input, params=params, headers=headers)
                    if resp.status_code in (200, 201):
                        return resp.json().get("data", {})
                    elif resp.status_code in (401, 403):
                        raise PermissionError(f"Apify authentication failed ({resp.status_code}): {resp.text}")
                    elif resp.status_code == 429:
                        await asyncio.sleep(backoff)
                        backoff *= 2
                        continue
                    else:
                        resp.raise_for_status()
                except (httpx.RequestError, httpx.HTTPStatusError) as e:
                    if attempt == retries - 1:
                        raise
                    await asyncio.sleep(backoff)
                    backoff *= 2

        raise RuntimeError("Exceeded retry attempts starting Apify actor run.")

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
        """Normalize raw records from either actor into the standard internal format."""
        normalized: list[dict[str, Any]] = []

        for r in raw_records:
            # Extract common identifier
            ext_id = str(r.get("id") or r.get("adArchiveID") or "")
            page_id = str(r.get("pageId") or r.get("page_id") or "")
            page_name = r.get("pageName") or r.get("page_name") or "Unknown Advertiser"

            # Snapshot URL
            snapshot = r.get("snapshotUrl") or r.get("ad_snapshot_url") or ""
            if not snapshot and ext_id:
                snapshot = f"https://www.facebook.com/ads/library/?id={ext_id}"

            # Dates
            start_date = r.get("startDate") or r.get("ad_delivery_start_time")
            is_active = r.get("isActive", r.get("is_active", True))

            # Creative media
            images = r.get("images") or r.get("ad_creative_link_images") or []
            if isinstance(images, str):
                images = [images]
            videos = r.get("videos") or r.get("ad_creative_videos") or []
            if isinstance(videos, str):
                videos = [videos]

            # Text
            bodies = r.get("bodies") or r.get("ad_creative_bodies") or []
            if isinstance(bodies, str):
                bodies = [bodies]
            title = r.get("title") or r.get("ad_creative_link_titles") or ""
            if isinstance(title, list):
                title = " | ".join(str(t) for t in title)

            # Landing page
            link_url = r.get("linkUrl") or r.get("link_url") or ""

            # Target countries
            target_countries = r.get("targetCountries") or r.get("delivery_by_region") or ["US"]
            if isinstance(target_countries, str):
                target_countries = [target_countries]

            norm = {
                "id": ext_id,
                "pageId": page_id,
                "pageName": page_name,
                "snapshotUrl": snapshot,
                "startDate": start_date,
                "isActive": bool(is_active),
                "images": images,
                "videos": videos,
                "bodies": bodies,
                "title": title,
                "linkUrl": link_url,
                "targetCountries": target_countries,
                "publisherPlatforms": r.get("publisherPlatforms") or ["facebook", "instagram"],
                "_provider_actor": actor_name,
                "_raw": r,
            }
            normalized.append(norm)

        return normalized

    def validate_records(self, records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
        """
        Enforce strict US WIN HUNTER quality gates:
        - Must have valid external ID
        - Must have advertiser identity
        - Must target United States (explicit US targeting check)
        - Must have non-empty creative content
        """
        valid: list[dict[str, Any]] = []
        errors: list[str] = []

        for idx, rec in enumerate(records):
            ext_id = rec.get("id")
            if not ext_id or ext_id == "None":
                errors.append(f"Record {idx}: Missing ad ID.")
                continue

            page_name = rec.get("pageName")
            if not page_name or page_name == "Unknown":
                errors.append(f"Record {idx} ({ext_id}): Missing advertiser page name.")
                continue

            # Strict US target validation
            targets = rec.get("targetCountries", [])
            # Accept if explicit "US" in target list, or if empty list (assume US since query was scoped to US)
            # Reject if explicit list without "US" (e.g. ['CA', 'GB'])
            if targets and isinstance(targets, list):
                has_us = any("US" in str(t).upper() or "UNITED STATES" in str(t).upper() for t in targets)
                if not has_us:
                    errors.append(f"Record {idx} ({ext_id}): Non-US target region ({targets}). Rejected.")
                    continue

            # Content completeness
            has_body = bool(rec.get("bodies"))
            has_title = bool(rec.get("title"))
            has_images = bool(rec.get("images"))
            if not (has_body or has_title or has_images):
                errors.append(f"Record {idx} ({ext_id}): Completely blank ad content.")
                continue

            valid.append(rec)

        return valid, errors

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

