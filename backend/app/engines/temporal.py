"""
US WIN HUNTER — Engine C: Temporal Advertising Intelligence

Builds persistent daily snapshots and computes historical metrics.
Supports 7/14/30/60/90-day comparison windows.

IMPORTANT:
- Missing records do NOT mean ads stopped — coverage must be tracked.
- Ad count is an ACTIVITY signal, never sales/revenue/spend/ROAS.
- first_seen_at is when our data first saw it, NOT the product launch date.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func, and_, or_, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Advertisement,
    AdvertisementSnapshot,
    CollectionRun,
    CollectionJobStatus,
    DataSourceType,
    EvidenceType,
    Product,
    ProductDailyMetric,
    SnapshotObservationQuality,
    SourceRecord,
)

logger = logging.getLogger(__name__)


def extract_ad_status(raw_data: Any) -> tuple[Optional[bool], str]:
    """
    Extract active/inactive status from raw source record data according to normalization contract.
    Returns (status_bool, status_str):
      - (True, "ACTIVE")
      - (False, "INACTIVE")
      - (None, "UNKNOWN")
    Never defaults to True/False when status is ambiguous or missing.
    """
    if not isinstance(raw_data, dict):
        return None, "UNKNOWN"

    # 1. Check isActive
    val = raw_data.get("isActive")
    if val is True:
        return True, "ACTIVE"
    if val is False:
        return False, "INACTIVE"
    if isinstance(val, str):
        v = val.strip().lower()
        if v in ("true", "active"):
            return True, "ACTIVE"
        if v in ("false", "inactive", "stopped", "paused", "archived", "completed"):
            return False, "INACTIVE"

    # 2. Check is_active
    val = raw_data.get("is_active")
    if val is True:
        return True, "ACTIVE"
    if val is False:
        return False, "INACTIVE"
    if isinstance(val, str):
        v = val.strip().lower()
        if v in ("true", "active"):
            return True, "ACTIVE"
        if v in ("false", "inactive", "stopped", "paused", "archived", "completed"):
            return False, "INACTIVE"

    # 3. Check activeStatus (from Meta Ad scraper input/output)
    val = raw_data.get("activeStatus")
    if isinstance(val, str):
        v = val.strip().lower()
        if v == "active":
            return True, "ACTIVE"
        if v == "inactive":
            return False, "INACTIVE"
        # "all" is a query filter, not an ad status confirmation!

    # 4. Check status
    val = raw_data.get("status")
    if isinstance(val, str):
        v = val.strip().upper()
        if v in ("ACTIVE", "RUNNING"):
            return True, "ACTIVE"
        if v in ("INACTIVE", "STOPPED", "PAUSED", "ARCHIVED", "COMPLETED", "DELETED"):
            return False, "INACTIVE"

    # Missing or ambiguous
    return None, "UNKNOWN"


class TemporalEngine:
    """Temporal advertising intelligence — snapshots and metrics."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Daily Snapshot ───────────────────────────────────────────────────

    async def create_daily_snapshot(
        self,
        snapshot_date: Optional[str] = None,
        collection_run_id: Optional[str] = None,
        observed_ad_statuses: Optional[dict[str, bool]] = None,
    ) -> dict:
        """
        Snapshot advertisements' status for the given date.
        Observation quality is strictly server-derived and evidence-validated:
        - VERIFIED_SOURCE_OBSERVATION: Confirmed per-ad source evidence from completed collection run or live observation.
        - DATABASE_DERIVED_SNAPSHOT: Analytical projection / backfill without live source evidence.
        - UNKNOWN: Missing or unverified evidence.
        Idempotent: re-running produces consistent state and never overwrites genuine evidence with derived data.
        """
        if snapshot_date is None:
            snapshot_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # 1. Validate collection_run_id if supplied
        validated_run: Optional[CollectionRun] = None
        source_records_by_ext_id: dict[str, Any] = {}

        if collection_run_id:
            run_stmt = select(CollectionRun).where(
                CollectionRun.id == collection_run_id,
                CollectionRun.status == CollectionJobStatus.COMPLETED,
            )
            run_obj = (await self.db.execute(run_stmt)).scalar_one_or_none()
            if not run_obj:
                logger.warning(
                    "Collection run %s not found or not completed. Cannot authenticate observations.",
                    collection_run_id,
                )
            else:
                # Prevent historical runs from manufacturing fresh observation dates
                run_date = (run_obj.completed_at or run_obj.created_at).strftime("%Y-%m-%d")
                if run_date != snapshot_date:
                    logger.warning(
                        "Collection run %s execution date (%s) does not match snapshot date (%s). Rejecting as fresh observation.",
                        collection_run_id,
                        run_date,
                        snapshot_date,
                    )
                else:
                    validated_run = run_obj
                    sr_stmt = select(SourceRecord).where(
                        SourceRecord.collection_run_id == collection_run_id,
                        SourceRecord.source_type == DataSourceType.META_AD_LIBRARY,
                    )
                    srs = (await self.db.execute(sr_stmt)).scalars().all()
                    for sr in srs:
                        if sr.external_id:
                            source_records_by_ext_id[str(sr.external_id)] = sr

        # 2. Scope target advertisements
        has_collection_evidence = bool(validated_run or observed_ad_statuses is not None)

        if has_collection_evidence:
            observed_ext_ids = set(source_records_by_ext_id.keys())
            observed_keys = set(str(k) for k in observed_ad_statuses.keys()) if observed_ad_statuses else set()
            target_ids = observed_ext_ids | observed_keys

            if not target_ids:
                logger.info("Collection run %s contains 0 Meta ad records. Created 0 observations.", collection_run_id)
                return {
                    "date": snapshot_date,
                    "created": 0,
                    "updated": 0,
                    "observation_quality": SnapshotObservationQuality.VERIFIED_SOURCE_OBSERVATION.value if validated_run else SnapshotObservationQuality.DATABASE_DERIVED_SNAPSHOT.value,
                    "collection_run_id": validated_run.id if validated_run else None,
                }

            ad_stmt = select(Advertisement).where(
                or_(
                    Advertisement.external_id.in_(target_ids),
                    Advertisement.id.in_(target_ids),
                )
            )
            ads = list((await self.db.execute(ad_stmt)).scalars().all())
        else:
            # Analytical derived snapshot across all advertisements in database
            ad_stmt = select(Advertisement)
            ads = list((await self.db.execute(ad_stmt)).scalars().all())

        created = 0
        updated = 0
        final_quality = SnapshotObservationQuality.DATABASE_DERIVED_SNAPSHOT.value

        for ad in ads:
            existing = (await self.db.execute(
                select(AdvertisementSnapshot).where(
                    AdvertisementSnapshot.advertisement_id == ad.id,
                    AdvertisementSnapshot.snapshot_date == snapshot_date,
                )
            )).scalar_one_or_none()

            # Prevent derived snapshots from overwriting genuine evidence
            if existing and existing.observation_quality in (
                SnapshotObservationQuality.VERIFIED_SOURCE_OBSERVATION.value,
                SnapshotObservationQuality.GENUINE_SOURCE_OBSERVATION.value,
            ):
                is_verified_input = bool(
                    (validated_run and str(ad.external_id) in source_records_by_ext_id)
                    or (observed_ad_statuses and (ad.id in observed_ad_statuses or ad.external_id in observed_ad_statuses))
                )
                if not is_verified_input:
                    logger.info("Preserving existing verified observation for ad %s on %s; skipping derived overwrite.", ad.id, snapshot_date)
                    continue

            # Determine status and evidence-validated observation quality
            if observed_ad_statuses is not None and (ad.id in observed_ad_statuses or ad.external_id in observed_ad_statuses):
                raw_status_val = observed_ad_statuses.get(ad.id, observed_ad_statuses.get(ad.external_id))
                if isinstance(raw_status_val, bool):
                    status_bool, status_str = raw_status_val, ("ACTIVE" if raw_status_val else "INACTIVE")
                elif isinstance(raw_status_val, dict):
                    status_bool, status_str = extract_ad_status(raw_status_val)
                elif isinstance(raw_status_val, str):
                    v = raw_status_val.strip().lower()
                    if v in ("active", "true"):
                        status_bool, status_str = True, "ACTIVE"
                    elif v in ("inactive", "false"):
                        status_bool, status_str = False, "INACTIVE"
                    else:
                        status_bool, status_str = None, "UNKNOWN"
                else:
                    status_bool, status_str = None, "UNKNOWN"

                if status_bool is None:
                    logger.info("Ad %s has unknown/ambiguous status in observed_ad_statuses; skipping confirmed snapshot.", ad.id)
                    continue

                ad_is_active = status_bool
                quality = SnapshotObservationQuality.VERIFIED_SOURCE_OBSERVATION.value
                active_run_id = validated_run.id if validated_run else (collection_run_id or (existing.collection_run_id if existing else None))
                raw_meta = {
                    "provenance": "observed_ad_statuses",
                    "observation_quality": quality,
                    "collection_run_id": active_run_id,
                    "status": status_str,
                }
            elif validated_run and str(ad.external_id) in source_records_by_ext_id:
                srec = source_records_by_ext_id[str(ad.external_id)]
                status_bool, status_str = extract_ad_status(srec.raw_data)

                if status_bool is None:
                    # Missing or ambiguous status must be UNKNOWN.
                    # Do not create a confirmed active/inactive snapshot from a source record whose status cannot be established.
                    logger.info(
                        "Ad %s status in SourceRecord %s is inconclusive (%s). Skipping confirmed snapshot creation.",
                        ad.id,
                        srec.id,
                        status_str,
                    )
                    continue

                ad_is_active = status_bool
                quality = SnapshotObservationQuality.VERIFIED_SOURCE_OBSERVATION.value
                active_run_id = validated_run.id

                # Do not manufacture an observation timestamp. Use authentic timestamp from source if available.
                obs_timestamp = None
                if isinstance(srec.raw_data, dict):
                    obs_timestamp = srec.raw_data.get("snapshotDate") or srec.raw_data.get("timestamp") or srec.raw_data.get("observed_at")

                raw_meta = {
                    "provenance": "verified_source_record",
                    "observation_quality": quality,
                    "source_record_id": srec.id,
                    "collection_run_id": validated_run.id,
                    "ad_archive_id": ad.external_id,
                    "status": status_str,
                }
                if obs_timestamp:
                    raw_meta["observed_at"] = obs_timestamp
            else:
                # Derived projection without live source observation
                ad_is_active = bool(ad.is_active)
                quality = SnapshotObservationQuality.DATABASE_DERIVED_SNAPSHOT.value
                active_run_id = None
                raw_meta = {
                    "provenance": "database_derived_projection",
                    "observation_quality": quality,
                    "note": "analytical snapshot without live Meta source observation",
                }

            final_quality = quality

            if snap := existing:
                snap.is_active = ad_is_active
                snap.observation_quality = quality
                snap.collection_run_id = active_run_id
                snap.raw_snapshot = raw_meta
                updated += 1
            else:
                snap = AdvertisementSnapshot(
                    advertisement_id=ad.id,
                    snapshot_date=snapshot_date,
                    is_active=ad_is_active,
                    source_type=ad.source_type,
                    collection_run_id=active_run_id,
                    observation_quality=quality,
                    raw_snapshot=raw_meta,
                )
                self.db.add(snap)
                created += 1

        await self.db.flush()
        logger.info(
            "Snapshot %s (quality=%s): %d created, %d updated",
            snapshot_date,
            final_quality,
            created,
            updated,
        )
        return {
            "date": snapshot_date,
            "created": created,
            "updated": updated,
            "observation_quality": final_quality,
            "collection_run_id": validated_run.id if validated_run else None,
        }

    # ── Daily Metrics Aggregation ────────────────────────────────────────

    async def aggregate_daily_metrics(self, metric_date: Optional[str] = None) -> list[ProductDailyMetric]:
        """
        Compute daily aggregated metrics for all US products.
        Idempotent upsert.
        """
        if metric_date is None:
            metric_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Get all US product IDs
        result = await self.db.execute(
            select(Product.id).where(Product.target_country == "US")
        )
        product_ids = [row[0] for row in result.all()]

        metrics = []
        for pid in product_ids:
            m = await self._compute_product_daily_metric(pid, metric_date)
            if m:
                metrics.append(m)

        await self.db.flush()
        logger.info("Aggregated daily metrics for %d products on %s", len(metrics), metric_date)
        return metrics

    async def _compute_product_daily_metric(
        self, product_id: str, metric_date: str
    ) -> Optional[ProductDailyMetric]:
        """
        Compute or update one product's daily metric.
        Requires genuine source observation provenance for confirmed active ads.
        Zero confirmed active ads stays strictly zero (no fallback to advertisements table).
        """
        # Active ads: count ONLY genuine source observations where is_active is True!
        active_count = (await self.db.execute(
            select(func.count(AdvertisementSnapshot.id)).where(
                AdvertisementSnapshot.snapshot_date == metric_date,
                AdvertisementSnapshot.is_active == True,
                AdvertisementSnapshot.observation_quality.in_([
                    SnapshotObservationQuality.VERIFIED_SOURCE_OBSERVATION.value,
                    SnapshotObservationQuality.GENUINE_SOURCE_OBSERVATION.value,
                ]),
                AdvertisementSnapshot.advertisement_id.in_(
                    select(Advertisement.id).where(Advertisement.product_id == product_id)
                ),
            )
        )).scalar() or 0

        # Note: We do NOT fall back to the advertisements table!
        # Requirement 4: When active snapshots for a date are zero because no collection was executed
        # or no ads were confirmed active, DO NOT fall back to historic Advertisement.is_active.
        # Zero confirmed active ads is zero.

        # New ads (first_seen on this date)
        new_ad_count = (await self.db.execute(
            select(func.count(Advertisement.id)).where(
                Advertisement.product_id == product_id,
                func.substr(func.cast(Advertisement.first_seen_at, sqlalchemy_text_type()), 1, 10) == metric_date,
            )
        )).scalar() or 0

        # Unique advertisers
        unique_adv = (await self.db.execute(
            select(func.count(distinct(Advertisement.advertiser_id))).where(
                Advertisement.product_id == product_id,
            )
        )).scalar() or 0

        # New advertisers (first ad for this product from this advertiser on this date)
        # Approximation: advertisers whose earliest ad for this product was first_seen on this date
        new_adv = (await self.db.execute(
            select(func.count(distinct(Advertisement.advertiser_id))).where(
                Advertisement.product_id == product_id,
                func.substr(func.cast(Advertisement.first_seen_at, sqlalchemy_text_type()), 1, 10) == metric_date,
            )
        )).scalar() or 0

        # Coverage: check if we had a successful collection run today
        coverage = await self._estimate_coverage(metric_date)

        # Upsert
        existing = await self.db.execute(
            select(ProductDailyMetric).where(
                ProductDailyMetric.product_id == product_id,
                ProductDailyMetric.metric_date == metric_date,
            )
        )
        m = existing.scalar_one_or_none()

        if m is None:
            m = ProductDailyMetric(
                product_id=product_id,
                metric_date=metric_date,
            )
            self.db.add(m)

        m.active_ad_count = active_count
        m.new_ad_count = new_ad_count
        m.unique_advertiser_count = unique_adv
        m.new_advertiser_count = new_adv
        m.coverage_completeness = coverage
        m.evidence_type = EvidenceType.DERIVED_METRIC

        return m

    async def _estimate_coverage(self, metric_date: str) -> float:
        """Estimate collection coverage for a given date (0.0 to 1.0)."""
        # Check if any successful collection run happened on this date
        result = await self.db.execute(
            select(func.count(CollectionRun.id)).where(
                CollectionRun.status == CollectionJobStatus.COMPLETED,
                func.substr(func.cast(CollectionRun.created_at, sqlalchemy_text_type()), 1, 10) == metric_date,
            )
        )
        run_count = result.scalar() or 0

        if run_count == 0:
            return 0.0  # No data collected on this date
        return min(1.0, run_count * 0.5)  # Heuristic: more runs = better coverage, capped at 1.0

    # ── Window Comparison ────────────────────────────────────────────────

    async def compute_window_comparison(
        self, product_id: str, window_days: int = 7
    ) -> dict:
        """
        Compare a recent window against the prior window of the same length.
        Supports 7, 14, 30, 60, 90-day windows.
        """
        now = datetime.now(timezone.utc)
        recent_start = (now - timedelta(days=window_days)).strftime("%Y-%m-%d")
        prior_start = (now - timedelta(days=window_days * 2)).strftime("%Y-%m-%d")
        recent_end = now.strftime("%Y-%m-%d")

        async def window_stats(start: str, end: str) -> dict:
            metrics_result = await self.db.execute(
                select(ProductDailyMetric).where(
                    ProductDailyMetric.product_id == product_id,
                    ProductDailyMetric.metric_date >= start,
                    ProductDailyMetric.metric_date <= end,
                )
            )
            rows = list(metrics_result.scalars().all())
            if not rows:
                return {
                    "days_with_data": 0,
                    "avg_active_ads": 0,
                    "total_new_ads": 0,
                    "max_advertisers": 0,
                    "avg_coverage": 0,
                }
            return {
                "days_with_data": len(rows),
                "avg_active_ads": round(sum(r.active_ad_count for r in rows) / len(rows), 2),
                "total_new_ads": sum(r.new_ad_count for r in rows),
                "max_advertisers": max(r.unique_advertiser_count for r in rows),
                "avg_coverage": round(sum(r.coverage_completeness or 0 for r in rows) / len(rows), 3),
            }

        recent = await window_stats(recent_start, recent_end)
        prior = await window_stats(prior_start, recent_start)

        # Compute deltas with safety for zero denominators
        def safe_delta(recent_val: float, prior_val: float) -> Optional[float]:
            if prior_val == 0:
                return None  # Cannot compute growth from zero base
            return round((recent_val - prior_val) / prior_val, 3)

        return {
            "product_id": product_id,
            "window_days": window_days,
            "recent_window": {"start": recent_start, "end": recent_end, **recent},
            "prior_window": {"start": prior_start, "end": recent_start, **prior},
            "deltas": {
                "avg_active_ads": safe_delta(recent["avg_active_ads"], prior["avg_active_ads"]),
                "total_new_ads": safe_delta(recent["total_new_ads"], prior["total_new_ads"]),
                "max_advertisers": safe_delta(recent["max_advertisers"], prior["max_advertisers"]),
            },
            "coverage_warning": (
                "Low data coverage in one or both windows — trends may be artifacts of missing collection runs"
                if recent["avg_coverage"] < 0.3 or prior["avg_coverage"] < 0.3
                else None
            ),
        }

    # ── Emergence Detection ──────────────────────────────────────────────

    async def detect_emerging_products(self, min_window: int = 7) -> list[dict]:
        """
        Find products with accelerating signals.
        Returns products sorted by acceleration strength.
        """
        result = await self.db.execute(
            select(Product.id, Product.name).where(Product.target_country == "US")
        )
        products = result.all()

        emerging = []
        for pid, pname in products:
            comparison = await self.compute_window_comparison(pid, min_window)

            recent = comparison["recent_window"]
            deltas = comparison["deltas"]

            # Skip products with no recent data
            if recent["days_with_data"] == 0:
                continue

            # Acceleration: positive delta in new ads or advertisers
            ad_delta = deltas.get("total_new_ads")
            adv_delta = deltas.get("max_advertisers")

            acceleration = 0.0
            if ad_delta is not None and ad_delta > 0:
                acceleration += min(ad_delta * 30, 50)
            if adv_delta is not None and adv_delta > 0:
                acceleration += min(adv_delta * 40, 50)

            if acceleration > 0:
                emerging.append({
                    "product_id": pid,
                    "product_name": pname,
                    "acceleration": round(acceleration, 2),
                    "window_days": min_window,
                    "comparison": comparison,
                    "coverage_warning": comparison.get("coverage_warning"),
                })

        emerging.sort(key=lambda x: x["acceleration"], reverse=True)
        return emerging


# Helper to work around SQLite/PostgreSQL cast differences
def sqlalchemy_text_type():
    """Return SQLAlchemy String type for CAST operations."""
    from sqlalchemy import String
    return String

