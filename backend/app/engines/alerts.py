"""
US WIN HUNTER — Alert Engine

Detects notable changes in advertising patterns and generates structured alerts.
Alerts are signals for operator review — never treated as definitive events.

Alert types:
- new_advertiser_entry: A product gained new independent advertisers
- creative_spike: Unusual surge in new creatives for a product
- sudden_contraction: Active ads dropped significantly (may be coverage gap)
- sustained_growth: Product shows consistent growth over multiple windows
- coverage_gap: Missing collection data may affect metric reliability
- high_emergence_low_confidence: High score but weak evidence
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Advertisement,
    Alert,
    AlertSeverity,
    AlertType,
    OpportunityScore,
    Product,
    ProductDailyMetric,
)

logger = logging.getLogger(__name__)


class AlertEngine:
    """Generates structured alerts from temporal analysis."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def run_all_detectors(self, analysis_date: Optional[str] = None) -> list[Alert]:
        """Run all alert detectors and return generated alerts."""
        if analysis_date is None:
            analysis_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        alerts: list[Alert] = []

        # Get all US products
        result = await self.db.execute(
            select(Product).where(Product.target_country == "US")
        )
        products = list(result.scalars().all())

        for product in products:
            alerts.extend(await self._detect_new_advertiser_entry(product, analysis_date))
            alerts.extend(await self._detect_creative_spike(product, analysis_date))
            alerts.extend(await self._detect_sudden_contraction(product, analysis_date))
            alerts.extend(await self._detect_sustained_growth(product, analysis_date))

        # System-level detectors
        alerts.extend(await self._detect_coverage_gaps(analysis_date))
        alerts.extend(await self._detect_high_emergence_low_confidence(analysis_date))

        # Deduplicate: don't re-create alerts for same entity+type+date
        new_alerts = []
        for alert in alerts:
            existing = await self.db.execute(
                select(Alert).where(
                    Alert.alert_type == alert.alert_type,
                    Alert.entity_type == alert.entity_type,
                    Alert.entity_id == alert.entity_id,
                    func.substr(func.cast(Alert.created_at, _str_type()), 1, 10) == analysis_date,
                )
            )
            if existing.scalar_one_or_none() is None:
                self.db.add(alert)
                new_alerts.append(alert)

        await self.db.flush()
        logger.info("Alert engine generated %d new alerts on %s", len(new_alerts), analysis_date)
        return new_alerts

    # ── Detectors ────────────────────────────────────────────────────────

    async def _detect_new_advertiser_entry(
        self, product: Product, analysis_date: str
    ) -> list[Alert]:
        """Detect when new independent advertisers start promoting a product."""
        alerts = []
        date_obj = datetime.strptime(analysis_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        week_ago = (date_obj - timedelta(days=7)).strftime("%Y-%m-%d")

        # Get recent metrics
        recent = await self.db.execute(
            select(ProductDailyMetric).where(
                ProductDailyMetric.product_id == product.id,
                ProductDailyMetric.metric_date == analysis_date,
            )
        )
        recent_metric = recent.scalar_one_or_none()

        prior = await self.db.execute(
            select(ProductDailyMetric).where(
                ProductDailyMetric.product_id == product.id,
                ProductDailyMetric.metric_date == week_ago,
            )
        )
        prior_metric = prior.scalar_one_or_none()

        if recent_metric and recent_metric.new_advertiser_count > 0:
            prior_count = prior_metric.unique_advertiser_count if prior_metric else 0
            if recent_metric.new_advertiser_count >= 2 or (
                prior_count > 0 and recent_metric.unique_advertiser_count > prior_count * 1.5
            ):
                alerts.append(Alert(
                    alert_type=AlertType.NEW_ADVERTISER_ENTRY,
                    severity=AlertSeverity.WARNING,
                    title=f"New advertisers promoting: {product.name}",
                    description=(
                        f"{recent_metric.new_advertiser_count} new advertiser(s) observed. "
                        f"Total: {recent_metric.unique_advertiser_count} "
                        f"(was {prior_count} a week ago). "
                        f"This is an advertising activity signal, not a confirmed sales indicator."
                    ),
                    entity_type="product",
                    entity_id=product.id,
                    entity_name=product.name,
                    data={
                        "new_count": recent_metric.new_advertiser_count,
                        "total_count": recent_metric.unique_advertiser_count,
                        "prior_count": prior_count,
                        "analysis_date": analysis_date,
                    },
                ))
        return alerts

    async def _detect_creative_spike(
        self, product: Product, analysis_date: str
    ) -> list[Alert]:
        """Detect unusual surge in new ad creatives."""
        alerts = []

        # Get last 7 days of metrics
        date_obj = datetime.strptime(analysis_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        week_ago = (date_obj - timedelta(days=7)).strftime("%Y-%m-%d")

        result = await self.db.execute(
            select(ProductDailyMetric).where(
                ProductDailyMetric.product_id == product.id,
                ProductDailyMetric.metric_date >= week_ago,
                ProductDailyMetric.metric_date <= analysis_date,
            )
        )
        recent_metrics = list(result.scalars().all())

        if len(recent_metrics) < 2:
            return alerts

        # Today's new ads vs average
        today_metric = next(
            (m for m in recent_metrics if m.metric_date == analysis_date), None
        )
        if today_metric is None:
            return alerts

        prior_metrics = [m for m in recent_metrics if m.metric_date != analysis_date]
        if not prior_metrics:
            return alerts

        avg_new_ads = sum(m.new_ad_count for m in prior_metrics) / len(prior_metrics)

        # Spike: today's new ads > 3x the average and at least 3 new ads
        if today_metric.new_ad_count >= 3 and avg_new_ads > 0 and today_metric.new_ad_count > avg_new_ads * 3:
            alerts.append(Alert(
                alert_type=AlertType.CREATIVE_SPIKE,
                severity=AlertSeverity.WARNING,
                title=f"Creative spike: {product.name}",
                description=(
                    f"{today_metric.new_ad_count} new ads observed today "
                    f"(7-day avg: {avg_new_ads:.1f}). "
                    f"This may indicate accelerating creative production or a testing phase."
                ),
                entity_type="product",
                entity_id=product.id,
                entity_name=product.name,
                data={
                    "new_ads_today": today_metric.new_ad_count,
                    "avg_new_ads_7d": round(avg_new_ads, 2),
                    "spike_ratio": round(today_metric.new_ad_count / max(avg_new_ads, 0.1), 2),
                    "analysis_date": analysis_date,
                },
            ))
        return alerts

    async def _detect_sudden_contraction(
        self, product: Product, analysis_date: str
    ) -> list[Alert]:
        """Detect significant drop in active ads (with coverage caveat)."""
        alerts = []
        date_obj = datetime.strptime(analysis_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        week_ago = (date_obj - timedelta(days=7)).strftime("%Y-%m-%d")

        today_result = await self.db.execute(
            select(ProductDailyMetric).where(
                ProductDailyMetric.product_id == product.id,
                ProductDailyMetric.metric_date == analysis_date,
            )
        )
        today = today_result.scalar_one_or_none()

        prior_result = await self.db.execute(
            select(ProductDailyMetric).where(
                ProductDailyMetric.product_id == product.id,
                ProductDailyMetric.metric_date == week_ago,
            )
        )
        prior = prior_result.scalar_one_or_none()

        if today and prior and prior.active_ad_count >= 3:
            drop_ratio = 1 - (today.active_ad_count / max(prior.active_ad_count, 1))
            if drop_ratio >= 0.5:  # 50%+ drop
                coverage_note = ""
                if today.coverage_completeness is not None and today.coverage_completeness < 0.5:
                    coverage_note = (
                        " WARNING: Low data coverage today — this contraction "
                        "may be an artifact of missing collection runs, not actual ad removal."
                    )

                alerts.append(Alert(
                    alert_type=AlertType.SUDDEN_CONTRACTION,
                    severity=AlertSeverity.CRITICAL if drop_ratio >= 0.8 else AlertSeverity.WARNING,
                    title=f"Ad contraction: {product.name}",
                    description=(
                        f"Active ads dropped {drop_ratio:.0%}: "
                        f"{prior.active_ad_count} → {today.active_ad_count}.{coverage_note}"
                    ),
                    entity_type="product",
                    entity_id=product.id,
                    entity_name=product.name,
                    data={
                        "prior_active": prior.active_ad_count,
                        "current_active": today.active_ad_count,
                        "drop_ratio": round(drop_ratio, 3),
                        "coverage_today": today.coverage_completeness,
                        "analysis_date": analysis_date,
                    },
                ))
        return alerts

    async def _detect_sustained_growth(
        self, product: Product, analysis_date: str
    ) -> list[Alert]:
        """Detect products with consistent growth over 14+ days."""
        alerts = []
        date_obj = datetime.strptime(analysis_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        two_weeks_ago = (date_obj - timedelta(days=14)).strftime("%Y-%m-%d")

        result = await self.db.execute(
            select(ProductDailyMetric).where(
                ProductDailyMetric.product_id == product.id,
                ProductDailyMetric.metric_date >= two_weeks_ago,
                ProductDailyMetric.metric_date <= analysis_date,
            ).order_by(ProductDailyMetric.metric_date)
        )
        metrics = list(result.scalars().all())

        if len(metrics) < 7:  # Need at least 7 data points
            return alerts

        # Check if active_ad_count is generally trending up
        half = len(metrics) // 2
        first_half_avg = sum(m.active_ad_count for m in metrics[:half]) / half
        second_half_avg = sum(m.active_ad_count for m in metrics[half:]) / len(metrics[half:])

        if first_half_avg > 0 and second_half_avg > first_half_avg * 1.3:
            # Also check advertiser count is growing
            first_advs = max(m.unique_advertiser_count for m in metrics[:half])
            second_advs = max(m.unique_advertiser_count for m in metrics[half:])

            if second_advs >= first_advs:
                alerts.append(Alert(
                    alert_type=AlertType.SUSTAINED_GROWTH,
                    severity=AlertSeverity.INFO,
                    title=f"Sustained growth: {product.name}",
                    description=(
                        f"Consistent upward trend over {len(metrics)} days. "
                        f"Avg active ads: {first_half_avg:.1f} → {second_half_avg:.1f}. "
                        f"Advertisers: {first_advs} → {second_advs}."
                    ),
                    entity_type="product",
                    entity_id=product.id,
                    entity_name=product.name,
                    data={
                        "first_half_avg_ads": round(first_half_avg, 2),
                        "second_half_avg_ads": round(second_half_avg, 2),
                        "first_half_max_advs": first_advs,
                        "second_half_max_advs": second_advs,
                        "days_analyzed": len(metrics),
                        "analysis_date": analysis_date,
                    },
                ))
        return alerts

    async def _detect_coverage_gaps(self, analysis_date: str) -> list[Alert]:
        """Detect days where collection coverage is suspiciously low."""
        alerts = []

        result = await self.db.execute(
            select(ProductDailyMetric).where(
                ProductDailyMetric.metric_date == analysis_date,
                ProductDailyMetric.coverage_completeness < 0.3,
            )
        )
        low_coverage = list(result.scalars().all())

        if low_coverage:
            product_ids = list(set(m.product_id for m in low_coverage))
            # Create one alert per affected product
            for pid in product_ids[:10]:  # Cap at 10 to avoid alert storm
                product = await self.db.get(Product, pid)
                if product:
                    alerts.append(Alert(
                        alert_type=AlertType.COVERAGE_GAP,
                        severity=AlertSeverity.INFO,
                        title=f"Low data coverage: {product.name}",
                        description=(
                            f"Coverage completeness < 30% on {analysis_date}. "
                            f"Temporal metrics may be unreliable. "
                            f"Check if collection jobs ran successfully."
                        ),
                        entity_type="product",
                        entity_id=pid,
                        entity_name=product.name,
                        data={"analysis_date": analysis_date},
                    ))
        return alerts

    async def _detect_high_emergence_low_confidence(self, analysis_date: str) -> list[Alert]:
        """Flag products where scoring flagged requires_verification."""
        alerts = []

        result = await self.db.execute(
            select(OpportunityScore).where(
                OpportunityScore.score_date == analysis_date,
                OpportunityScore.requires_verification == True,
            )
        )
        flagged = list(result.scalars().all())

        for score in flagged:
            product = await self.db.get(Product, score.product_id)
            if product:
                alerts.append(Alert(
                    alert_type=AlertType.HIGH_EMERGENCE_LOW_CONFIDENCE,
                    severity=AlertSeverity.WARNING,
                    title=f"Verification needed: {product.name}",
                    description=(
                        f"Emergence: {score.emergence_score:.0f}, "
                        f"Confidence: {score.evidence_confidence:.0f}. "
                        f"Reason: {score.verification_reason or 'Unknown'}. "
                        f"Review evidence before acting on this product."
                    ),
                    entity_type="product",
                    entity_id=score.product_id,
                    entity_name=product.name,
                    data={
                        "emergence_score": score.emergence_score,
                        "evidence_confidence": score.evidence_confidence,
                        "composite_score": score.composite_score,
                        "verification_reason": score.verification_reason,
                        "score_date": analysis_date,
                    },
                ))
        return alerts


def _str_type():
    """Return SQLAlchemy String type for CAST operations."""
    from sqlalchemy import String
    return String

