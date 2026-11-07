"""
US WIN HUNTER — Landing Page Bundle Extractor

Extracts pricing, multi-unit quantity tiers, and discount offers from landing page content.
Computes Estimated Order Value (EOV) and evaluates whether offers fall into target $30–$90 AOV range.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from app.models.models import BundleMechanism, EvidenceType

logger = logging.getLogger(__name__)


class LandingPageExtractor:
    """Parses landing page text and HTML for bundle offers and pricing."""

    def extract_offers(
        self,
        html_or_text: str,
        source_url: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Extract observable bundle offers from landing page content.
        Returns a list of dicts suitable for creating BundleOffer records.
        """
        offers: list[dict[str, Any]] = []

        # Clean text
        text = self._strip_tags(html_or_text)

        # 1. Look for explicit multi-pack patterns:
        # e.g. "Buy 3 for $45", "Pack of 5 - $59.99", "3x / 3 Units: $39.00", "Buy 10 Get 40% Off"
        patterns = [
            # Pattern: "Buy X for $Y" or "X Pack for $Y" or "X Units: $Y"
            r"(?:buy\s+|pack\s+of\s+|set\s+of\s+|)(\d+)\s*(?:pack|units?|pieces?|pcs|x)?\s*(?:for|:|-|@)?\s*\$\s*([\d,]+(?:\.\d{2})?)",
            # Pattern: "$Y for X pack"
            r"\$\s*([\d,]+(?:\.\d{2})?)\s*(?:for|\/)\s*(\d+)\s*(?:pack|units?|pieces?|pcs|x)",
            # Pattern: "Buy X Get Y"
            r"buy\s+(\d+)\s+get\s+(\d+)\s*(?:free)?",
        ]

        seen_quantities = set()

        # Try standard quantity patterns
        for match in re.finditer(patterns[0], text, re.IGNORECASE):
            try:
                qty = int(match.group(1))
                price = float(match.group(2).replace(",", ""))
                if qty > 1 and qty <= 50 and price > 0 and qty not in seen_quantities:
                    seen_quantities.add(qty)
                    offers.append(self._build_bundle_dict(qty, price, source_url, text))
            except (ValueError, IndexError):
                continue

        # Try reversed pattern: "$Y for X"
        for match in re.finditer(patterns[1], text, re.IGNORECASE):
            try:
                price = float(match.group(1).replace(",", ""))
                qty = int(match.group(2))
                if qty > 1 and qty <= 50 and price > 0 and qty not in seen_quantities:
                    seen_quantities.add(qty)
                    offers.append(self._build_bundle_dict(qty, price, source_url, text))
            except (ValueError, IndexError):
                continue

        # If standard preferred quantities (3, 5, 10) are mentioned with single price:
        if not offers:
            single_price = self._extract_single_price(text)
            if single_price:
                # Check if text mentions bundles without explicit total prices
                for target_qty in [3, 5, 10]:
                    if re.search(rf"\b{target_qty}\s*(?:pack|units?|pcs|pieces)\b", text, re.IGNORECASE):
                        # Estimated bundle price with typical dropship tiered discounts
                        discount = 0.15 if target_qty == 3 else 0.25 if target_qty == 5 else 0.40
                        est_price = round(single_price * target_qty * (1 - discount), 2)
                        offers.append({
                            "quantity": target_qty,
                            "bundle_price_usd": est_price,
                            "unit_price_usd": round(est_price / target_qty, 2),
                            "discount_claim": f"Estimated ~{int(discount * 100)}% bundle discount",
                            "estimated_order_value_usd": est_price,
                            "source_url": source_url,
                            "bundle_status": "promoted",
                            "is_natural_bundle": None,
                            "evidence_type": EvidenceType.DERIVED_METRIC,
                        })

        return offers

    def _build_bundle_dict(
        self,
        quantity: int,
        bundle_price: float,
        source_url: Optional[str],
        full_text: str,
    ) -> dict[str, Any]:
        unit_price = round(bundle_price / quantity, 2)

        # Check for discount claim nearby
        discount_match = re.search(
            rf"(?:save|discount|off)\s*(\d+%\s*|\$\s*[\d.]+)", full_text, re.IGNORECASE
        )
        discount_claim = discount_match.group(0).strip() if discount_match else None

        return {
            "quantity": quantity,
            "bundle_price_usd": bundle_price,
            "unit_price_usd": unit_price,
            "discount_claim": discount_claim,
            "estimated_order_value_usd": bundle_price,
            "source_url": source_url,
            "bundle_status": "offered",
            "is_natural_bundle": None,
            "evidence_type": EvidenceType.OBSERVED_FACT,
        }

    def _extract_single_price(self, text: str) -> Optional[float]:
        """Extract primary observable price from text."""
        match = re.search(r"\$\s*([\d,]+(?:\.\d{2})?)", text)
        if match:
            try:
                val = float(match.group(1).replace(",", ""))
                if 1.0 <= val <= 1000.0:
                    return val
            except ValueError:
                pass
        return None

    def _strip_tags(self, html: str) -> str:
        """Strip HTML tags while preserving spaces."""
        text = re.sub(r"<[^>]+>", " ", html)
        return " ".join(text.split())

