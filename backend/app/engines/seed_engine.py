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


# ── Phase 9: Multi-Category Discovery Taxonomy (6 Core Categories) ───────────

PHASE9_CORE_CATEGORIES: dict[str, dict[str, Any]] = {
    "Home & Cleaning": {
        "allocation_weight": 0.20,
        "problem_class": "Stubborn grime, grease, lime scale, and pet hair across diverse household surfaces requiring continuous pad/wipe rotation.",
        "mechanism_of_action": "Electrostatic microfiber absorption, washable deep-cleaning pads, rotating scrubbers.",
        "natural_bundle_rationale": "Multi-room utility: clean kitchen floors, bathrooms, and living areas with dedicated pads to prevent cross-contamination.",
        "replenishment_logic": "Washable laundry cycle (3-5 pads in wash, 3-5 active) and consumable wear replacement.",
        "target_bundle_units": [3, 5, 10],
        "plausible_aov_range": "$30–$75",
        "structured_seed_templates": [
            {
                "problem": "pet hair and dirty grout",
                "solution": "washable microfiber replacement mop pads",
                "outcome": "scratch-free streak-free clean floors",
                "audience": "pet owners and suburban homeowners",
                "usage_context": "hardwood and tile floor cleaning rotation",
                "bundle_rationale": "5-pack laundry cycle rotation",
                "query": "washable microfiber mop replacement pads 5 pack rotation",
            },
            {
                "problem": "lime scale and soap scum buildup in showers",
                "solution": "power scrubber rotating brush head refills",
                "outcome": "deep bathroom restoration without elbow grease",
                "audience": "busy homeowners",
                "usage_context": "bathroom tile and glass door cleaning",
                "bundle_rationale": "4-pack brush head refills for shower, sink, tub",
                "query": "electric spin scrubber replacement brush heads 4 pack",
            },
            {
                "problem": "streaky glass windows and dust traps in blinds",
                "solution": "washable groove window sill cleaning brush set",
                "outcome": "spotless sliding tracks and window corners",
                "audience": "spring cleaners",
                "usage_context": "multi-window house cleaning",
                "bundle_rationale": "3-pack for upstairs, downstairs, and patio doors",
                "query": "washable window groove cleaning brush set of 3 multi room",
            },
        ],
        "exclusion_rules": [
            "Exclude single-unit plastic mop handles without refill packs",
            "Exclude heavy corded vacuum cleaners and expensive floor machines",
            "Exclude single-use disposable chemical wipes with chemical hazard warnings",
            "Exclude promotional keywords ('50% off', 'free shipping', 'bogo')",
        ],
    },
    "Functional Apparel": {
        "allocation_weight": 0.20,
        "problem_class": "Plantar fasciitis, arch pain, varicose veins, chafing, and bladder leak vulnerability during daily movement.",
        "mechanism_of_action": "Targeted graduated compression weave (20-30 mmHg), multi-layer moisture-wicking leakproof gussets.",
        "natural_bundle_rationale": "Daily wear necessity: consumers must change underwear, socks, and joint sleeves every single day.",
        "replenishment_logic": "Daily rotation and weekly laundry cycle (3, 5, or 7-pack to cover work week without daily washing).",
        "target_bundle_units": [3, 5, 7],
        "plausible_aov_range": "$35–$85",
        "structured_seed_templates": [
            {
                "problem": "foot fatigue and ankle swelling from standing all day",
                "solution": "graduated compression socks 20-30 mmHg",
                "outcome": "improved circulation and all-day leg relief",
                "audience": "nurses, retail workers, travelers",
                "usage_context": "12-hour shifts and daily work rotation",
                "bundle_rationale": "5-pack weekly work rotation",
                "query": "graduated compression socks nurses 5 pack daily rotation",
            },
            {
                "problem": "plantar fasciitis heel stabbing pain in morning",
                "solution": "copper arch support compression sleeves",
                "outcome": "continuous arch support inside daily shoes",
                "audience": "active walkers and sufferers of heel spurs",
                "usage_context": "daily wearing with athletic shoes and work boots",
                "bundle_rationale": "3-pair rotation: active, spare, and laundry",
                "query": "plantar fasciitis copper compression arch support sleeve pair 3 pack",
            },
            {
                "problem": "thigh chafing and sweat buildup in summer heat",
                "solution": "seamless anti-chafing bamboo slip shorts",
                "outcome": "friction-free comfortable walking under dresses and pants",
                "audience": "women seeking discreet comfort",
                "usage_context": "daily summer wardrobe rotation",
                "bundle_rationale": "3-pack neutral colors for daily rotation",
                "query": "seamless anti chafing cooling slip shorts 3 pack daily rotation",
            },
        ],
        "exclusion_rules": [
            "Exclude fast-fashion novelty graphic t-shirts and luxury brand designer clothes",
            "Exclude seasonal outerwear (winter coats, ski jackets) lacking replenishment utility",
            "Exclude custom-tailored suits or dresses with single-event wearability",
            "Exclude promotional discount queries ('cheap socks', 'bogo underwear')",
        ],
    },
    "Automotive": {
        "allocation_weight": 0.15,
        "problem_class": "Lost items between seats, cluttered vehicle cabins, blinding sun glare, and dust accumulation on delicate car finishes.",
        "mechanism_of_action": "Contoured seat gap drop catchers, magnetic organizer rails, ultra-absorbent edgeless drying microfiber.",
        "natural_bundle_rationale": "Multi-car households and driver+passenger symmetry: 2-pack or 4-pack for multi-vehicle coverage.",
        "replenishment_logic": "Multi-vehicle coverage (average US household has 2.2 vehicles) and rotating wash cycles.",
        "target_bundle_units": [2, 3, 4],
        "plausible_aov_range": "$30–$65",
        "structured_seed_templates": [
            {
                "problem": "phones and cards falling into unreachable seat gaps",
                "solution": "flexible contoured leather car seat gap filler organizers",
                "outcome": "zero dropped items and extra storage slot",
                "audience": "commuters and rideshare drivers",
                "usage_context": "front driver and passenger seats",
                "bundle_rationale": "2-pack or 4-pack for family 2-car household",
                "query": "car seat gap filler organizer leather 2 pack multi car",
            },
            {
                "problem": "micro-scratches and water spots during car drying",
                "solution": "heavyweight 1200 GSM twisted loop microfiber drying towels",
                "outcome": "streak-free scratch-free one-pass drying",
                "audience": "DIY auto detailing enthusiasts",
                "usage_context": "routine car wash and wax buffing",
                "bundle_rationale": "3-pack rotation for paint, glass, and wheels",
                "query": "twisted loop microfiber car drying towels 1200 gsm 3 pack",
            },
            {
                "problem": "foggy windshields and interior oily film obscuring vision",
                "solution": "windshield reach cleaning tool with pivoting head and microfiber bonnets",
                "outcome": "crystal clear interior glass reaching bottom dash corners",
                "audience": "daily commuters in humid or cold climates",
                "usage_context": "windshield defogging and glass maintenance",
                "bundle_rationale": "2-pack wand with 4 replacement washable bonnets",
                "query": "car windshield cleaning tool with replacement microfiber pads 4 pack",
            },
        ],
        "exclusion_rules": [
            "Exclude heavy mechanical engine parts (transmissions, alternators, brake pads)",
            "Exclude single-unit vehicle specific electronics requiring professional installation",
            "Exclude oversized accessories (roof tents, full exhaust systems)",
            "Exclude promotional keywords ('50% off car accessories')",
        ],
    },
    "Pet Supplies": {
        "allocation_weight": 0.15,
        "problem_class": "Embedded pet hair on rugs and upholstery, muddy paws tracked indoors, and rapid pet gulping causing vomiting.",
        "mechanism_of_action": "Dual-edge copper/rubber hair scrapers, silicone paw plungers, maze slow-feeder silicone inserts.",
        "natural_bundle_rationale": "Multi-location necessity: one at front entryway, one in car trunk, one by backyard door.",
        "replenishment_logic": "Multiple locations across home/vehicles, multi-pet households, and hygienic replacement.",
        "target_bundle_units": [2, 3, 5],
        "plausible_aov_range": "$30–$70",
        "structured_seed_templates": [
            {
                "problem": "stubborn embedded dog and cat fur on carpets and car seats",
                "solution": "multi-surface copper and rubber pet hair removal rake",
                "outcome": "instant hair lift without vacuum clogs or sticky tape waste",
                "audience": "pet owners with shedding dogs and cats",
                "usage_context": "couch, car trunk, and bedroom rugs",
                "bundle_rationale": "3-pack multi-location: living room, car, and upstairs",
                "query": "pet hair remover carpet scraper tool multi location 3 pack",
            },
            {
                "problem": "muddy dirty dog paws tracking onto clean carpets after rain",
                "solution": "portable silicone bristle dog paw cleaner cup",
                "outcome": "clean paws in 30 seconds before entering home",
                "audience": "dog owners walking in parks or yards",
                "usage_context": "entryway, back porch, and car rear hatch",
                "bundle_rationale": "2-pack: one for house entryway, one for car adventures",
                "query": "portable dog paw cleaner silicone cup 2 pack entryway car",
            },
            {
                "problem": "dogs gulping kibble too fast leading to bloat and vomiting",
                "solution": "universal spiral slow feeder silicone bowl inserts",
                "outcome": "10x slower eating and improved pet digestion",
                "audience": "owners of food-driven dog breeds",
                "usage_context": "daily mealtime in standard stainless steel bowls",
                "bundle_rationale": "3-pack for multiple pets or rotational washing",
                "query": "slow feeder bowl insert silicone suction cup 3 pack multi pet",
            },
        ],
        "exclusion_rules": [
            "Exclude perishable pet food, raw meat diets, and prescription veterinary medication",
            "Exclude large wooden furniture (heavy cat trees, full dog crates)",
            "Exclude cheap plastic chew toys that pose choking hazards",
            "Exclude promotional keywords ('cheap dog toys', 'free shipping pet')",
        ],
    },
    "Household Essentials": {
        "allocation_weight": 0.15,
        "problem_class": "Drafts, insects, and noise through door gaps; tangled cable clutter; dark closets and stairs causing tripping.",
        "mechanism_of_action": "Twin-cylinder silicone under-door sweeps, magnetic silicone cable clips, magnetic rechargeable motion sensor pucks.",
        "natural_bundle_rationale": "Whole-home room coverage: US single-family homes have multiple exterior doors, closets, and rooms.",
        "replenishment_logic": "Multi-room installation across bedroom, front door, patio, and office stations.",
        "target_bundle_units": [3, 5, 10],
        "plausible_aov_range": "$30–$75",
        "structured_seed_templates": [
            {
                "problem": "cold drafts, dust, and insects entering under exterior doors",
                "solution": "twin draft stopper soundproof weatherstripping seal",
                "outcome": "reduced heating bills, quiet rooms, and zero draft leaks",
                "audience": "homeowners and apartment renters",
                "usage_context": "exterior front, back, and bedroom doors",
                "bundle_rationale": "3-pack or 5-pack for all doors in the home",
                "query": "under door draft stopper twin soundproof seal 3 pack multi door",
            },
            {
                "problem": "tangled messy charging cables dropping behind desks and nightstands",
                "solution": "magnetic silicone cable management clips with adhesive bases",
                "outcome": "cords stay neatly positioned and accessible with one touch",
                "audience": "home office remote workers and tech households",
                "usage_context": "desk, nightstand, and kitchen charging counter",
                "bundle_rationale": "10-pack to organize every workstation and bedroom",
                "query": "magnetic cable clips cord organizer desk nightstand 10 pack",
            },
            {
                "problem": "dark dark closets, pantry shelves, and stairways without hardwired outlets",
                "solution": "ultra-thin magnetic rechargeable motion sensor LED lights",
                "outcome": "hands-free instant illumination upon opening doors",
                "audience": "home organizers and families with kids/seniors",
                "usage_context": "wardrobe closets, dark pantry, under kitchen cabinets",
                "bundle_rationale": "4-pack or 6-pack to illuminate all dark storage areas",
                "query": "rechargeable motion sensor closet lights magnetic slim 4 pack",
            },
        ],
        "exclusion_rules": [
            "Exclude heavy hardwired electrical fixtures requiring licensed electricians",
            "Exclude bulky furniture pieces (sofas, dining tables, mattresses)",
            "Exclude disposable plastic cutlery and paper goods",
            "Exclude promotional discount queries ('clearance household items')",
        ],
    },
    "Tools & Home Improvement": {
        "allocation_weight": 0.15,
        "problem_class": "Dropping screws from ladders, messy caulk beads around sinks/tubs, chaotic garage tool storage.",
        "mechanism_of_action": "Embedded neodymium magnetic wristbands, 3-in-1 silicone sealant finisher scrapers, heavy-duty vinyl-coated steel garage hooks.",
        "natural_bundle_rationale": "Multi-point utility: systematic tool wall hangings (10-pack hooks) or multi-toolbox distribution.",
        "replenishment_logic": "Multi-point workshop installation and accessory replacement (pads, blades, scrapers).",
        "target_bundle_units": [3, 5, 10],
        "plausible_aov_range": "$30–$80",
        "structured_seed_templates": [
            {
                "problem": "heavy ladders, bikes, and garden tools cluttering garage floor",
                "solution": "heavy-duty vinyl-coated steel garage storage wall hooks",
                "outcome": "clean elevated garage wall organization holding up to 50 lbs each",
                "audience": "suburban homeowners and DIY enthusiasts",
                "usage_context": "garage wall studs and shed organization",
                "bundle_rationale": "10-pack multi-hook set for comprehensive tool wall",
                "query": "heavy duty garage storage hooks wall mount steel 10 pack",
            },
            {
                "problem": "moldy peeling caulk and uneven sealant beads leaking around tubs",
                "solution": "3-in-1 silicone caulking tool with stainless scraper and interchangeable pads",
                "outcome": "professional smooth watertight caulk lines without mess",
                "audience": "homeowners doing DIY bathroom and kitchen updates",
                "usage_context": "bathtub, shower, kitchen sink, and window seams",
                "bundle_rationale": "3-piece kit with replacement silicone smoothing radius pads",
                "query": "silicone caulking tool kit sealant finisher scraper set 3 pack",
            },
            {
                "problem": "lost screws, bolts, and drill bits while working on ladders or tight spaces",
                "solution": "breathable neodymium magnetic wristband tool holder",
                "outcome": "hands-free third hand holding screws right on your wrist",
                "audience": "woodworkers, electricians, and home DIYers",
                "usage_context": "ladder repairs, roof fixes, and assembly work",
                "bundle_rationale": "2-pack or 3-pack for main toolbox, car kit, and helper",
                "query": "magnetic wristband holding screws drill bits tools 2 pack",
            },
        ],
        "exclusion_rules": [
            "Exclude expensive heavy power tools (table saws, cordless drills, generators)",
            "Exclude bulky raw building materials (lumber, dry cement bags, drywall sheets)",
            "Exclude single-use cheap disposable hardware without multi-point utility",
            "Exclude promotional discount queries ('cheap tools', '50% off hardware')",
        ],
    },
}

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


