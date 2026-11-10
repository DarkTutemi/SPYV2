"""
US WIN HUNTER — LLM Service Abstraction Layer

Provides structured LLM inference for:
- Bundle mechanism classification (e.g. daily rotation, multi-location, multi-household)
- Product pain synthesis
- Hypothesis generation

IMPORTANT:
- Deterministic heuristic fallbacks are used when API keys are not provided.
- AI inferences are ALWAYS tagged as EvidenceType.AI_INFERENCE.
- LLMs are NEVER used to calculate numerical scores directly.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

import httpx

from app.core.config import get_settings
from app.models.models import BundleMechanism

logger = logging.getLogger(__name__)


class LLMService:
    """Provider-agnostic LLM client with heuristic fallbacks."""

    def __init__(self):
        self.settings = get_settings()
        self.provider = self.settings.llm_provider.lower()
        self.api_key = self.settings.llm_api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = self.settings.llm_model

    async def classify_bundle_mechanism(
        self,
        product_name: str,
        description: str,
        observed_bundles: list[dict],
    ) -> dict[str, Any]:
        """
        Classify the natural bundle mechanism of a product and evaluate $30-$90 AOV fit.
        Returns:
            {
                "mechanism": BundleMechanism,
                "confidence": float (0-1),
                "is_natural": bool,
                "reasoning": str,
                "evidence_type": "ai_inference" | "unverified_hypothesis"
            }
        """
        # If API key is available and provider is google, call Gemini API
        if self.api_key and self.provider == "google":
            try:
                return await self._call_gemini_bundle_classification(
                    product_name, description, observed_bundles
                )
            except Exception as e:
                logger.warning("Gemini classification failed, falling back to heuristics: %s", e)

        # Fallback to rule-based deterministic heuristic
        return self._heuristic_bundle_classification(product_name, description, observed_bundles)

    # ── Rule-Based Deterministic Heuristic ───────────────────────────────

    def _heuristic_bundle_classification(
        self,
        product_name: str,
        description: str,
        observed_bundles: list[dict],
    ) -> dict[str, Any]:
        """Classify bundle mechanism using deterministic text analysis."""
        text = f"{product_name} {description}".lower()

        # Keywords mapping to BundleMechanism
        keywords = {
            BundleMechanism.DAILY_ROTATION: [
                "underwear", "boxer", "brief", "sock", "panty", "towel", "undershirt",
                "daily", "rotation", "wash", "wear daily", "everyday wear", "linens"
            ],
            BundleMechanism.MULTIPLE_LOCATIONS: [
                "charger", "cable", "organizer", "hook", "night light", "sensor",
                "car", "kitchen", "bedroom", "office", "desk", "multi-room",
                "every room", "each room", "wall mount", "door stop", "air freshener"
            ],
            BundleMechanism.FREQUENT_USAGE: [
                "sponge", "cleaning", "scrubber", "filter", "wipe", "cloth",
                "heavy use", "frequent", "wear out", "kitchen sink"
            ],
            BundleMechanism.MULTI_PERSON_HOUSEHOLD: [
                "family", "pack of", "household", "kids", "children", "guest",
                "multiple users", "his and hers", "couples"
            ],
            BundleMechanism.MULTI_PET: [
                "dog", "cat", "pet", "puppy", "kitten", "litter", "paw", "leash", "bowl"
            ],
            BundleMechanism.CONSUMABLE_REPLENISHMENT: [
                "refill", "cartridge", "replacement head", "battery", "tape",
                "consumable", "pad", "filter replacement"
            ],
            BundleMechanism.BACKUP_REPLACEMENT: [
                "spare", "backup", "lost easily", "replacement", "extra", "emergency"
            ],
            BundleMechanism.COMPLETE_COVERAGE: [
                "set", "complete kit", "all angles", "corners", "full set", "covers all"
            ],
        }

        matched_mechanisms = []
        for mech, terms in keywords.items():
            count = sum(1 for term in terms if re.search(r"\b" + re.escape(term) + r"\b", text))
            if count > 0:
                matched_mechanisms.append((mech, count))

        if matched_mechanisms:
            matched_mechanisms.sort(key=lambda x: x[1], reverse=True)
            best_mech, count = matched_mechanisms[0]
            confidence = min(0.9, 0.4 + count * 0.15)
            is_natural = best_mech in (
                BundleMechanism.DAILY_ROTATION,
                BundleMechanism.MULTIPLE_LOCATIONS,
                BundleMechanism.FREQUENT_USAGE,
                BundleMechanism.MULTI_PERSON_HOUSEHOLD,
                BundleMechanism.CONSUMABLE_REPLENISHMENT,
                BundleMechanism.MULTI_PET,
                BundleMechanism.COMPLETE_COVERAGE,
            )
            reasoning = (
                f"Heuristic pattern match: matched terms for {best_mech.value} "
                f"in product title/description. (Deterministic fallback)"
            )
            return {
                "mechanism": best_mech,
                "confidence": confidence,
                "is_natural": is_natural,
                "reasoning": reasoning,
                "evidence_type": "ai_inference",
            }

        return {
            "mechanism": BundleMechanism.UNKNOWN,
            "confidence": 0.2,
            "is_natural": False,
            "reasoning": "No strong functional multi-unit reason identified via keyword heuristics.",
            "evidence_type": "unverified_hypothesis",
        }

    # ── Gemini API Integration ───────────────────────────────────────────

    async def _call_gemini_bundle_classification(
        self,
        product_name: str,
        description: str,
        observed_bundles: list[dict],
    ) -> dict[str, Any]:
        """Call Google Gemini API with JSON output mode."""
        prompt = f"""
You are an expert US E-Commerce Product Research Analyst.
Analyze the following physical consumer product and classify its natural bundle mechanism for the US market.

Target achievable Average Order Value (AOV): $30–$90 USD.
Preferred multi-unit quantities: 3, 5, or 10 units.

Product Name: {product_name}
Description: {description}
Observed Bundles: {json.dumps(observed_bundles)}

Mechanisms to choose from:
- daily_rotation (e.g. underwear, socks, towels needing frequent laundering/rotation)
- multiple_locations (e.g. chargers, night lights, organizers used in car/bedroom/office)
- frequent_usage (e.g. sponges, cleaning cloths worn down quickly)
- consumable_replenishment (e.g. filters, refills)
- complete_coverage (e.g. corner guards, full protection sets)
- multi_person_household (e.g. items used simultaneously by family members)
- multi_pet (e.g. multiple dogs or cats in household)
- backup_replacement (e.g. items frequently misplaced or broken)
- unknown (no genuine functional reason for buying multiples)

Return valid JSON with exactly these keys:
{{
    "mechanism": "string",
    "is_natural": true/false,
    "confidence": float between 0.0 and 1.0,
    "reasoning": "brief explanation distinguishing natural multi-unit necessity from forced discounts"
}}
"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"},
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(raw_text)

            mech_str = parsed.get("mechanism", "unknown").lower()
            try:
                mech = BundleMechanism(mech_str)
            except ValueError:
                mech = BundleMechanism.UNKNOWN

            return {
                "mechanism": mech,
                "confidence": float(parsed.get("confidence", 0.7)),
                "is_natural": bool(parsed.get("is_natural", False)),
                "reasoning": str(parsed.get("reasoning", "")),
                "evidence_type": "ai_inference",
            }


# Singleton helper
_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
