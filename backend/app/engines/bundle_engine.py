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

        # Distinguish consumable refills vs durable hardware tools from product identity
        title_lower = product.name.lower()
        desc_lower = (product.description or "").lower()
        url_lower = (product.source_url or "").lower()
        text_for_hints = f"{title_lower} {desc_lower} {url_lower}"

        is_refill = any(
            kw in title_lower
            for kw in ["refill", "replacement", "cloth", "pad", "head", "sponge", "wipe", "cartridge", "strands"]
        )
        is_tool = any(
            kw in title_lower
            for kw in ["flat mop", "squeeze mop", "cleaning mop", "mop –", "mop -"]
        ) and not is_refill

        is_consumable = is_refill or (
            any(kw in desc_lower for kw in ["refill", "replacement", "cloth", "pad", "sponge", "wipe"]) and not is_tool
        )

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

        # Override/Refine based on verified physical product type
        if is_tool:
            classification["is_natural"] = False
            classification["mechanism"] = BundleMechanism.UNKNOWN
            classification["reasoning"] = (
                "Hardware tool / durable good. Typical households only need 1 unit per home; "
                "multi-unit offers represent seller-driven bulk discounts rather than natural consumable rotation."
            )
        elif is_consumable:
            classification["is_natural"] = True
            if "rotation" in text_for_hints or "washable" in text_for_hints or "cloth" in text_for_hints:
                classification["mechanism"] = BundleMechanism.DAILY_ROTATION
                classification["reasoning"] = (
                    "Washable / reusable cleaning refills with natural room-by-room rotation (kitchen, bathroom) "
                    "and laundry replacement necessity. Customers naturally purchase in 3, 5, or 10-packs."
                )
            else:
                classification["mechanism"] = BundleMechanism.CONSUMABLE_REPLENISHMENT
                classification["reasoning"] = (
                    "High-wear consumable replacement heads requiring regular replacement every 1-2 months. "
                    "Natural multipack demand for multi-room coverage and planned refills."
                )

        # Check for explicit observed packs in URL or text (e.g. 3-pack)
        observed_qty = None
        if any(w in text_for_hints for w in ["3-pack", "3 pack", "pack of 3", "3pack", "3-piece", "3 piece"]):
            observed_qty = 3
        elif any(w in text_for_hints for w in ["5-pack", "5 pack", "pack of 5", "5pack", "5-piece", "5 piece"]):
            observed_qty = 5
        elif any(w in text_for_hints for w in ["10-pack", "10 pack", "pack of 10", "10pack", "10-piece", "10 piece"]):
            observed_qty = 10

        # Update product primary_bundle_qty: strictly observed, else None (Unknown)
        product.primary_bundle_qty = observed_qty

        # If current_bundles is empty, create standard evaluation bundles for 3, 5, 10 units
        if not current_bundles:
            for qty in [3, 5, 10]:
                is_obs = (qty == observed_qty)
                status = "promoted" if is_obs else "modeled_scenario"

                # Estimated AOV modeling based on physical category
                est_unit = 7.0 if is_consumable else (24.0 if is_tool else 10.0)
                tier_discount = 0.10 if qty == 3 else (0.20 if qty == 5 else 0.30)
                eov = round(est_unit * qty * (1 - tier_discount), 2)

                # Only assign price if observed from product; otherwise leave None (missing observed price)
                obs_price = (product.min_price_usd * qty * (1 - tier_discount)) if (product.min_price_usd and is_obs) else None
                obs_unit = product.min_price_usd if (product.min_price_usd and is_obs) else None

                offer = BundleOffer(
                    product_id=product_id,
                    quantity=qty,
                    bundle_price_usd=obs_price,
                    unit_price_usd=obs_unit,
                    estimated_order_value_usd=eov,
                    bundle_mechanism=classification["mechanism"],
                    bundle_status=status,
                    is_natural_bundle=classification["is_natural"],
                    natural_bundle_reasoning=classification["reasoning"],
                    mechanism_evidence=f"Modeled evaluation scenario for {qty}-pack under {classification['mechanism'].value}",
                    source_url=product.source_url,
                )
                self.db.add(offer)
                current_bundles.append(offer)

        # Update bundles with classification if not manually reviewed
        for b in current_bundles:
            if b.bundle_mechanism == BundleMechanism.UNKNOWN or is_consumable or is_tool:
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

