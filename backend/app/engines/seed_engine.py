"""
US WIN HUNTER — Discovery Seed Engine

Automated seed generation and query taxonomy engine.
Generates pain-grounded, bundle-rationalized research queries for the US market
across 10 core physical product categories.

Enforces:
- US-only product context
- Natural multi-unit bundle rationale (3, 5, 10 units, multi-room, daily rotation)
- Consumer pain/problem/solution framing
- Dynamic prioritization based on empirical discovery yield
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)

SEEDS_STORAGE_PATH = Path(__file__).resolve().parents[3] / "data" / "discovery_seeds.json"


@dataclass
class DiscoverySeed:
    keyword: str
    category: str
    source: str  # "taxonomy", "pain_cluster", "product_expansion", "custom"
    generation_reason: str
    bundle_rationale: str
    target_bundle_units: list[int] = field(default_factory=lambda: [3, 5, 10])
    last_collected_at: Optional[str] = None
    total_runs: int = 0
    unique_products_found: int = 0
    new_advertisers_found: int = 0
    total_records_fetched: int = 0
    duplicate_records: int = 0
    estimated_cost_usd: float = 0.0
    yield_score: float = 50.0  # Initial neutral score for exploration

    @property
    def duplicate_rate(self) -> float:
        if self.total_records_fetched == 0:
            return 0.0
        return self.duplicate_records / self.total_records_fetched


# ── 10 Initial US Physical Product Taxonomy ───────────────────────────────────

TAXONOMY_CATEGORIES = {
    "Home & Cleaning": {
        "pains": [
            "pet hair and stubborn stains on upholstery",
            "lime scale and soap scum buildup in showers",
            "dust accumulation in hard-to-reach ceiling vents",
            "streaky glass and mirror residue",
        ],
        "mechanisms": [
            "washable reusable microfiber rotation",
            "electrostatic dust attraction",
            "drill-powered rotating bristle scrubbers",
        ],
        "bundle_rationales": [
            "3-pack: one for kitchen, one for master bathroom, one for guest bathroom",
            "5-pack daily rotation: wash used pads while clean ones remain active",
        ],
        "seed_templates": [
            ("reusable microfiber mop pads multi pack washable rotation", [3, 5]),
            ("drill brush attachment set bathroom scrubber 5 pack", [3, 5]),
            ("crevice cleaning brush hard bristle set of 3 multi room", [3, 5]),
            ("washable magic groove window cleaning tool 3 pack", [3, 5]),
        ],
    },
    "Automotive": {
        "pains": [
            "dropped phones and coins between seat gaps",
            "loose tools rattling in truck beds and trunks",
            "sun damage and intense heat on steering wheels",
            "foggy windshields reducing night visibility",
        ],
        "mechanisms": [
            "contoured wedge drop catchers",
            "magnetic modular tool socket rails",
            "foldable umbrella-style heat reflective barriers",
        ],
        "bundle_rationales": [
            "2-pack or 4-pack for multi-car households (driver + passenger, 2 family cars)",
            "3-pack socket organizers (1/4, 3/8, 1/2 inch drive sizes)",
        ],
        "seed_templates": [
            ("car seat gap filler organizer leather pair 2 pack", [2, 4]),
            ("magnetic socket organizer tray metric and sae 3 pack", [3]),
            ("automotive glass defogging cleaning wand replacement pads 3 pack", [3, 5]),
            ("car trunk collapsible storage organizer heavy duty 2 pack", [2]),
        ],
    },
    "Pet Supplies": {
        "pains": [
            "fur embedded in car seats and sofa fabrics",
            "fast-eating pets bloating and choking",
            "destructive chewing during separation anxiety",
            "dirty muddy paws tracking into the house after walks",
        ],
        "mechanisms": [
            "dual-blade rubber deshedding scrapers",
            "maze slow feeder silicone inserts",
            "dog paw plunger cleaner with soft silicone bristles",
        ],
        "bundle_rationales": [
            "3-pack multi-location: one at front door, one in car, one by back patio",
            "Multi-pet households: 3 units for different pet sizes or rotational wash",
        ],
        "seed_templates": [
            ("pet hair remover metal scraper multi room 3 pack", [3, 5]),
            ("portable dog paw cleaner cup multi door 2 pack", [2, 3]),
            ("slow feeder bowl insert silicone suction cups 3 pack", [3]),
            ("washable leakproof pet pee pads reusable 4 pack rotation", [3, 5]),
        ],
    },
    "Household Essentials": {
        "pains": [
            "drafts and insects entering through door gaps",
            "cables tangling behind desks and entertainment centers",
            "cabinet doors slamming loudly at night",
            "cluttered pantry staples losing freshness",
        ],
        "mechanisms": [
            "twin-draft silicone door sweep weatherstripping",
            "magnetic silicone cable clips and organizers",
            "airtight silicone pop-lock storage seals",
        ],
        "bundle_rationales": [
            "Multi-room necessity: every exterior and interior door needs sealing (3-5 doors)",
            "10-pack cable organizers for home office, bedroom, and kitchen charging stations",
        ],
        "seed_templates": [
            ("under door draft stopper twin soundproof 3 pack", [3, 5]),
            ("magnetic cable clips cord organizer desk 10 pack", [5, 10]),
            ("silicone stretch lids airtight reusable food covers 6 pack", [6, 12]),
            ("motion sensor closet lights magnetic rechargeable 3 pack", [3, 5]),
        ],
    },
    "Functional Apparel": {
        "pains": [
            "plantar fasciitis and arch fatigue from standing all day",
            "chafing during exercise or daily walking",
            "sweaty feet and blister friction in work boots",
            "slouching and upper back strain during desk work",
        ],
        "mechanisms": [
            "targeted 20-30 mmHg graduated compression weave",
            "anti-friction moisture-wicking bamboo fibers",
            "ergonomic clavicle posture brace alignment",
        ],
        "bundle_rationales": [
            "Daily rotation: 5-pack or 7-pack required for weekly laundry cycles",
            "3-pack: one for work, one for gym, one in wash",
        ],
        "seed_templates": [
            ("graduated compression socks running nurses 5 pack daily rotation", [5, 7]),
            ("plantar fasciitis arch support copper sleeve pair 3 pack", [3, 5]),
            ("moisture wicking cushioned work boot socks 6 pack", [6, 10]),
            ("seamless anti chafing slip shorts underwear 3 pack", [3, 5]),
        ],
    },
    "Kitchen": {
        "pains": [
            "cluttered spice jars falling out of high cabinets",
            "excess oil pouring and uneven pan coating",
            "blunt knives slipping on tomato skins and meats",
            "grease splashing on stove tops and backsplashes",
        ],
        "mechanisms": [
            "pressurized fine mist oil sprayer nozzles",
            "magnetic stainless steel refrigerator spice racks",
            "foldable silicone anti-splatter screens",
        ],
        "bundle_rationales": [
            "2-pack / 3-pack: one bottle for olive oil, one for avocado oil, one for vinegar",
            "4-pack magnetic storage shelves for side of fridge and stove",
        ],
        "seed_templates": [
            ("olive oil sprayer mister for cooking kitchen 2 pack", [2, 3]),
            ("magnetic spice rack organizer refrigerator side 4 pack", [2, 4]),
            ("silicone baking mats non stick reusable half sheet 3 pack", [3, 5]),
            ("reusable silicone food storage bags stand up zip 6 pack", [6, 10]),
        ],
    },
    "Storage & Organization": {
        "pains": [
            "under-sink pipe obstruction wasting cabinet height",
            "closet clothes folding over into messy heaps",
            "shoes piling up in chaotic entryway heaps",
            "drawer dividers shifting whenever opened",
        ],
        "mechanisms": [
            "expandable two-tier sliding under-sink drawer caddies",
            "clear stackable drop-front magnetic shoeboxes",
            "spring-loaded adjustable bamboo drawer dividers",
        ],
        "bundle_rationales": [
            "2-pack under-sink organizers (kitchen + master bathroom)",
            "6-pack or 12-pack modular shoe container display wall",
            "4-pack drawer dividers for multiple dresser drawers",
        ],
        "seed_templates": [
            ("under sink organizer 2 tier pull out sliding drawer 2 pack", [2, 4]),
            ("drop front shoe storage boxes stackable magnetic 6 pack", [6, 12]),
            ("spring loaded bamboo drawer dividers expandable 4 pack", [4, 8]),
            ("hat organizer rack for baseball caps closet hanger 2 pack", [2, 4]),
        ],
    },
    "Tools & Home Improvement": {
        "pains": [
            "lost small screws and drill bits on ladders and floors",
            "messy caulk beads leaking around tubs and sinks",
            "inaccurate contour measurements on pipes and tile cuts",
            "heavy garden tools toppling in garage corners",
        ],
        "mechanisms": [
            "embedded neodymium magnetic wristband holders",
            "3-in-1 silicone caulk finishing scraper tools",
            "locking profile contour duplicator gauge teeth",
            "heavy-duty wall-mounted rubberized steel hooks",
        ],
        "bundle_rationales": [
            "10-pack heavy duty garage hooks for systematic tool wall hangings",
            "3-pack magnetic wristbands for worker, helper, and backup toolbox",
        ],
        "seed_templates": [
            ("magnetic wristband holding screws drill bits 2 pack", [2, 3]),
            ("heavy duty garage storage hooks wall mount steel 10 pack", [6, 10]),
            ("silicone caulking tool kit sealant finisher scraper set of 3", [3]),
            ("contour gauge profile tool with lock wide shape duplicator 2 pack", [2]),
        ],
    },
    "Gardening": {
        "pains": [
            "plants drying out while on vacation or long workdays",
            "pests eating vegetable seedlings overnight",
            "tangled hoses kinking and bursting under summer sun",
            "back pain from kneeling on hard soil and rocks",
        ],
        "mechanisms": [
            "terracotta self-watering spikes using recycled wine bottles",
            "foldable elevated garden kneeler seat with tool pouches",
            "expandable kink-free flexible garden hose with brass fittings",
        ],
        "bundle_rationales": [
            "6-pack or 12-pack self-watering spikes for all indoor/patio potted plants",
            "Multi-zone hose splitters and sprinkler heads for front and back yards",
        ],
        "seed_templates": [
            ("self watering spikes terracotta plant dripper stakes 6 pack", [6, 12]),
            ("garden hose quick connect brass fittings set 4 pack", [4, 8]),
            ("solar ultrasonic animal repellent waterproof garden 2 pack", [2, 4]),
            ("hanging plant pulley retractable hook ceiling garden 3 pack", [3, 6]),
        ],
    },
    "Outdoor Essentials": {
        "pains": [
            "mosquitoes ruining backyard deck and patio evenings",
            "pitch-black walkways causing tripping hazards at night",
            "patio furniture cushions fading and mildewing in rain",
            "flat tires on bicycles and outdoor equipment far from gas stations",
        ],
        "mechanisms": [
            "solar-powered high-lumen motion-activated LED floodlights",
            "ultrasonic thermacell-style mosquito repellent spatial zones",
            "cordless rechargeable portable air compressor pumps",
        ],
        "bundle_rationales": [
            "4-pack or 8-pack solar pathway lights for full perimeter coverage",
            "2-pack rechargeable mosquito repellers (front porch + rear patio)",
        ],
        "seed_templates": [
            ("solar outdoor lights motion sensor waterproof wall 4 pack", [4, 8]),
            ("solar pathway lights outdoor bright led driveway 8 pack", [6, 8, 12]),
            ("waterproof outdoor patio furniture covers heavy duty 2 pack", [2, 4]),
            ("portable led camping lantern collapsible magnetic 3 pack", [3, 4]),
        ],
    },
}


class DiscoverySeedEngine:
    """Manages the discovery seed bank, taxonomy generation, and yield-based ranking."""

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or SEEDS_STORAGE_PATH
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.seeds: dict[str, DiscoverySeed] = {}
        self._load_seeds()

    def _load_seeds(self) -> None:
        """Load seeds from storage or bootstrap from taxonomy."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        seed = DiscoverySeed(**item)
                        self.seeds[seed.keyword.lower().strip()] = seed
                if self.seeds:
                    return
            except Exception as e:
                logger.warning("Failed to load discovery seeds from %s: %s", self.storage_path, e)

        # Bootstrap from default taxonomy
        self.generate_taxonomy_seeds()

    def _save_seeds(self) -> None:
        """Persist seeds to disk."""
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump([asdict(s) for s in self.seeds.values()], f, indent=2)
        except Exception as e:
            logger.error("Failed to save discovery seeds: %s", e)

    def generate_taxonomy_seeds(self) -> list[DiscoverySeed]:
        """Bootstrap seeds from the structured 10-category US physical product taxonomy."""
        new_seeds: list[DiscoverySeed] = []

        for category, cat_data in TAXONOMY_CATEGORIES.items():
            rationale_summary = " | ".join(cat_data["bundle_rationales"])
            for template, bundle_units in cat_data["seed_templates"]:
                norm_kw = template.lower().strip()
                if norm_kw not in self.seeds:
                    seed = DiscoverySeed(
                        keyword=norm_kw,
                        category=category,
                        source="taxonomy",
                        generation_reason=f"Pain-grounded functional seed for {category}",
                        bundle_rationale=rationale_summary,
                        target_bundle_units=bundle_units,
                        yield_score=60.0,  # Favorable initial score for hand-crafted seeds
                    )
                    self.seeds[norm_kw] = seed
                    new_seeds.append(seed)

        self._save_seeds()
        return new_seeds

    def add_custom_seed(
        self,
        keyword: str,
        category: str,
        source: str = "custom",
        reason: str = "Manual operator research query",
        bundle_rationale: str = "Multi-unit purchase potential",
        target_bundle_units: Optional[list[int]] = None,
    ) -> DiscoverySeed:
        """Register a new research seed."""
        norm_kw = keyword.lower().strip()
        seed = DiscoverySeed(
            keyword=norm_kw,
            category=category,
            source=source,
            generation_reason=reason,
            bundle_rationale=bundle_rationale,
            target_bundle_units=target_bundle_units or [3, 5],
            yield_score=50.0,
        )
        self.seeds[norm_kw] = seed
        self._save_seeds()
        return seed

    def get_prioritized_seeds(
        self,
        limit: int = 10,
        category: Optional[str] = None,
        only_uncollected: bool = False,
    ) -> list[DiscoverySeed]:
        """
        Rank seeds by yield score and recency.
        Uncollected seeds get exploration priority; collected seeds rank by empirical yield.
        """
        candidates = list(self.seeds.values())
        if category:
            candidates = [c for c in candidates if c.category.lower() == category.lower()]

        if only_uncollected:
            candidates = [c for c in candidates if not c.last_collected_at]

        # Prioritization formula:
        # 1. Uncollected seeds have exploration weight
        # 2. Collected seeds: yield_score - (penalty for high duplicate rate)
        def score_seed(s: DiscoverySeed) -> float:
            if not s.last_collected_at:
                return 100.0 + s.yield_score  # High priority to explore new seeds
            score = s.yield_score
            score -= s.duplicate_rate * 30.0  # Penalize high saturation/duplicate queries
            score += s.unique_products_found * 10.0
            score += s.new_advertisers_found * 5.0
            return score

        candidates.sort(key=score_seed, reverse=True)
        return candidates[:limit]

    def record_query_feedback(
        self,
        keyword: str,
        total_fetched: int,
        unique_products: int,
        new_advertisers: int,
        duplicates: int,
        cost_usd: float = 0.0,
    ) -> Optional[DiscoverySeed]:
        """Update seed performance metrics and recalculate yield score."""
        norm_kw = keyword.lower().strip()
        seed = self.seeds.get(norm_kw)
        if not seed:
            return None

        seed.total_runs += 1
        seed.last_collected_at = datetime.now(timezone.utc).isoformat()
        seed.total_records_fetched += total_fetched
        seed.unique_products_found += unique_products
        seed.new_advertisers_found += new_advertisers
        seed.duplicate_records += duplicates
        seed.estimated_cost_usd += cost_usd

        # Dynamic yield calculation (0 to 100 scale)
        if total_fetched > 0:
            product_rate = unique_products / total_fetched
            adv_rate = new_advertisers / total_fetched
            dup_rate = duplicates / total_fetched
            
            # Higher weight for new products and advertisers, penalize pure duplicates
            calculated = (product_rate * 120.0) + (adv_rate * 80.0) + 20.0 - (dup_rate * 30.0)
            seed.yield_score = max(5.0, min(100.0, round(calculated, 1)))
        else:
            seed.yield_score = max(10.0, seed.yield_score - 5.0)

        self._save_seeds()
        return seed

    def list_all_seeds(self) -> list[dict[str, Any]]:
        """Return all seeds as dictionary list for API / dashboard."""
        return [asdict(s) for s in self.seeds.values()]

