"""
US WIN HUNTER — Engine F: Bundle Intelligence Engine

Analyzes whether physical consumer products have genuine reasons for multi-unit purchases.
Distinguishes natural bundle demand from artificially forced discounts.

Evaluates:
- Bundle mechanism (daily rotation, multiple locations, frequent usage, etc.)
- Bundle quantities (3, 5, 10 units preferred)
- Target AOV feasibility ($30–$90 USD)
- Bundles offered vs. promoted vs. purchased (evidence distinction)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.landing_page import LandingPageExtractor
from app.models.models import (
    BundleMechanism,
    BundleOffer,
    ConfidenceLevel,
    EvidenceType,
    Product,
)
from app.services.llm_service import get_llm_service

logger = logging.getLogger(__name__)


class BundleIntelligenceEngine:
    """Engine F: bundle mechanism evaluation, offer extraction, and $30-$90 AOV modeling."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.extractor = LandingPageExtractor()
        self.llm = get_llm_service()

    async def analyze_product_bundles(
        self,
        product_id: str,
        page_content: Optional[str] = None,
        source_url: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Run full bundle intelligence on a product:
        1. Extract observable bundles from landing page if provided
        2. Classify natural bundle mechanism
        3. Model $30-$90 AOV scenarios for 3, 5, 10 units
        4. Update bundle records in database
        """
        product = await self.db.get(Product, product_id)
        if not product:
            raise ValueError(f"Product not found: {product_id}")

        # 1. Extract offers from content if provided
        extracted_offers = []
        if page_content:
            extracted_offers = self.extractor.extract_offers(page_content, source_url)
            for offer_dict in extracted_offers:
                await self._upsert_bundle_offer(product_id, offer_dict)

        # 2. Get all bundle offers currently stored for this product
        result = await self.db.execute(
            select(BundleOffer).where(BundleOffer.product_id == product_id)
        )
        current_bundles = list(result.scalars().all())

        # 3. Classify bundle mechanism via LLM/Heuristic service
        bundles_data = [
            {"quantity": b.quantity, "bundle_price": b.bundle_price_usd}
            for b in current_bundles
        ]
        classification = await self.llm.classify_bundle_mechanism(
            product_name=product.name,
            description=product.description or "",
            observed_bundles=bundles_data,
        )

        # Update bundles with classification if not manually reviewed
        for b in current_bundles:
            if b.bundle_mechanism == BundleMechanism.UNKNOWN:
                b.bundle_mechanism = classification["mechanism"]
                b.is_natural_bundle = classification["is_natural"]
                b.natural_bundle_reasoning = classification["reasoning"]
                b.mechanism_evidence = (
                    f"Classified via {classification['evidence_type']}: "
                    f"confidence {classification['confidence']:.2f}"
                )

        # 4. Compute AOV Scenarios for preferred quantities (3, 5, 10)
        aov_scenarios = self._compute_aov_scenarios(product, current_bundles)

        await self.db.flush()

        return {
            "product_id": product_id,
            "product_name": product.name,
            "bundle_mechanism": classification["mechanism"].value,
            "is_natural_bundle": classification["is_natural"],
            "classification_confidence": classification["confidence"],
            "reasoning": classification["reasoning"],
            "bundle_count": len(current_bundles),
            "bundles": [
                {
                    "quantity": b.quantity,
                    "bundle_price_usd": b.bundle_price_usd,
                    "unit_price_usd": b.unit_price_usd,
                    "discount_claim": b.discount_claim,
                    "eov_usd": b.estimated_order_value_usd,
                    "status": b.bundle_status,
                    "is_natural": b.is_natural_bundle,
                }
                for b in current_bundles
            ],
            "aov_scenarios": aov_scenarios,
        }

    def _compute_aov_scenarios(
        self, product: Product, bundles: list[BundleOffer]
    ) -> list[dict[str, Any]]:
        """
        Model order value scenarios for preferred bundles (3, 5, 10 units)
        and determine whether they fall within the $30-$90 target AOV window.
        """
        # Determine base unit price
        base_price = product.min_price_usd or product.max_price_usd
        if not base_price:
            # Check if any bundle gives unit price
            for b in bundles:
                if b.unit_price_usd:
                    base_price = b.unit_price_usd
                    break

        scenarios = []
        target_quantities = [3, 5, 10]

        for qty in target_quantities:
            # Check if an explicit bundle already exists for this qty
            matching_bundle = next((b for b in bundles if b.quantity == qty), None)

            if matching_bundle and matching_bundle.estimated_order_value_usd:
                eov = matching_bundle.estimated_order_value_usd
                is_within_target = 30.0 <= eov <= 90.0
                scenarios.append({
                    "quantity": qty,
                    "estimated_order_value": eov,
                    "is_within_target_aov": is_within_target,
                    "source": "observed_bundle_offer",
                    "status": matching_bundle.bundle_status,
                })
            elif base_price:
                # Modeled bundle with tiered discount
                discount = 0.15 if qty == 3 else 0.25 if qty == 5 else 0.35
                modeled_eov = round(base_price * qty * (1 - discount), 2)
                is_within_target = 30.0 <= modeled_eov <= 90.0
                scenarios.append({
                    "quantity": qty,
                    "estimated_order_value": modeled_eov,
                    "is_within_target_aov": is_within_target,
                    "source": f"modeled_scenario ({int(discount*100)}% discount)",
                    "status": "hypothetical",
                })
            else:
                scenarios.append({
                    "quantity": qty,
                    "estimated_order_value": None,
                    "is_within_target_aov": False,
                    "source": "missing_price_data",
                    "status": "unknown",
                })

        return scenarios

    async def _upsert_bundle_offer(self, product_id: str, offer_dict: dict[str, Any]) -> BundleOffer:
        """Upsert a bundle offer for a product."""
        existing = await self.db.execute(
            select(BundleOffer).where(
                BundleOffer.product_id == product_id,
                BundleOffer.quantity == offer_dict["quantity"],
            )
        )
        offer = existing.scalar_one_or_none()

        if offer is None:
            offer = BundleOffer(product_id=product_id, quantity=offer_dict["quantity"])
            self.db.add(offer)

        offer.bundle_price_usd = offer_dict.get("bundle_price_usd")
        offer.unit_price_usd = offer_dict.get("unit_price_usd")
        offer.discount_claim = offer_dict.get("discount_claim")
        offer.estimated_order_value_usd = offer_dict.get("estimated_order_value_usd")
        offer.source_url = offer_dict.get("source_url")
        offer.bundle_status = offer_dict.get("bundle_status", "offered")
        offer.evidence_type = offer_dict.get("evidence_type", EvidenceType.OBSERVED_FACT)

        return offer