# ── Advanced Discovery Strategies (Phase 9) ───────────────────────────────────

@dataclass
class PainFirstDiscovery:
    """Strategy A: Pain-First Discovery mapping consumer problems to commercial search queries."""
    consumer_problem: str
    solution_class: str
    target_category: str
    keyword_variations: list[str]
    bundle_rationale: str
    target_bundle_units: list[int] = field(default_factory=lambda: [3, 5])

    def generate_ad_library_queries(self) -> list[str]:
        """Convert consumer pain into Meta Ad Library keyword queries."""
        queries = []
        for kw in self.keyword_variations:
            norm = kw.lower().strip()
            if norm not in queries:
                queries.append(norm)
        return queries


@dataclass
class BundleFirstDiscovery:
    """Strategy B: Bundle-First Discovery based on natural multi-unit necessity."""
    product_type: str
    utility_mechanism: str  # "daily_rotation", "location_coverage", "consumable_replenishment"
    pack_scenarios: list[int]  # [3, 5, 10]
    target_aov_range: str  # "$30–$90"
    target_category: str
    search_queries: list[str]

    def validate_aov_feasibility(self, estimated_unit_cost: float) -> dict[str, Any]:
        """Verify that 3, 5, or 10 units fit squarely in the $30–$90 consumer sweet spot."""
        scenarios = {}
        for qty in self.pack_scenarios:
            bundle_aov = round(estimated_unit_cost * qty * 0.85, 2)  # typical 15% bundle discount
            scenarios[f"{qty}-pack"] = {
                "quantity": qty,
                "projected_aov_usd": bundle_aov,
                "fits_target_range": 30.0 <= bundle_aov <= 90.0,
            }
        return scenarios


