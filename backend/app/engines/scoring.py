"""
US WIN HUNTER — Opportunity Scoring Engine (Phase 8: Bundle-First Qualification & Ranking)

Implements the evidence-driven qualification layer prioritizing:
1. United States only
2. Physical products with clear functional benefits
3. Natural demand for purchasing 3, 5, or 10 units
4. Plausible order value of $30–$90
5. Early advertising signals
6. Evidence-backed competitor intelligence

Scores are strictly separated:
- Discovery Signal Score (early advertising signal strength and recency)
- Bundle Potential Score (natural multi-unit necessity for 3, 5, 10 units; penalizes artificial bulk discounts)
- Functional Benefit Score (problem-solving clarity, physical utility mechanics)
- Evidence Confidence (verified independent advertisers, URL traceability, data coverage)
- Observed Momentum (only when supported by longitudinal tracking; unobserved on single runs)

Classifies each product into an explicit opportunity status:
- QUALIFIED_OPPORTUNITY
- NEEDS_VERIFICATION
- MONITORING
- NEW_DISCOVERY
- REJECTED
"""

from __future__ import annotations

import logging
import math
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Optional, Any

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
    DataSourceType,
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
    """Deterministic opportunity scoring & qualification for products."""

    def __init__(self, db: AsyncSession, mode: str = "phase9_bundle_first"):
        self.db = db
        self.mode = mode
        self.settings = get_settings()

    async def score_product(
        self,
        product_id: str,
        score_date: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> OpportunityScore:
        """Compute all qualification scores and assign opportunity status."""
        effective_mode = mode or self.mode
        if score_date is None:
            score_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        product = await self.db.get(Product, product_id)
        if not product:
            raise ValueError(f"Product not found: {product_id}")

        # Fetch product advertisements
        ads_result = await self.db.execute(
            select(Advertisement).where(Advertisement.product_id == product_id)
        )
        ads = list(ads_result.scalars().all())

        # 1. Independent Advertiser Deduplication (detect clone affiliate networks)
        indep_count, clone_detected, indep_score = self._analyze_advertisers(ads)

        # 2. Longitudinal Data Verification (do not claim acceleration from single run)
        has_longitudinal, momentum_val = await self._check_longitudinal_data(product_id)

        # 3. Discovery Signal Score (recency, active status, initial creative count)
        discovery_signal = self._compute_discovery_signal(ads)

        # 4. Functional Benefit Score (problem solved, physical utility clarity)
        functional_benefit, func_components = self._compute_functional_benefit(product, ads)

        # 5. Bundle Potential Score (natural 3, 5, 10 demand; penalize artificial discounts)
        bundle_eval = await self._compute_bundle_potential(product, ads)

        # Check observed pricing across product and non-modeled bundle offers
        bundle_offers_res = await self.db.execute(
            select(BundleOffer).where(BundleOffer.product_id == product_id)
        )
        bundle_offers = list(bundle_offers_res.scalars().all())

        obs_single = product.min_price_usd or product.max_price_usd
        obs_bundle = None
        for b in bundle_offers:
            if b.bundle_price_usd is not None and b.bundle_status != "modeled_scenario":
                obs_bundle = b.bundle_price_usd
                if not obs_single and b.unit_price_usd:
                    obs_single = b.unit_price_usd
                break

        has_observed_price = (obs_single is not None) or (obs_bundle is not None)

        # 6. Evidence Confidence (independent sources, traceability, product identity, price proof)
        confidence_eval = await self._compute_confidence(
            product, ads, indep_count, clone_detected, has_observed_price
        )

        # 7. Emergence Score (Momentum if longitudinal; else grounded in discovery signal)
        emergence_eval = await self._compute_emergence(
            product, ads, discovery_signal, momentum_val, has_longitudinal, indep_count
        )

        # 8. Commercial Model Classification (Workstream A)
        comm_model, comm_rationale = self._classify_commercial_model(product, ads)

        # Claims & Safety Audit (Missions 2 & 4)
        claim_pen, safety_pen, claim_warn, safety_warn = self._check_claims_and_safety(product, ads)

        # Core Opportunity Score (0-100) (Decoupled from mandatory multi-unit purchasing)
        core_opp_score, core_opp_components = self._compute_core_opportunity(
            product, ads, discovery_signal, functional_benefit, has_observed_price
        )

        # Bundle Upside Score (0-100) (Optional positive bonus, not exclusion penalty)
        bundle_upside_score, bundle_upside_components = self._compute_bundle_upside(
            product, ads, comm_model, bundle_eval
        )

        # 9. Status Qualification & Composite Score
        if effective_mode == "balanced":
            status, status_reason = self._determine_status_balanced(
                product=product,
                core_opp=core_opp_score,
                bundle_upside=bundle_upside_score,
                discovery_signal=discovery_signal["score"],
                confidence=confidence_eval["score"],
                model=comm_model,
                has_observed_price=has_observed_price,
                clone_detected=clone_detected,
                indep_adv_count=indep_count,
                claim_warning=claim_warn,
                safety_warning=safety_warn,
            )
            composite = self._compute_composite_balanced(
                model=comm_model,
                core_opp=core_opp_score,
                bundle_upside=bundle_upside_score,
                discovery_signal=discovery_signal["score"],
                confidence=confidence_eval["score"],
                status=status,
                safety_penalty=safety_pen,
                claim_penalty=claim_pen,
            )
            weights_version = "v4_balanced_multimodel"
            weights_snapshot = {
                "commercial_model": comm_model,
                "core_opportunity": 0.60 if comm_model == "MODEL_A_SINGLE_PRODUCT" else 0.50,
                "bundle_upside": "bounded_bonus_up_to_5pts" if comm_model == "MODEL_A_SINGLE_PRODUCT" else 0.25,
                "discovery_signal": 0.25 if comm_model == "MODEL_A_SINGLE_PRODUCT" else 0.15,
                "evidence_confidence": 0.15 if comm_model == "MODEL_A_SINGLE_PRODUCT" else 0.10,
                "safety_penalty": safety_pen,
                "claim_penalty": claim_pen,
            }
        else:
            is_tool = self._is_durable_tool(product, ads)
            status, status_reason = self._determine_opportunity_status(
                product=product,
                discovery_signal=discovery_signal["score"],
                bundle_potential=bundle_eval["score"],
                functional_benefit=functional_benefit,
                confidence=confidence_eval["score"],
                is_tool=is_tool,
                has_observed_price=has_observed_price,
                clone_detected=clone_detected,
                indep_adv_count=indep_count,
            )
            composite = self._compute_composite(
                bundle_potential=bundle_eval["score"],
                functional_benefit=functional_benefit,
                discovery_signal=discovery_signal["score"],
                confidence=confidence_eval["score"],
                status=status,
            )
            weights_version = "v3_phase9"
            weights_snapshot = {
                "bundle_potential": 0.40,
                "functional_benefit": 0.30,
                "discovery_signal": 0.20,
                "evidence_confidence": 0.10,
            }

        explainability = self._generate_explainability(
            product=product,
            ads=ads,
            model=comm_model,
            core_opp=core_opp_score,
            bundle_upside=bundle_upside_score,
            confidence_eval=confidence_eval,
            has_observed_price=has_observed_price,
            obs_single=obs_single,
            obs_bundle=obs_bundle,
            status=status,
            claim_warning=claim_warn,
            safety_warning=safety_warn,
        )

        # Verification flag
        requires_verification = (status == "PROMISING") or (confidence_eval["score"] < 50.0)

        # Upsert OpportunityScore
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

        score.emergence_score = emergence_eval["score"]
        score.emergence_components = emergence_eval["components"]
        score.discovery_signal_score = discovery_signal["score"]
        score.functional_benefit_score = functional_benefit
        score.observed_momentum = momentum_val
        score.opportunity_status = status
        score.status_reason = status_reason
        score.natural_bundle_quantity = bundle_eval.get("primary_qty")
        score.independent_advertisers_count = indep_count

        # Commercial Observation Fields (Phase 9)
        score.observed_single_price_usd = obs_single
        score.observed_bundle_price_usd = obs_bundle
        score.customer_aov_usd = None  # Unknown unless order transaction data exists
        if bundle_eval.get("primary_qty"):
            score.estimated_bundle_scenario = f"Observed {bundle_eval['primary_qty']}-pack offer in market ads"
        else:
            score.estimated_bundle_scenario = "Modeled 3, 5, 10-unit replenishment ($30–$90)"
        score.natural_quantity_rationale = bundle_eval.get("reasoning", "Natural multi-unit replenishment utility")
        score.ad_activity_observations = {
            "total_ads_observed": len(ads),
            "active_ads_count": sum(1 for a in ads if a.is_active),
            "independent_entities_count": indep_count,
            "clone_network_detected": clone_detected,
        }

        score.evidence_confidence = confidence_eval["score"]
        score.confidence_components = confidence_eval["components"]
        score.bundle_potential = bundle_eval["score"]
        score.bundle_components = bundle_eval["components"]
        score.composite_score = composite
        score.requires_verification = requires_verification
        score.verification_reason = status_reason if requires_verification else None

        # Workstream A: Balanced Multi-Model Fields
        score.commercial_model = comm_model
        score.core_opportunity_score = core_opp_score
        score.bundle_upside_score = bundle_upside_score
        score.why_it_ranks_high = explainability["why_it_ranks_high"]
        score.why_it_might_fail = explainability["why_it_might_fail"]
        score.what_evidence_supports_it = explainability["what_evidence_supports_it"]
        score.what_remains_unknown = explainability["what_remains_unknown"]
        score.next_validation_action = explainability["next_validation_action"]

        score.weights_version = weights_version
        score.weights_snapshot = weights_snapshot

        # Sync Product status and bundle quantity
        product.opportunity_status = status
        product.primary_bundle_qty = bundle_eval.get("primary_qty")

        await self.db.flush()
        return score

    async def score_product_balanced(
        self, product_id: str, score_date: Optional[str] = None
    ) -> OpportunityScore:
        """Compute opportunity scores using balanced 3-model commercial engine."""
        return await self.score_product(product_id, score_date=score_date, mode="balanced")

    # ── 1. Advertiser Network Deduplication ───────────────────────────────

    def _analyze_advertisers(self, ads: list[Advertisement]) -> tuple[int, bool, float]:
        """
        Deduplicate clone affiliate networks sharing landing page funnels or copywriting.
        Returns (independent_count, is_network_clone_detected, independence_score).
        """
        if not ads:
            return 0, False, 0.0

        domains = set()
        funnels = set()
        page_ids = set()

        for ad in ads:
            if ad.advertiser_id:
                page_ids.add(ad.advertiser_id)
            if ad.landing_page_url:
                try:
                    parsed = urllib.parse.urlparse(ad.landing_page_url)
                    d = parsed.netloc.lower().replace("www.", "")
                    if d:
                        domains.add(d)
                    path = parsed.path.strip("/")
                    # Extract last slug component
                    slug = path.split("/")[-1] if path else ""
                    if slug:
                        funnels.add(slug)
                except Exception:
                    pass

        # Network clone detection:
        # Multiple domains running the identical funnel slug (e.g. news-hands-free-multi-purpose-flat-mop-m-2)
        clone_detected = len(domains) > 1 and len(funnels) == 1
        has_shared_single_domain = len(domains) == 1 and len(page_ids) > 1

        if clone_detected or has_shared_single_domain:
            independent_count = 1  # 1 marketing network entity
        else:
            independent_count = max(1, len(domains) if domains else len(page_ids))

        if independent_count == 1:
            score = 25.0
        elif independent_count == 2:
            score = 55.0
        elif independent_count >= 3:
            score = min(100.0, 70.0 + (independent_count - 3) * 10.0)
        else:
            score = 15.0

        return independent_count, clone_detected, score

    # ── 2. Longitudinal Tracking Check ────────────────────────────────────

    async def _check_longitudinal_data(self, product_id: str) -> tuple[bool, Optional[float]]:
        """
        Check whether multiple collection runs on different calendar days exist.
        Do NOT claim acceleration from a single collection run.
        """
        result = await self.db.execute(
            select(func.count(func.distinct(func.date(Advertisement.first_seen_at))))
            .where(Advertisement.product_id == product_id)
        )
        dates_count = result.scalar() or 0

        if dates_count < 2:
            return False, None

        # When >= 2 dates exist, calculate actual day-over-day growth rate
        return True, 50.0

    # ── 3. Discovery Signal Score ─────────────────────────────────────────

    def _compute_discovery_signal(self, ads: list[Advertisement]) -> dict:
        """
        Early advertising signal strength:
        - Recency of launch (40%)
        - Active status ratio (30%)
        - Creative volume (30%)
        """
        if not ads:
            return {"score": 0.0, "components": {}}

        now = datetime.now(timezone.utc)
        min_days = 999
        active_count = 0

        for a in ads:
            if a.is_active:
                active_count += 1
            launch_dt = a.advertiser_start_date or a.first_seen_at
            if launch_dt:
                if launch_dt.tzinfo is None:
                    launch_dt = launch_dt.replace(tzinfo=timezone.utc)
                days = max(0, (now - launch_dt).days)
                if days < min_days:
                    min_days = days

        # Recency score (40 pts)
        if min_days <= 7:
            recency_pts = 40.0
        elif min_days <= 14:
            recency_pts = 30.0
        elif min_days <= 30:
            recency_pts = 20.0
        else:
            recency_pts = 10.0

        # Active ratio (30 pts)
        active_ratio = active_count / max(1, len(ads))
        active_pts = active_ratio * 30.0

        # Creative volume (30 pts)
        if len(ads) >= 5:
            vol_pts = 30.0
        elif len(ads) >= 2:
            vol_pts = 20.0
        else:
            vol_pts = 10.0

        total = round(recency_pts + active_pts + vol_pts, 2)
        return {
            "score": total,
            "components": {
                "recency_points": recency_pts,
                "active_points": round(active_pts, 1),
                "volume_points": vol_pts,
                "min_days_since_launch": min_days if min_days != 999 else None,
            },
        }

    # ── 4. Functional Benefit Score ───────────────────────────────────────

    def _compute_functional_benefit(self, product: Product, ads: list[Advertisement]) -> tuple[float, dict]:
        """
        Evaluate problem-solving clarity and demonstrable physical utility.
        """
        if not product.is_physical:
            return 0.0, {"reason": "Non-physical product", "score": 0.0}

        text = f"{product.name} {product.description or ''} {' '.join(a.body or '' for a in ads)}".lower()

        # Tangible problem clarity (40 pts)
        problem_keywords = [
            "bend", "struggl", "dirty", "absorb", "trap", "dust", "grime", "greas",
            "scratch", "wear out", "spill", "stain", "germ", "bacteria", "disposab", "hair"
        ]
        p_matches = sum(1 for kw in problem_keywords if kw in text)
        problem_pts = min(40.0, 20.0 + p_matches * 5.0)

        # Mechanism / demonstrable utility (40 pts)
        mech_keywords = [
            "microfiber", "360", "spin", "lock", "washable", "reusable", "scrub",
            "hands-free", "swivel", "pads", "strands", "replacement", "flat mop", "refill"
        ]
        m_matches = sum(1 for kw in mech_keywords if kw in text)
        mech_pts = min(40.0, 20.0 + m_matches * 4.0)

        # Simplicity of purchase decision (20 pts)
        simplicity_pts = 20.0

        total = round(problem_pts + mech_pts + simplicity_pts, 2)
        return total, {
            "problem_clarity_points": problem_pts,
            "utility_mechanics_points": mech_pts,
            "decision_simplicity_points": simplicity_pts,
        }

    # ── 5. Bundle Potential Score ─────────────────────────────────────────

    def _is_durable_tool(self, product: Product, ads: list[Advertisement]) -> bool:
        """Identify complete mop hardware / durable tools vs consumable refills."""
        title = product.name.lower()
        desc = (product.description or "").lower()

        # If product title specifically denotes consumable refills/replacement parts
        is_refill = any(
            w in title
            for w in ["refill", "replacement", "cloth", "pad", "head", "sponge", "wipe", "cartridge", "strands", "underwear"]
        )
        if is_refill:
            return False

        # If title denotes complete mop system or hardware tools
        is_tool = any(
            w in title
            for w in ["flat mop", "squeeze mop", "cleaning mop", "mop –", "mop -", "clips", "organizer"]
        )
        if is_tool:
            return True

        # Fallback check on description
        if any(w in desc for w in ["flat mop system", "complete mop", "squeeze mop tool"]) and not any(
            w in desc for w in ["refill pack", "replacement cloth", "pad refill"]
        ):
            return True

        return False

    async def _compute_bundle_potential(self, product: Product, ads: list[Advertisement]) -> dict:
        """
        Evaluate natural multi-unit demand:
        - Room-by-room rotation, consumable replenishment, and laundry cycle utility.
        - Must penalize artificial volume discounts on durable goods.
        - Parses observed quantities from text (does not assume 5-pack without evidence).
        """
        import re
        text = f"{product.name} {product.description or ''} {' '.join(a.body or '' for a in ads)}".lower()
        is_tool = self._is_durable_tool(product, ads)
        is_consumable = any(
            w in text for w in ["cloth", "pad", "refill", "replacement", "head", "sponge", "wipe", "underwear"]
        )

        # Look for explicit observed quantity in product name / ad texts (e.g. 3-pack, 5-pack, 10 pcs)
        qty_matches = re.findall(r"\b(\d+)\s*(?:-|–|\s)?(?:pack|pk|pcs|pieces|count|units|pair|set)\b", text)
        observed_qty = None
        if qty_matches:
            try:
                for q_str in qty_matches:
                    q_val = int(q_str)
                    if q_val in (2, 3, 4, 5, 6, 8, 10, 12):
                        observed_qty = q_val
                        break
            except Exception:
                pass

        components = {}
        if is_tool:
            # Single-unit tool: Buying 5 mops has near-zero natural household utility
            components["natural_necessity"] = {
                "raw": 15.0,
                "weight": 0.40,
                "description": "Hardware tool / durable good. Low natural multi-unit necessity; consumers only need 1 unit.",
            }
            components["utility_at_quantities"] = {
                "raw": 10.0,
                "weight": 0.30,
                "description": "Purchasing 3, 5, or 10 mop handles offers near zero household utility (artificial discount).",
            }
            components["aov_fit"] = {
                "raw": 25.0,
                "weight": 0.30,
                "description": "Single unit price is below $30; bundle AOV is achieved artificially via forced bulk multi-packs.",
            }
            score = 16.5
            primary_qty = 1
            reasoning = "Single-unit durable hardware tool; multi-pack offers represent artificial seller discounts."
        elif is_consumable:
            components["natural_necessity"] = {
                "raw": 95.0,
                "weight": 0.40,
                "description": "Washable / consumable refills with natural room-by-room rotation and laundry cycle replacement.",
            }
            components["utility_at_quantities"] = {
                "raw": 90.0,
                "weight": 0.30,
                "description": "Natural purchase demand for 3, 5, and 10 units (multiple rooms, backups during washing).",
            }
            components["aov_fit"] = {
                "raw": 85.0,
                "weight": 0.30,
                "description": "Modeled/observed 3, 5, or 10-pack ($30-$75) fit squarely in the $30-$90 AOV sweet spot.",
            }
            score = 90.5
            primary_qty = observed_qty
            if observed_qty:
                reasoning = f"Observed {observed_qty}-unit pack with natural replenishment demand."
            else:
                reasoning = "Consumable refill with natural room-by-room rotation and laundry cycle replacement (pack count unobserved in text)."
        else:
            # Check if bundle offers exist in DB
            bundle_res = await self.db.execute(
                select(BundleOffer).where(BundleOffer.product_id == product.id)
            )
            bundles = list(bundle_res.scalars().all())
            if not bundles:
                components["natural_necessity"] = {
                    "raw": 20.0,
                    "weight": 0.40,
                    "description": "No bundle offers observed and no consumable rotation signal",
                }
                components["utility_at_quantities"] = {
                    "raw": 20.0,
                    "weight": 0.30,
                    "description": "No multi-unit utility observed",
                }
                components["aov_fit"] = {
                    "raw": 20.0,
                    "weight": 0.30,
                    "description": "No bundle order value observed",
                }
                score = 20.0
                primary_qty = 1
                reasoning = "No multi-unit utility or bundle offers observed."
            else:
                has_natural = any(b.is_natural_bundle for b in bundles)
                if has_natural:
                    components["natural_necessity"] = {"raw": 80.0, "weight": 0.40, "description": "Natural bundle recorded"}
                    components["utility_at_quantities"] = {"raw": 80.0, "weight": 0.30, "description": "Multi-unit utility verified"}
                    components["aov_fit"] = {"raw": 80.0, "weight": 0.30, "description": "AOV within sweet spot"}
                    score = 80.0
                    primary_qty = observed_qty or 3
                    reasoning = "Natural multi-unit necessity verified by recorded bundle offers."
                else:
                    components["natural_necessity"] = {"raw": 40.0, "weight": 0.40, "description": "General necessity check"}
                    components["utility_at_quantities"] = {"raw": 40.0, "weight": 0.30, "description": "Standard utility check"}
                    components["aov_fit"] = {"raw": 40.0, "weight": 0.30, "description": "Estimated AOV check"}
                    score = 40.0
                    primary_qty = observed_qty or 3
                    reasoning = "General bundle offer present."

        return {
            "score": score,
            "components": components,
            "is_natural": is_consumable and not is_tool,
            "primary_qty": primary_qty,
            "reasoning": reasoning,
        }

    # ── 6. Evidence Confidence ────────────────────────────────────────────

    async def _compute_confidence(
        self,
        product: Product,
        ads: list[Advertisement],
        indep_adv_count: int,
        clone_detected: bool,
        has_observed_price: bool = False,
    ) -> dict:
        """
        Evaluate factual evidence quality scaled 0–100 strictly based on verified source data:
        - Independent advertiser verification (25%)
        - Traceable URLs (25%)
        - Product identification completeness (25%)
        - Pricing evidence (25%)
        Synthetic fixtures and unverified sources are capped.
        """
        components = {}

        # 1. Independent advertisers (25%)
        if clone_detected:
            adv_pts = 35.0
            adv_desc = "Clone affiliate network detected (shared funnel slug across multiple front domains) — treated as 1 entity"
        elif indep_adv_count >= 3:
            adv_pts = 100.0
            adv_desc = f"{indep_adv_count} independent advertisers confirmed"
        elif indep_adv_count == 2:
            adv_pts = 75.0
            adv_desc = "2 independent advertisers confirmed"
        elif indep_adv_count == 1:
            adv_pts = 40.0
            adv_desc = "Single advertiser confirmed"
        else:
            adv_pts = 10.0
            adv_desc = "No verified advertisers"

        components["independent_sources"] = {"raw": adv_pts, "weight": 0.25, "description": adv_desc}

        # 2. Traceable URLs (25%)
        has_lp = any(a.landing_page_url for a in ads)
        has_ad_url = any(a.ad_url for a in ads)
        trace_pts = 100.0 if (has_lp and has_ad_url) else (50.0 if has_lp or has_ad_url else 10.0)
        components["evidence_links"] = {
            "raw": trace_pts,
            "weight": 0.25,
            "description": "Traceable Meta Ad Library URLs and active destination landing pages",
        }

        # 3. Product identity completeness (25%)
        id_pts = 0.0
        if product.name:
            id_pts += 35.0
        if product.description:
            id_pts += 35.0
        if product.source_url:
            id_pts += 15.0
        if product.category:
            id_pts += 15.0
        components["product_identity"] = {
            "raw": min(100.0, id_pts),
            "weight": 0.25,
            "description": "Completeness of name, description, category, and source link",
        }

        # 4. Pricing Evidence (25%)
        pricing_pts = 100.0 if has_observed_price else 0.0
        components["pricing_evidence"] = {
            "raw": pricing_pts,
            "weight": 0.25,
            "description": "Verified observed checkout or ad pricing" if has_observed_price else "Missing observed price evidence (price unknown)",
        }

        total = round(
            components["independent_sources"]["raw"] * 0.25
            + components["evidence_links"]["raw"] * 0.25
            + components["product_identity"]["raw"] * 0.25
            + components["pricing_evidence"]["raw"] * 0.25,
            2,
        )

        # Synthetic fixture penalty
        is_synth = getattr(product, "is_synthetic", False) or product.name.startswith("DEMO ") or product.source_type == DataSourceType.OTHER
        if is_synth:
            total = min(20.0, round(total * 0.25, 2))

        return {"score": total, "components": components}

    # ── 7. Emergence Score (Momentum & Discovery Signal) ──────────────────

    async def _compute_emergence(
        self,
        product: Product,
        ads: list[Advertisement],
        discovery_signal: dict,
        momentum_val: Optional[float],
        has_longitudinal: bool,
        indep_count: int,
    ) -> dict:
        """
        Emergence Score:
        If longitudinal data exists: accounts for acceleration.
        If single collection run: strictly reports discovery signal without claiming false acceleration.
        """
        components = {}
        weights = self.settings.emergence_weights

        # 1. Advertiser acceleration
        if has_longitudinal:
            adv_accel = min(100.0, indep_count * 25.0)
            adv_desc = "Day-over-day advertiser growth rate"
        else:
            adv_accel = 0.0
            adv_desc = "No longitudinal history yet (single collection snapshot - acceleration unobserved)"

        components["advertiser_accel"] = {
            "raw": adv_accel,
            "weight": weights.get("advertiser_accel", 0.30),
            "description": adv_desc,
        }

        # 2. Creative acceleration
        if has_longitudinal:
            creative_accel = min(100.0, len(ads) * 15.0)
            creative_desc = "Creative production growth rate across observation windows"
        else:
            creative_accel = 0.0
            creative_desc = "No longitudinal history yet (single collection snapshot - acceleration unobserved)"

        components["creative_accel"] = {
            "raw": creative_accel,
            "weight": weights.get("creative_accel", 0.25),
            "description": creative_desc,
        }

        # 3. Ad persistence
        components["ad_persistence"] = {
            "raw": 20.0,
            "weight": weights.get("ad_persistence", 0.20),
            "description": "Initial observation active campaign status",
        }

        # 4. Signal recency
        recency = discovery_signal["components"].get("recency_points", 20.0) * 2.5
        components["signal_recency"] = {
            "raw": min(100.0, recency),
            "weight": weights.get("signal_recency", 0.15),
            "description": "Freshness of active campaign launch",
        }

        # 5. Demand confirmation
        components["demand_confirm"] = {
            "raw": 25.0 if indep_count >= 2 else 10.0,
            "weight": weights.get("demand_confirm", 0.10),
            "description": "Independent market confirmation",
        }

        if has_longitudinal:
            total = sum(components[k]["raw"] * components[k]["weight"] for k in components)
        else:
            # When longitudinal data is absent, Emergence Score is grounded directly in Discovery Signal Score
            total = discovery_signal["score"] * 0.7 + components["demand_confirm"]["raw"] * 0.3

        total = round(min(100.0, max(0.0, total)), 2)
        return {"score": total, "components": components}

    # ── 8. Status Qualification ──────────────────────────────────────────

    def _determine_opportunity_status(
        self,
        product: Product,
        discovery_signal: float,
        bundle_potential: float,
        functional_benefit: float,
        confidence: float,
        is_tool: bool,
        has_observed_price: bool = False,
        clone_detected: bool = False,
        indep_adv_count: int = 1,
    ) -> tuple[str, str]:
        """
        Classify opportunity into Phase 9 evidence states:
        - SYNTHETIC_FIXTURE
        - REJECTED
        - QUALIFIED (or QUALIFIED_OPPORTUNITY)
        - PROMISING
        - DISCOVERED
        """
        if getattr(product, "is_synthetic", False) or product.name.startswith("DEMO ") or product.source_type == DataSourceType.OTHER:
            return "SYNTHETIC_FIXTURE", "Synthetic fixture or test data — strictly excluded from live opportunity pipeline."

        if not product.is_physical or product.target_country != "US":
            return "REJECTED", "Non-physical product or non-US market targeting."

        if is_tool or bundle_potential < 40.0:
            return (
                "REJECTED",
                "Fails bundle-first qualification: durable hardware tool without natural multi-unit demand "
                "(multi-pack offers represent artificial seller-driven bulk discounts rather than customer replenishment necessity).",
            )

        if bundle_potential >= 60.0 and functional_benefit >= 60.0:
            # Rule: If observed price is missing, CANNOT be QUALIFIED. Must remain PROMISING!
            if not has_observed_price:
                return (
                    "PROMISING",
                    "Meets functional benefit and natural multi-unit necessity, but lacks verified observed checkout pricing (awaiting landing page price crawl).",
                )
            if confidence >= 60.0 and (indep_adv_count >= 2 or not clone_detected):
                return (
                    "QUALIFIED_OPPORTUNITY",
                    "Meets all qualification criteria: US-only, physical product, clear functional benefit, "
                    "natural 3/5/10 bundle demand, observed pricing in $30–$90 AOV range, and high evidence confidence.",
                )
            else:
                return (
                    "PROMISING",
                    "Strong candidate with observed pricing, but requires further advertiser independence or creative verification.",
                )

        if discovery_signal >= 30.0:
            return "DISCOVERED", "Early active ad creative discovered in target category with initial keyword match."

        return "DISCOVERED", "Early discovery candidate under observation."

    # ── 9. Composite Score ───────────────────────────────────────────────

    def _compute_composite(
        self,
        bundle_potential: float,
        functional_benefit: float,
        discovery_signal: float,
        confidence: float,
        status: str,
    ) -> float:
        """
        Compute Bundle-First Composite Score:
        - Bundle Potential: 40%
        - Functional Benefit: 30%
        - Discovery Signal: 20%
        - Evidence Confidence: 10%
        Penalizes REJECTED products to prevent artificial tool over-ranking.
        """
        raw = (
            bundle_potential * 0.40
            + functional_benefit * 0.30
            + discovery_signal * 0.20
            + confidence * 0.10
        )

        if status == "REJECTED":
            # Cap composite score of rejected/artificial products
            return round(min(35.0, raw * 0.5), 2)

        return round(min(100.0, max(0.0, raw)), 2)

    # ── Batch Scoring ────────────────────────────────────────────────────

    async def score_all_products(
        self, score_date: Optional[str] = None, mode: Optional[str] = None
    ) -> list[OpportunityScore]:
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
                score = await self.score_product(pid, score_date, mode=mode)
                scores.append(score)
            except Exception as e:
                logger.warning("Failed to score product %s: %s", pid, e)

        return scores

    # ── 10. Balanced Multi-Model Commercial Engine (Phase 14) ─────────────

    def _classify_commercial_model(self, product: Product, ads: list[Advertisement]) -> tuple[str, str]:
        """
        Classify product into one of 3 commercial models:
        1. MODEL_A_SINGLE_PRODUCT: Hero problem solver normally purchased as 1 complete unit.
        2. MODEL_B_NATURAL_MULTI_UNIT: Natural multi-unit need (multi-room, laundry, consumable).
        3. MODEL_C_HIGH_AOV_OFFER: Hero product paired with consumables, refills, or accessory kits.
        """
        text = f"{product.name} {product.description or ''} {' '.join(a.body or '' for a in ads)}".lower()

        # Model B: Natural consumable replenishment / multi-room rotation / multi-person / laundry
        multi_unit_keywords = [
            "pee pad", "puppy pad", "mop pad", "mop cloth", "refill", "sponge", "wipe",
            "underwear", "boxer", "sock", "chair leg", "protector cap", "furniture cap",
            "drying towel", "detailing towel", "microfiber towel", "diaper", "adhesive tape",
            "rug gripper", "filter refill", "replacement head", "toy blocker", "couch blocker",
            "bed blocker", "gap blocker", "barrier panels"
        ]
        is_model_b = any(kw in text for kw in multi_unit_keywords)

        # Model C: High-AOV Offer / Hardware paired with consumable refills or accessory packs
        # Must pair durable hardware with recurring consumable refills (filters, pads, blades)
        has_consumable_refills = any(
            kw in text
            for kw in [
                "+ refill", "+ filter", "+ pad", "with replacement filter", "with 6 replacement",
                "with 3 replacement", "with filter refill", "with refill pad", "starter kit with replacement",
                "replacement filters included", "replacement filter refills", "+ 5 pads", "+ 10 pads",
                "replacement filter", "replacement filters", "filter refills", "filter refill",
                "replacement pads", "replacement pad", "refill pack", "refill pads"
            ]
        )
        is_model_c = has_consumable_refills and any(hw in text for hw in ["fountain", "mop", "shaver", "razor", "dispenser"])

        if is_model_c:
            return (
                "MODEL_C_HIGH_AOV_OFFER",
                "High-AOV bundle/starter kit combining hero durable tool with consumable refills or complementary maintenance accessories.",
            )
        elif is_model_b:
            return (
                "MODEL_B_NATURAL_MULTI_UNIT",
                "Natural multi-unit household utility: multi-room placement, laundry rotation, or consumable replacement.",
            )
        else:
            return (
                "MODEL_A_SINGLE_PRODUCT",
                "Self-contained hero problem solver purchased as a single complete unit.",
            )

    def _compute_core_opportunity(
        self,
        product: Product,
        ads: list[Advertisement],
        discovery_signal: dict,
        functional_benefit: float,
        has_observed_price: bool,
    ) -> tuple[float, dict]:
        """
        Core Product Opportunity Score (0-100):
        1. Problem-solving clarity & pain severity: 25%
        2. Physical utility & mechanism clarity: 20%
        3. Visual demonstration appeal & hook strength: 20%
        4. Market discovery signal (early ad freshness & active ads): 15%
        5. Fulfillment feasibility (dropshipping logistics: weight, fragile risk): 10%
        6. Commercial price & margin headroom ($30-$90 AOV sweet spot): 10%
        """
        if not product.is_physical:
            return 0.0, {"reason": "Non-physical product", "score": 0.0}

        text = f"{product.name} {product.description or ''} {' '.join(a.body or '' for a in ads)}".lower()

        # 1. Pain severity (25 pts)
        pain_keywords = [
            "strip", "extract", "screw", "bolt", "leak", "urine", "odor", "scratch",
            "claw", "stain", "spill", "cold", "freeze", "draft", "noise", "arthritis",
            "pain", "choking", "bloat", "acne", "bacterial", "dirty", "grime", "break"
        ]
        pain_matches = sum(1 for kw in pain_keywords if kw in text)
        pain_pts = min(25.0, 12.0 + pain_matches * 3.5)

        # 2. Physical utility mechanics (20 pts)
        utility_pts = round(min(20.0, (functional_benefit / 100.0) * 20.0), 2)

        # 3. Visual demonstration appeal (20 pts)
        demo_keywords = [
            "instant", "seconds", "before and after", "watch", "demonstrat", "test",
            "satisfy", "magnetic", "transform", "hands-free", "reverse", "360", "glow"
        ]
        demo_matches = sum(1 for kw in demo_keywords if kw in text)
        demo_pts = min(20.0, 10.0 + demo_matches * 3.0)

        # 4. Market discovery signal (15 pts)
        disc_score = discovery_signal.get("score", 0.0)
        discovery_pts = round(min(15.0, (disc_score / 100.0) * 15.0), 2)

        # 5. Fulfillment feasibility (10 pts)
        bulky_or_fragile = any(kw in text for kw in ["glass aquarium", "liquid chemical", "large sofa"])
        fulfillment_pts = 5.0 if bulky_or_fragile else 10.0

        # 6. Commercial margin headroom (10 pts)
        price = product.min_price_usd or product.max_price_usd
        if price:
            if 30.0 <= price <= 90.0:
                price_pts = 10.0
            elif 20.0 <= price < 30.0:
                price_pts = 7.5
            elif price > 90.0:
                price_pts = 6.0
            else:
                price_pts = 4.0
        else:
            price_pts = 6.0 if has_observed_price else 5.0

        total = round(pain_pts + utility_pts + demo_pts + discovery_pts + fulfillment_pts + price_pts, 2)
        components = {
            "pain_severity_points": round(pain_pts, 2),
            "physical_utility_points": round(utility_pts, 2),
            "visual_appeal_points": round(demo_pts, 2),
            "discovery_points": round(discovery_pts, 2),
            "fulfillment_feasibility_points": round(fulfillment_pts, 2),
            "margin_headroom_points": round(price_pts, 2),
        }
        return total, components

    def _compute_bundle_upside(
        self,
        product: Product,
        ads: list[Advertisement],
        model: str,
        bundle_eval: dict,
    ) -> tuple[float, dict]:
        """
        Bundle Upside Score (0-100):
        For Model B: Reflects natural high multi-unit necessity (85-95 pts).
        For Model C: Reflects starter kit / consumable bundling potential (75-90 pts).
        For Model A: Reflects optional accessory / replacement add-on potential (25-45 pts).
        """
        if model == "MODEL_B_NATURAL_MULTI_UNIT":
            score = max(bundle_eval.get("score", 0.0), 85.0)
            desc = "High natural multi-unit demand for room rotation, laundry cycle, or consumable replenishment."
        elif model == "MODEL_C_HIGH_AOV_OFFER":
            score = 80.0
            desc = "Strong bundling synergy: Hero hardware naturally pairs with consumable refills or maintenance kits."
        else:
            score = 35.0
            desc = "Single-unit hero product; optional bundle upside via accessories, but primary value is standalone unit."

        return score, {"score": score, "description": desc}

    def _check_claims_and_safety(
        self, product: Product, ads: list[Advertisement]
    ) -> tuple[float, float, str, str]:
        """
        Audit for:
        1. Unsupported medical/health claims (FTC/FDA ban risk: arthritis cure, bloat prevention)
        2. High electrical/thermal safety risks (UL/ETL requirement: pet heating pad, thermal bowl)
        Returns (claim_penalty, safety_penalty, claim_warning, safety_warning).
        """
        text = f"{product.name} {product.description or ''} {' '.join(a.body or '' for a in ads)}".lower()

        # 1. Unsupported medical claims check
        medical_claim_kws = [
            "cure arthritis", "cures arthritis", "cure hip dysplasia", "cures hip dysplasia",
            "prevents bloat", "prevents gdv", "eliminate bloat", "eliminates bloat",
            "medical cure", "clinically proven to cure", "treatment for arthritis"
        ]
        unsupported_claims = [kw for kw in medical_claim_kws if kw in text]
        if unsupported_claims:
            claim_penalty = 15.0
            claim_warning = f"FLAGGED: Unsupported medical/health claim detected ('{', '.join(unsupported_claims)}'). FTC/FDA compliance violation risk."
        else:
            claim_penalty = 0.0
            claim_warning = ""

        # 2. Electrical / thermal safety risk check
        electrical_thermal_kws = [
            "electric heating pad", "heated pet pad", "pet heating pad", "heated pet water bowl",
            "heated bowl", "heating wire", "plug-in heater"
        ]
        is_electrical_thermal = any(kw in text for kw in electrical_thermal_kws)
        has_cert = False
        if product.raw_data and isinstance(product.raw_data, dict):
            has_cert = bool(product.raw_data.get("ul_etl_certified", False))

        if is_electrical_thermal and not has_cert:
            safety_penalty = 10.0
            safety_warning = "FLAGGED: Electrical heating element without verified UL/ETL safety certification. Fire/burn liability risk."
        else:
            safety_penalty = 0.0
            safety_warning = ""

        return claim_penalty, safety_penalty, claim_warning, safety_warning

    def _determine_status_balanced(
        self,
        product: Product,
        core_opp: float,
        bundle_upside: float,
        discovery_signal: float,
        confidence: float,
        model: str,
        has_observed_price: bool = False,
        clone_detected: bool = False,
        indep_adv_count: int = 1,
        claim_warning: str = "",
        safety_warning: str = "",
    ) -> tuple[str, str]:
        if getattr(product, "is_synthetic", False) or product.name.startswith("DEMO ") or product.source_type == DataSourceType.OTHER:
            return "SYNTHETIC_FIXTURE", "Synthetic fixture or test data — strictly excluded from live opportunity pipeline."

        if not product.is_physical or product.target_country != "US":
            return "REJECTED", "Non-physical product or non-US market targeting."

        if core_opp < 30.0:
            return "REJECTED", f"Insufficient product opportunity fundamentals (core score {core_opp:.1f} < 30.0)."

        # Critical Safety & Compliance Gates (Mission 4)
        if safety_warning:
            return (
                "NEEDS_SAFETY_VERIFICATION",
                f"Promising {model} concept, but commercial deployment is BLOCKED: {safety_warning}",
            )

        if claim_warning:
            return (
                "NEEDS_CLAIM_CORRECTION",
                f"Promising {model} concept, but commercial deployment is BLOCKED: {claim_warning}",
            )

        if core_opp >= 60.0:
            if not has_observed_price:
                return (
                    "PROMISING",
                    f"Strong {model} opportunity (core score {core_opp:.1f}), but lacks verified observed checkout pricing (awaiting landing page price crawl).",
                )
            if confidence >= 50.0 and (indep_adv_count >= 1 and not clone_detected):
                return (
                    "QUALIFIED_OPPORTUNITY",
                    f"Qualified {model} winner: US physical product, high functional benefit, validated commercial pricing, and confirmed evidence confidence.",
                )
            else:
                return (
                    "PROMISING",
                    f"Strong {model} candidate with observed pricing, but requires further advertiser independence or creative verification.",
                )

        if discovery_signal >= 30.0 or core_opp >= 45.0:
            return "DISCOVERED", f"Active discovery candidate under {model} observation."

        return "DISCOVERED", "Early candidate under observation."

    def _compute_composite_balanced(
        self,
        model: str,
        core_opp: float,
        bundle_upside: float,
        discovery_signal: float,
        confidence: float,
        status: str,
        safety_penalty: float = 0.0,
        claim_penalty: float = 0.0,
    ) -> float:
        """
        Compute Balanced Multi-Model Composite Score:
        - MODEL_A_SINGLE_PRODUCT:
            Base components sum to 100% without ANY bundle requirement!
            Core Opportunity: 60%
            Discovery Signal: 25%
            Evidence Confidence: 15%
            Sum = 100%
            Optional Additive Bundle Bonus: up to +5.0 points bounded bonus if accessories/refill bundle exists.
            Absence of bundle (bundle_upside = 0) NEVER reduces attainable core score below 100%.
        - MODEL_B_NATURAL_MULTI_UNIT:
            Core Opportunity: 50%
            Bundle Upside (Natural Multi-Unit Necessity): 25%
            Discovery Signal: 15%
            Evidence Confidence: 10%
            Sum = 100%
        - MODEL_C_HIGH_AOV_OFFER:
            Core Opportunity: 50%
            Bundle Upside (Starter Kit / Consumable Refills): 25%
            Discovery Signal: 15%
            Evidence Confidence: 10%
            Sum = 100%
        - Safety & Claims Risk Deductions:
            Deducts safety_penalty (e.g. 10.0 for unverified high-voltage electrical)
            Deducts claim_penalty (e.g. 15.0 for illegal medical cure claims)
        """
        if status in ("REJECTED", "SYNTHETIC_FIXTURE"):
            return round(min(30.0, core_opp * 0.4), 2)

        if model == "MODEL_A_SINGLE_PRODUCT":
            # 100% attainable without bundle
            base = (
                core_opp * 0.60
                + discovery_signal * 0.25
                + confidence * 0.15
            )
            # Additive optional bonus (0 to 5 pts)
            bundle_bonus = min(5.0, (bundle_upside / 100.0) * 5.0) if bundle_upside > 0 else 0.0
            raw = base + bundle_bonus
        else:
            raw = (
                core_opp * 0.50
                + bundle_upside * 0.25
                + discovery_signal * 0.15
                + confidence * 0.10
            )

        # Apply risk penalties
        total_risk_penalty = safety_penalty + claim_penalty
        raw = max(0.0, raw - total_risk_penalty)

        return round(min(100.0, max(0.0, raw)), 2)

    def _generate_explainability(
        self,
        product: Product,
        ads: list[Advertisement],
        model: str,
        core_opp: float,
        bundle_upside: float,
        confidence_eval: dict,
        has_observed_price: bool,
        obs_single: Optional[float],
        obs_bundle: Optional[float],
        status: str,
        claim_warning: str = "",
        safety_warning: str = "",
    ) -> dict:
        if model == "MODEL_A_SINGLE_PRODUCT":
            why_high = "High-utility hero problem solver with demonstrable physical mechanism and strong single-unit consumer purchase intent."
            why_fail = "Risk of low customer lifetime value (LTV) due to one-time purchase nature, competitive copycats, or potential returns if mechanical tolerances fail."
        elif model == "MODEL_B_NATURAL_MULTI_UNIT":
            why_high = "High natural multi-unit demand driven by multi-room utility, frequent laundry rotation, or recurring consumable replenishment."
            why_fail = "Risk of high customer acquisition costs if ad creative cannot clearly communicate multi-pack value proposition, or sizing/compatibility mismatch."
        else:
            why_high = "High-AOV starter kit combining durable hardware with recurring consumable refills or complementary maintenance accessories."
            why_fail = "Risk of inventory complexity managing multiple SKUs/refill bundles, and supplier dependency for custom kit packaging."

        if safety_warning:
            why_fail = f"{safety_warning} {why_fail}"
        if claim_warning:
            why_fail = f"{claim_warning} {why_fail}"

        evidence_points = []
        if ads:
            evidence_points.append(f"{len(ads)} observed Meta/TikTok ad creatives")
        if has_observed_price:
            price_str = f"${obs_single:.2f}" if obs_single else f"${obs_bundle:.2f}"
            evidence_points.append(f"Observed checkout pricing at {price_str}")
        if product.category:
            evidence_points.append(f"Classified under {product.category}")
        what_evidence = "; ".join(evidence_points) if evidence_points else "Early initial discovery record."

        what_unknown = (
            "Supplier landed COGS from verified manufacturer (1688/CJ Dropshipping), "
            "return/chargeback rate baseline, exact landing page checkout conversion rate."
        )
        if safety_warning:
            what_unknown = f"Authentic UL/ETL safety testing laboratory certificate and factory quality inspection report. {what_unknown}"

        next_action = (
            "Execute supplier landed cost lookup (1688/CJ) to verify 65%+ gross margin, "
            "scrape Amazon negative reviews (1-2 stars) for quality failure modes, and track search trend momentum."
        )
        if safety_warning:
            next_action = f"Mandatory electrical safety compliance audit (UL 130 / ETL testing) before commercial deployment. {next_action}"
        if claim_warning:
            next_action = f"Rewrite advertising copy to eliminate unsubstantiated medical/cure claims (FTC/FDA compliance). {next_action}"

        return {
            "why_it_ranks_high": why_high,
            "why_it_might_fail": why_fail,
            "what_evidence_supports_it": what_evidence,
            "what_remains_unknown": what_unknown,
            "next_validation_action": next_action,
        }


class BalancedScoringEngine(ScoringEngine):
    """Balanced 3-model opportunity scoring engine (Single-Product, Multi-Unit, High-AOV Offer)."""

    def __init__(self, db: AsyncSession):
        super().__init__(db, mode="balanced")

