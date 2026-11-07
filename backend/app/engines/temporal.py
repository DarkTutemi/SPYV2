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

from sqlalchemy import select, func, and_, distinct
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
)

logger = logging.getLogger(__name__)


class TemporalEngine:
    """Temporal advertising intelligence — snapshots and metrics."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Daily Snapshot ───────────────────────────────────────────────────

    async def create_daily_snapshot(self, snapshot_date: Optional[str] = None) -> dict:
        """
        Snapshot all advertisements' current active status for the given date.
        Idempotent: re-running for the same date updates existing snapshots.
        """
        if snapshot_date is None:
            snapshot_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        result = await self.db.execute(select(Advertisement))
        ads = result.scalars().all()

        created = 0
        updated = 0

        for ad in ads:
            existing = await self.db.execute(
                select(AdvertisementSnapshot).where(
                    AdvertisementSnapshot.advertisement_id == ad.id,
                    AdvertisementSnapshot.snapshot_date == snapshot_date,
                )
            )
            snap = existing.scalar_one_or_none()

            if snap:
                snap.is_active = bool(ad.is_active)
                updated += 1
            else:
                snap = AdvertisementSnapshot(
                    advertisement_id=ad.id,
                    snapshot_date=snapshot_date,
                    is_active=bool(ad.is_active),
                    source_type=ad.source_type,
                )
                self.db.add(snap)
                created += 1

        await self.db.flush()
        logger.info("Snapshot %s: %d created, %d updated", snapshot_date, created, updated)
        return {"date": snapshot_date, "created": created, "updated": updated}

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
        """Compute or update one product's daily metric."""
        # Active ads (from snapshots if available, otherwise from advertisement table)
        active_count = (await self.db.execute(
            select(func.count(AdvertisementSnapshot.id)).where(
                AdvertisementSnapshot.snapshot_date == metric_date,
                AdvertisementSnapshot.is_active == True,
                AdvertisementSnapshot.advertisement_id.in_(
                    select(Advertisement.id).where(Advertisement.product_id == product_id)
                ),
            )
        )).scalar() or 0

        # If no snapshots, fall back to advertisement table
        if active_count == 0:
            active_count = (await self.db.execute(
                select(func.count(Advertisement.id)).where(
                    Advertisement.product_id == product_id,
                    Advertisement.is_active == True,
                )
            )).scalar() or 0

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

