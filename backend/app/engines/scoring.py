"""
US WIN HUNTER — Opportunity Scoring Engine

Implements three independent scores:
1. Emergence Score (0-100) — advertising momentum signal
2. Evidence Confidence (0-100) — data quality/reliability
3. Bundle Potential (0-100) — natural multi-unit demand

All computations are deterministic. AI is NOT used for score calculation.
Weights are configurable via environment variables.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.models import (
    Advertisement,
    AdvertisementSnapshot,
    Advertiser,
    BundleMechanism,
    BundleOffer,
    ConfidenceLevel,
    EvidenceLink,
    EvidenceType,
    OpportunityScore,
    Product,
    ProductCluster,
    ProductClusterMember,
    ProductDailyMetric,
    SourceRecord,
)

logger = logging.getLogger(__name__)


class ScoringEngine:
    """Deterministic opportunity scoring for products."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    async def score_product(self, product_id: str, score_date: Optional[str] = None) -> OpportunityScore:
        """Compute all three scores for a product."""
        if score_date is None:
            score_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        product = await self.db.get(Product, product_id)
        if not product:
            raise ValueError(f"Product not found: {product_id}")

        emergence = await self._compute_emergence(product, score_date)
        confidence = await self._compute_confidence(product, score_date)
        bundle = await self._compute_bundle_potential(product, score_date)

        # Composite: geometric mean of emergence and confidence, weighted by bundle
        composite = self._compute_composite(emergence, confidence, bundle)

        # Determine verification requirement
        requires_verification = False
        verification_reason = None
        if emergence["score"] >= 50 and confidence["score"] < 30:
            requires_verification = True
            verification_reason = "High emergence but low evidence confidence"
        elif confidence["score"] < 20:
            requires_verification = True
            verification_reason = "Very low evidence confidence — insufficient data"

        # Upsert score
        existing = await self.db.execute(
            select(OpportunityScore).where(
                OpportunityScore.product_id == product_id,
                OpportunityScore.score_date == score_date,
            )
        )
        score = existing.scalar_one_or_none()

        if score is None:
            score = OpportunityScore(product_id=product_id, score_date=score_date)
            self.db.add(score)

        score.emergence_score = emergence["score"]
        score.emergence_components = emergence["components"]
        score.evidence_confidence = confidence["score"]
        score.confidence_components = confidence["components"]
        score.bundle_potential = bundle["score"]
        score.bundle_components = bundle["components"]
        score.composite_score = composite
        score.requires_verification = requires_verification
        score.verification_reason = verification_reason
        score.weights_version = "v1"
        score.weights_snapshot = {
            "emergence": self.settings.emergence_weights,
            "confidence": self.settings.confidence_weights,
            "bundle": self.settings.bundle_weights,
        }

        await self.db.flush()
        return score

    # ── Emergence Score ──────────────────────────────────────────────────

    async def _compute_emergence(self, product: Product, score_date: str) -> dict:
        """
        Emergence Score: advertising momentum signal.
        NOT a sales or revenue indicator.
        """
        weights = self.settings.emergence_weights
        components = {}
        now = datetime.now(timezone.utc)

        # 1. Independent advertiser acceleration (30%)
        adv_accel = await self._advertiser_acceleration(product.id, now)
        components["advertiser_accel"] = {
            "raw": adv_accel,
            "weight": weights["advertiser_accel"],
            "description": "Growth rate of independent advertisers promoting this product",
        }

        # 2. New creative acceleration (25%)
        creative_accel = await self._creative_acceleration(product.id, now)
        components["creative_accel"] = {
            "raw": creative_accel,
            "weight": weights["creative_accel"],
            "description": "Rate of new ad creatives being produced",
        }

        # 3. Ad persistence (20%)
        persistence = await self._ad_persistence(product.id, now)
        components["ad_persistence"] = {
            "raw": persistence,
            "weight": weights["ad_persistence"],
            "description": "How long ads stay active (sustained investment signal)",
        }

        # 4. Signal recency (15%)
        recency = await self._signal_recency(product.id, now)
        components["signal_recency"] = {
            "raw": recency,
            "weight": weights["signal_recency"],
            "description": "How recent the latest advertising activity is",
        }

        # 5. Independent demand confirmation (10%)
        demand = await self._demand_confirmation(product.id, now)
        components["demand_confirm"] = {
            "raw": demand,
            "weight": weights["demand_confirm"],
            "description": "Corroborating signals from non-advertising sources",
        }

        # Weighted sum
        total = sum(
            components[k]["raw"] * components[k]["weight"]
            for k in components
        )
        total = min(100.0, max(0.0, total))

        return {"score": round(total, 2), "components": components}

    async def _advertiser_acceleration(self, product_id: str, now: datetime) -> float:
        """Count of independent advertisers in recent vs prior window."""
        recent_cutoff = now - timedelta(days=14)
        prior_cutoff = now - timedelta(days=28)

        recent_advs = (await self.db.execute(
            select(func.count(func.distinct(Advertisement.advertiser_id))).where(
                Advertisement.product_id == product_id,
                Advertisement.first_seen_at >= recent_cutoff,
            )
        )).scalar() or 0

        prior_advs = (await self.db.execute(
            select(func.count(func.distinct(Advertisement.advertiser_id))).where(
                Advertisement.product_id == product_id,
                Advertisement.first_seen_at >= prior_cutoff,
                Advertisement.first_seen_at < recent_cutoff,
            )
        )).scalar() or 0

        if prior_advs == 0 and recent_advs == 0:
            return 0.0
        if prior_advs == 0 and recent_advs > 0:
            return min(100.0, recent_advs * 25.0)  # New entrants, capped

        growth_rate = (recent_advs - prior_advs) / max(prior_advs, 1)
        return min(100.0, max(0.0, 50 + growth_rate * 50))

    async def _creative_acceleration(self, product_id: str, now: datetime) -> float:
        """New ads in recent window."""
        recent_cutoff = now - timedelta(days=7)
        prior_cutoff = now - timedelta(days=14)

        recent = (await self.db.execute(
            select(func.count(Advertisement.id)).where(
                Advertisement.product_id == product_id,
                Advertisement.first_seen_at >= recent_cutoff,
            )
        )).scalar() or 0

        prior = (await self.db.execute(
            select(func.count(Advertisement.id)).where(
                Advertisement.product_id == product_id,
                Advertisement.first_seen_at >= prior_cutoff,
                Advertisement.first_seen_at < recent_cutoff,
            )
        )).scalar() or 0

        if prior == 0 and recent == 0:
            return 0.0
        if prior == 0 and recent > 0:
            return min(100.0, recent * 20.0)

        growth = (recent - prior) / max(prior, 1)
        return min(100.0, max(0.0, 50 + growth * 50))

    async def _ad_persistence(self, product_id: str, now: datetime) -> float:
        """Average days that product's ads have remained active."""
        result = await self.db.execute(
            select(Advertisement.first_seen_at, Advertisement.last_seen_at)
            .where(Advertisement.product_id == product_id)
        )
        rows = result.all()
        if not rows:
            return 0.0
        spans = [
            max(0.0, (last - first).total_seconds() / 86400)
            for first, last in rows if first and last
        ]
        if not spans:
            return 0.0
        avg_days = sum(spans) / len(spans)

        # Normalize: 0 days = 0, 30+ days = 100
        return min(100.0, max(0.0, (avg_days / 30) * 100))

    async def _signal_recency(self, product_id: str, now: datetime) -> float:
        """How recent the latest ad activity is."""
        result = await self.db.execute(
            select(func.max(Advertisement.last_seen_at)).where(
                Advertisement.product_id == product_id
            )
        )
        last_seen = result.scalar()

        if last_seen is None:
            return 0.0

        if isinstance(last_seen, str):
            last_seen = datetime.fromisoformat(last_seen)
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)

        days_ago = (now - last_seen).days
        if days_ago <= 1:
            return 100.0
        elif days_ago <= 7:
            return 80.0
        elif days_ago <= 14:
            return 60.0
        elif days_ago <= 30:
            return 40.0
        elif days_ago <= 60:
            return 20.0
        return 0.0

    async def _demand_confirmation(self, product_id: str, now: datetime) -> float:
        """Cross-source evidence of demand (pain clusters, trends, etc.)."""
        # Count evidence links from non-advertising sources
        from app.models.models import EvidenceLink
        result = await self.db.execute(
            select(func.count(EvidenceLink.id)).where(
                EvidenceLink.entity_type == "product",
                EvidenceLink.entity_id == product_id,
            )
        )
        evidence_count = result.scalar() or 0

        if evidence_count == 0:
            return 0.0
        return min(100.0, evidence_count * 20.0)

    # ── Evidence Confidence ──────────────────────────────────────────────

    async def _compute_confidence(self, product: Product, score_date: str) -> dict:
        """Evidence Confidence: data quality and reliability."""
        weights = self.settings.confidence_weights
        components = {}

        # 1. Data coverage (30%)
        coverage = await self._data_coverage(product.id)
        components["coverage"] = {
            "raw": coverage,
            "weight": weights["coverage"],
            "description": "Temporal data coverage and collection consistency",
        }

        # 2. Independent sources (25%)
        sources = await self._independent_sources(product.id)
        components["independent_sources"] = {
            "raw": sources,
            "weight": weights["independent_sources"],
            "description": "Number of independent data sources confirming the product",
        }

        # 3. Product identity confidence (20%)
        identity = self._product_identity_confidence(product)
        components["product_identity"] = {
            "raw": identity,
            "weight": weights["product_identity"],
            "description": "Confidence in product identification accuracy",
        }

        # 4. Advertiser independence (15%)
        adv_independence = await self._advertiser_independence(product.id)
        components["advertiser_independence"] = {
            "raw": adv_independence,
            "weight": weights["advertiser_independence"],
            "description": "Verification that advertisers are independent entities",
        }

        # 5. Evidence links (10%)
        evidence = await self._evidence_links_score(product.id)
        components["evidence_links"] = {
            "raw": evidence,
            "weight": weights["evidence_links"],
            "description": "Verifiable source URLs and timestamps attached to claims",
        }

        total = sum(components[k]["raw"] * components[k]["weight"] for k in components)
        total = min(100.0, max(0.0, total))

        return {"score": round(total, 2), "components": components}

    async def _data_coverage(self, product_id: str) -> float:
        """How many days have data points."""
        result = await self.db.execute(
            select(func.count(ProductDailyMetric.id)).where(
                ProductDailyMetric.product_id == product_id
            )
        )
        days_with_data = result.scalar() or 0

        result2 = await self.db.execute(
            select(
                func.min(Advertisement.first_seen_at),
                func.max(Advertisement.last_seen_at),
            ).where(Advertisement.product_id == product_id)
        )
        row = result2.one_or_none()
        if not row or not row[0] or not row[1]:
            return 0.0

        first, last = row
        if isinstance(first, str):
            first = datetime.fromisoformat(first)
        if isinstance(last, str):
            last = datetime.fromisoformat(last)

        total_days = max(1, (last - first).days + 1)
        coverage = days_with_data / total_days
        return min(100.0, coverage * 100)

    async def _independent_sources(self, product_id: str) -> float:
        """Count of distinct source types."""
        result = await self.db.execute(
            select(func.count(func.distinct(Advertisement.source_type))).where(
                Advertisement.product_id == product_id
            )
        )
        source_count = result.scalar() or 0

        # 1 source = 25, 2 = 50, 3 = 75, 4+ = 100
        return min(100.0, source_count * 25.0)

    def _product_identity_confidence(self, product: Product) -> float:
        """How well-identified is this product."""
        score = 0.0
        if product.name and len(product.name) > 5:
            score += 20
        if product.description and len(product.description) > 20:
            score += 20
        if product.image_url:
            score += 20
        if product.source_url:
            score += 15
        if product.category:
            score += 10
        if product.normalized_name:
            score += 15
        return min(100.0, score)

    async def _advertiser_independence(self, product_id: str) -> float:
        """Verify distinct advertisers are actually independent."""
        result = await self.db.execute(
            select(func.count(func.distinct(Advertisement.advertiser_id))).where(
                Advertisement.product_id == product_id
            )
        )
        adv_count = result.scalar() or 0

        if adv_count <= 1:
            return 20.0  # Single advertiser — low confidence in independence
        elif adv_count <= 3:
            return 50.0
        elif adv_count <= 5:
            return 70.0
        return min(100.0, 70 + (adv_count - 5) * 5)

    async def _evidence_links_score(self, product_id: str) -> float:
        """How many verifiable evidence links exist."""
        result = await self.db.execute(
            select(func.count(EvidenceLink.id)).where(
                EvidenceLink.entity_type == "product",
                EvidenceLink.entity_id == product_id,
                EvidenceLink.source_url.isnot(None),
            )
        )
        count = result.scalar() or 0

        return min(100.0, count * 15.0)

    # ── Bundle Potential ─────────────────────────────────────────────────

    async def _compute_bundle_potential(self, product: Product, score_date: str) -> dict:
        """Bundle Potential: natural multi-unit demand."""
        weights = self.settings.bundle_weights
        components = {}

        bundles = await self.db.execute(
            select(BundleOffer).where(BundleOffer.product_id == product.id)
        )
        bundle_list = list(bundles.scalars().all())

        # 1. Natural multi-unit necessity (30%)
        necessity = self._multi_unit_necessity(bundle_list, product)
        components["multi_unit_necessity"] = {
            "raw": necessity,
            "weight": weights["multi_unit_necessity"],
            "description": "Functional reason for purchasing multiple units",
        }

        # 2. Functional benefit (25%)
        benefit = self._functional_benefit(bundle_list, product)
        components["functional_benefit"] = {
            "raw": benefit,
            "weight": weights["functional_benefit"],
            "description": "Clear functional advantage of having multiple units",
        }

        # 3. AOV fit (20%)
        aov = self._aov_fit(bundle_list, product)
        components["aov_fit"] = {
            "raw": aov,
            "weight": weights["aov_fit"],
            "description": "Plausibility of $30-$90 bundle order value",
        }

        # 4. Usage frequency (15%)
        frequency = self._usage_frequency(bundle_list, product)
        components["usage_frequency"] = {
            "raw": frequency,
            "weight": weights["usage_frequency"],
            "description": "Evidence of repeated or rotational usage pattern",
        }

        # 5. Decision simplicity (10%)
        simplicity = self._decision_simplicity(bundle_list, product)
        components["decision_simplicity"] = {
            "raw": simplicity,
            "weight": weights["decision_simplicity"],
            "description": "How simple the multi-unit purchasing decision is",
        }

        total = sum(components[k]["raw"] * components[k]["weight"] for k in components)
        total = min(100.0, max(0.0, total))

        return {"score": round(total, 2), "components": components}

    def _multi_unit_necessity(self, bundles: list[BundleOffer], product: Product) -> float:
        """Score based on natural reasons for multiple units."""
        if not bundles:
            return 0.0

        natural_count = sum(1 for b in bundles if b.is_natural_bundle)
        if natural_count == 0:
            # Check mechanism types for inherently natural ones
            natural_mechanisms = {
                BundleMechanism.DAILY_ROTATION,
                BundleMechanism.MULTIPLE_LOCATIONS,
                BundleMechanism.FREQUENT_USAGE,
                BundleMechanism.MULTI_PERSON_HOUSEHOLD,
            }
            mechanism_match = sum(1 for b in bundles if b.bundle_mechanism in natural_mechanisms)
            if mechanism_match > 0:
                return 60.0
            return 20.0  # Bundle offered but no natural reason identified

        return min(100.0, 50 + natural_count * 15)

    def _functional_benefit(self, bundles: list[BundleOffer], product: Product) -> float:
        """Score based on clear functional benefit of multiple units."""
        if not bundles:
            return 0.0

        has_reasoning = any(b.natural_bundle_reasoning for b in bundles)
        has_evidence = any(b.mechanism_evidence for b in bundles)

        score = 30.0  # Base: bundles exist
        if has_reasoning:
            score += 35.0
        if has_evidence:
            score += 35.0
        return min(100.0, score)

    def _aov_fit(self, bundles: list[BundleOffer], product: Product) -> float:
        """Score based on whether bundle prices fit $30-$90 range."""
        if not bundles:
            # Try single-unit price
            price = product.min_price_usd or product.max_price_usd
            if price:
                # Check if 3-10 units would fit range
                for qty in [3, 5, 10]:
                    order = price * qty
                    if 30 <= order <= 90:
                        return 60.0
                return 20.0
            return 0.0

        fits = 0
        for b in bundles:
            eov = b.estimated_order_value_usd or (b.bundle_price_usd if b.bundle_price_usd else None)
            if eov is None and b.unit_price_usd:
                eov = b.unit_price_usd * b.quantity
            if eov and 30 <= eov <= 90:
                fits += 1

        if fits == 0:
            return 10.0
        return min(100.0, 40 + fits * 20)

    def _usage_frequency(self, bundles: list[BundleOffer], product: Product) -> float:
        """Score based on repeated use patterns."""
        high_freq_mechanisms = {
            BundleMechanism.DAILY_ROTATION,
            BundleMechanism.FREQUENT_USAGE,
            BundleMechanism.CONSUMABLE_REPLENISHMENT,
        }
        count = sum(1 for b in bundles if b.bundle_mechanism in high_freq_mechanisms)
        if count > 0:
            return min(100.0, 50 + count * 20)

        # Check product description for frequency signals
        desc = (product.description or "").lower()
        freq_keywords = ["daily", "everyday", "regular", "frequent", "weekly", "rotation"]
        matches = sum(1 for kw in freq_keywords if kw in desc)
        return min(100.0, matches * 20)

    def _decision_simplicity(self, bundles: list[BundleOffer], product: Product) -> float:
        """Score based on simplicity of purchasing decision."""
        if not bundles:
            return 30.0  # Unknown

        # Simple: uniform products (same thing, just more)
        quantities = [b.quantity for b in bundles]
        has_standard = any(q in [3, 5, 10] for q in quantities)

        score = 50.0
        if has_standard:
            score += 25.0

        # If all bundles are same mechanism, it's simpler
        mechanisms = set(b.bundle_mechanism for b in bundles)
        if len(mechanisms) == 1 and BundleMechanism.UNKNOWN not in mechanisms:
            score += 25.0

        return min(100.0, score)

    # ── Composite ────────────────────────────────────────────────────────

    def _compute_composite(self, emergence: dict, confidence: dict, bundle: dict) -> float:
        """Composite score combining all three dimensions."""
        e = emergence["score"]
        c = confidence["score"]
        b = bundle["score"]

        # Weighted combination: emergence most important, modulated by confidence
        # Products with zero confidence should score very low regardless
        if c < 5:
            return round(e * 0.1, 2)

        # Geometric-ish blend to penalize very low scores in any dimension
        raw = (e * 0.4 + b * 0.35 + c * 0.25)
        # Apply confidence as a multiplier (0.5 to 1.0 range)
        confidence_multiplier = 0.5 + (c / 200)
        composite = raw * confidence_multiplier

        return round(min(100.0, max(0.0, composite)), 2)

    # ── Batch Scoring ────────────────────────────────────────────────────

    async def score_all_products(self, score_date: Optional[str] = None) -> list[OpportunityScore]:
        """Score all products in the database."""
        if score_date is None:
            score_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        result = await self.db.execute(
            select(Product.id).where(Product.target_country == "US")
        )
        product_ids = [row[0] for row in result.all()]

        scores = []
        for pid in product_ids:
            try:
                score = await self.score_product(pid, score_date)
                scores.append(score)
            except Exception as e:
                logger.warning("Failed to score product %s: %s", pid, e)

        return scores