@dataclass
class AdvertiserFirstDiscovery:
    """Strategy C: Advertiser-First Discovery from verified entities and clone graph analysis."""
    seed_advertiser_id: str
    seed_advertiser_name: str
    verified_category: str
    source_product_id: Optional[str] = None
    target_page_urls: list[str] = field(default_factory=list)
    exploration_depth_bound: int = 1
    max_ads_per_advertiser: int = 20


@dataclass
class DiscoveryPerformanceTracker:
    """Task 5: Tracking discovery efficiency, candidate yield, and actual costs across runs."""
    queries_executed: int = 0
    total_ads_returned: int = 0
    unique_product_clusters: int = 0
    new_advertisers_discovered: int = 0
    promising_opportunities: int = 0
    qualified_opportunities: int = 0
    actual_cost_usd: float = 0.0

    @property
    def duplicate_rate(self) -> float:
        if self.total_ads_returned == 0:
            return 0.0
        dupes = max(0, self.total_ads_returned - self.unique_product_clusters)
        return round(dupes / self.total_ads_returned, 3)

    @property
    def cost_per_unique_product(self) -> float:
        if self.unique_product_clusters == 0:
            return 0.0
        return round(self.actual_cost_usd / self.unique_product_clusters, 6)

    @property
    def cost_per_promising(self) -> float:
        if self.promising_opportunities == 0:
            return 0.0
        return round(self.actual_cost_usd / self.promising_opportunities, 6)

    @property
    def cost_per_qualified(self) -> float:
        if self.qualified_opportunities == 0:
            return 0.0
        return round(self.actual_cost_usd / self.qualified_opportunities, 6)

    def to_dict(self) -> dict[str, Any]:
        return {
            "queries_executed": self.queries_executed,
            "total_ads_returned": self.total_ads_returned,
            "unique_product_clusters": self.unique_product_clusters,
            "new_advertisers_discovered": self.new_advertisers_discovered,
            "promising_opportunities": self.promising_opportunities,
            "qualified_opportunities": self.qualified_opportunities,
            "actual_cost_usd": round(self.actual_cost_usd, 6),
            "duplicate_rate": self.duplicate_rate,
            "cost_per_unique_product_usd": self.cost_per_unique_product,
            "cost_per_promising_usd": self.cost_per_promising,
            "cost_per_qualified_usd": self.cost_per_qualified,
        }


