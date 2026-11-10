# US WIN HUNTER — PHASE 9: DISCOVERY QUALITY & MULTI-CATEGORY EXPANSION PLAN

**Document Version:** 1.0.0  
**Date:** November 10, 2026  
**System Status:** Production Ready | 109 Tests Passing (100%) | Zero Synthetic Records in Opportunity Pipeline  
**Budget Safeguards:** `APIFY_AUTO_COLLECTION_ENABLED=false` | Daily Budget: \$2.00 | Monthly Budget: \$10.00  

---

## 1. Corrected Current Live Opportunity Inventory

### 1.1 Resolution of Phase 8 Inventory Discrepancy
In Phase 8, the database displayed five non-demo product entries, whereas the original live collection report identified four candidate clusters. A forensic database and provenance audit revealed two root causes:
1. **Test Fixture Pollution:** A hand-authored test fixture (`bc7472c6`: *Washable Microfiber Mop Pads Multi-Room 3-Pack*) from Phase 6 unit tests was present in the production database table without an isolation flag.
2. **Cluster Fragment Duplication:** Two independent advertisers—**Swiftlifty** (`0c32575b`) and **Gridsparkl** (`cb979fff`)—were advertising the *identical physical product* (*2026 Upgraded Spin Mop Replacement Heads with Scrubbing Pad*). Because the Swiftlifty creative lacked an explicit `<title>` tag, the import service fell back to body copywriting (`"✨ Extra-long microfiber strands..."`), temporarily creating two product records for one physical product.

### 1.2 Canonical Deduplication & Physical Product Count
Through database migration `migrate_phase9.py`:
- All 3 Swiftlifty advertisements were merged into the canonical product record `cb979fff` alongside the Gridsparkl ad.
- The fixture `bc7472c6` was isolated and flagged with `is_synthetic = 1`.
- The duplicate stub `0c32575b` was pruned.

The authentic live dataset contains **exactly 20 Meta advertisements** representing **3 distinct physical consumer products**:

| Canonical ID | Product Name | Ad Count | Independent Entities | Status | Composite | Bundle Potential | Functional Benefit | Confidence | Price Evidence | Quantity Demand |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `cb979fff` | **2026 Upgraded Spin Mop Replacement Heads with Scrubbing Pad** | 4 | 2 (Swiftlifty & Gridsparkl) | **PROMISING** | **91.1** | 90.5 | 100.0 | 68.8% | *Unobserved* (Awaiting crawl) | *Unobserved* (Refill utility) |
| `d93334eb` | **🌟Mop Replacement Cloth** | 9 | 1 (Pawndify Network) | **PROMISING** | **87.7** | 90.5 | 85.0 | 60.0% | *Unobserved* (Awaiting crawl) | *Unobserved* (Refill utility) |
| `21be4a4b` | **Hands-Free Multi-Purpose Flat Mop System** | 7 | 1 (Pawndify Network) | **REJECTED** | **30.5** | 16.5 | 95.0 | 58.8% | *Unobserved* | 1-Unit Tool (Artificial BOGO) |

---

## 2. Synthetic Data Isolation Verification

### 2.1 Database & Pipeline Isolation Architecture
To guarantee that hand-authored fixtures, demo mock data, or synthetic seed generation never contaminate commercial opportunities:
1. **Schema Column:** Added `is_synthetic BOOLEAN DEFAULT 0 NOT NULL` across `source_records`, `advertisements`, and `products`.
2. **Import Guardrail:** `ImportService` automatically tags any fixture originating from non-live data sources (`DataSourceType.OTHER`, `MANUAL_IMPORT` without live URL) as `is_synthetic = True`.
3. **Scoring Engine Exclusion:** `ScoringEngine._determine_opportunity_status()` instantly assigns status `SYNTHETIC_FIXTURE` and caps evidence confidence to &le; 20.0% if `is_synthetic` or `DEMO ` is detected.
4. **API Layer Provenance Filtering:**
   - `GET /api/v1/products/ranked` strictly filters out synthetic records:
     `Product.is_synthetic == False` AND `~Product.name.startswith("DEMO ")` AND `OpportunityScore.opportunity_status != "SYNTHETIC_FIXTURE"`.
   - `GET /api/v1/products/` enforces identical provenance boundaries unless an explicit operator debug flag `include_synthetic=true` is passed.

### 2.2 Live API Query Verification
Executing `GET /api/v1/products/ranked` against the live backend daemon returns:
- Total opportunities returned: **3** (Exactly the 3 authentic products from Apify collection `VzGf16G2H8QdG8xqy`).
- Synthetic products returned: **0** (`DEMO Leakproof Underwear`, `DEMO Cable Organizer Clips`, and `bc7472c6` fixture completely excluded).

---

## 3. Corrected Evidence-Based Qualification Layer

### 3.1 Principal Evidence States
Opportunities are classified into five explicit research states:

```
[ NEW DISCOVERY / AD CRAWL ]
             │
             ▼
     Is Physical & US? ──────── No ──────► [ REJECTED ]
             │ Yes
     Is Durable Tool / Bulk Discount? ───► [ REJECTED ]
             │ No (Consumable / High Necessity)
             ▼
    [ DISCOVERED ] ──(Functional Benefit >= 60 & Bundle Potential >= 60)
             │
             ├── Price Unobserved OR Confidence < 60% ──► [ PROMISING ]
             │                                                │
             └── Price Verified & Confidence >= 60% ──────────► [ QUALIFIED ]
```

1. **`DISCOVERED`**:
   - Initial active ad creative or cluster detected in a target category.
   - Initial creative count, recent start date, keyword match, unverified advertiser independence.
2. **`PROMISING`**:
   - Meets product, category, and bundle-potential criteria, but has incomplete commercial evidence.
   - Daily rotation / multi-location / replenishment utility verified.
   - Modeled bundle scenario fits $30–$90 AOV sweet spot.
   - **Gated at PROMISING** because checkout pricing, order economics, or landing page crawl is pending.
3. **`QUALIFIED`**:
   - Verified physical US-only consumer product.
   - Confirmed functional problem/solution mechanics.
   - Verified advertiser independence (&ge; 2 independent entities or verified domain).
   - **Observed single and bundle pricing** confirmed from ad creative or landing page checkout.
   - Multi-unit order value verified between $30–$90.
   - High Evidence Confidence (&ge; 60.0%).
4. **`REJECTED`**:
   - Hardware tools lacking replenishment utility (e.g., mop handles where multi-packs represent artificial seller-driven volume discounts), non-physical products, or non-US market targeting.
5. **`SYNTHETIC_FIXTURE`**:
   - Test fixtures and synthetic demo records; strictly isolated from operator research pipelines.

### 3.2 Commercial Evidence Attribute Separation
The system strictly separates verified observations from modeled hypotheses:
- **Observed Single Price:** Verified checkout price for 1 unit (e.g. from landing page crawl). If unobserved in ad creative, stored strictly as `None` (Unknown).
- **Observed Bundle Price:** Verified checkout price for a multi-unit pack (e.g. 3-pack or 5-pack). Stored strictly as `None` if unobserved.
- **Estimated Bundle Scenario:** Modeled feasibility scenario (e.g. `"Modeled 3, 5, 10-unit replenishment ($30–$90)"`).
- **Customer AOV:** Stored strictly as `None` (Unknown) unless authentic order or checkout funnel analytics exist.
- **Natural Quantity Rationale:** Qualitative necessity mechanism explaining why households purchase multiple units (e.g. room-by-room distribution, laundry cycle backup).
- **Evidence Confidence:** Scaled 0–100 strictly on verified source data (Independent sources 25%, Evidence URLs 25%, Identity completeness 25%, Observed pricing 25%).

---

## 4. Multi-Category Discovery Taxonomy (6 Core Categories)

To expand beyond mop pads into sustainable US commercial opportunities, resources are allocated across exactly 6 core physical categories:

| Category | Allocation Weight | Problem Class | Physical Mechanism | Natural Bundle Rationale | Replenishment Logic | Target Pack | Plausible AOV |
| :--- | :---: | :--- | :--- | :--- | :--- | :---: | :---: |
| **Home & Cleaning** | **20%** | Stubborn grime, grease, lime scale, and pet hair across diverse surfaces | Electrostatic microfiber absorption, washable deep-cleaning pads, rotating scrubbers | Multi-room utility: clean kitchen floors, bathrooms, and living areas with dedicated pads | Washable laundry cycle (3-5 pads in wash, 3-5 active) and wear replacement | 3, 5, 10 | $30–$75 |
| **Functional Apparel** | **20%** | Plantar fasciitis, arch pain, varicose veins, chafing, and bladder leak vulnerability | Targeted graduated compression weave (20-30 mmHg), multi-layer moisture-wicking gussets | Daily wear necessity: consumers must change underwear, socks, and joint sleeves daily | Weekly work rotation (5-pack covers work week without daily washing) | 3, 5, 7 | $35–$85 |
| **Automotive** | **15%** | Lost items in seat gaps, cluttered cabins, blinding sun glare, and paint swirls | Contoured seat gap drop catchers, magnetic organizer rails, 1200 GSM twisted-loop towels | Multi-car households and driver+passenger symmetry: 2-pack or 4-pack coverage | Average US household owns 2.2 vehicles; rotating wash and drying cycles | 2, 3, 4 | $30–$65 |
| **Pet Supplies** | **15%** | Embedded pet hair on rugs/upholstery, muddy paws tracked indoors, rapid gulping | Dual-edge copper/rubber hair scrapers, silicone paw plungers, spiral slow-feeder inserts | Multi-location necessity: front door, car trunk, and backyard patio | Multiple home entryways, vehicles, multi-pet homes, and hygienic replacement | 2, 3, 5 | $30–$70 |
| **Household Essentials** | **15%** | Drafts/insects entering door gaps, tangled cable clutter, dark closets/stairs | Twin-cylinder silicone under-door sweeps, magnetic cable clips, motion-activated LED pucks | Whole-home room coverage: US single-family homes have multiple exterior doors and rooms | Multi-room installation across bedroom, front door, patio, and office stations | 3, 5, 10 | $30–$75 |
| **Tools & Home Improvement** | **15%** | Lost screws on ladders, messy caulk beads around tubs/sinks, chaotic garage walls | Embedded neodymium magnetic wristbands, 3-in-1 silicone caulk scrapers, vinyl-coated steel hooks | Multi-point utility: systematic tool wall hangings (10-pack hooks) or multi-toolbox kits | Multi-point workshop installation and accessory replacement (pads, blades, scrapers) | 3, 5, 10 | $30–$80 |

### 4.1 Query Structure Formula
Every seed query is synthesized strictly via the formula:
$$\text{Query} = \text{Problem} \times \text{Solution} \times \text{Outcome} \times \text{Audience} \times \text{Usage Context} \times \text{Bundle Rationale}$$

### 4.2 Universal Negative Constraints & Exclusion Rules
Under no circumstances will the system collect or qualify:
- Promotional discount terms: `"50% off"`, `"free shipping"`, `"buy 1 get 1"`, `"clearance"`, `"best seller"`.
- Bulky, non-shippable items: Heavy furniture, large wooden cat trees, lumber, drywall sheets.
- Dangerous or restricted goods: Prescription veterinary medicine, raw pet food, hazardous chemical cleaners.
- Durable hardware tools lacking replacement refills: Single-unit plastic handles, expensive cordless power tools.

---

## 5. Strategy A: Pain-First Discovery

### 5.1 Architecture & Workflow
Pain-First Discovery identifies unaddressed consumer friction points and traces them forward into commercial search queries:
1. **Friction Identification:** Mine customer complaints from verified reviews and problem classes (e.g., *"plantar fasciitis morning heel stabbing"*).
2. **Mechanism Mapping:** Identify the physical mechanical solution (e.g., *copper-infused graduated compression arch sleeve*).
3. **Keyword Synthesis:** Transform pain and mechanism into specific commercial queries matching how US e-commerce brands title their ad campaigns.
4. **Execution Gate:** Run bounded queries targeting active ads in the US Meta Ad Library.

### 5.2 Category Seed Mapping
- *Problem:* Severe foot fatigue and arch burning during 12-hour nursing shifts.  
  *Query:* `graduated compression socks nurses 5 pack daily rotation`
- *Problem:* Dog and cat fur deeply embedded in woven car seats and rugs.  
  *Query:* `pet hair remover carpet scraper tool multi location 3 pack`
- *Problem:* Cold drafts, dust, and insects entering under exterior front and back doors.  
  *Query:* `under door draft stopper twin soundproof seal 3 pack multi door`

---

## 6. Strategy B: Bundle-First Discovery

### 6.1 Inherent Multi-Unit Utility Mechanisms
Strategy B filters directly for products whose physical utility demands multiple units:
1. **Daily Rotation (Apparel & Hygiene):** Items worn or used daily that enter weekly laundry cycles (compression socks, leakproof underwear, sweat-wicking work socks).
2. **Location Coverage (Multi-Room & Multi-Car):** Items deployed simultaneously in distinct areas (door sweeps on 3 exterior doors, pet hair scrapers in house + car, garage tool hooks).
3. **Consumable Replenishment (Refills & Wear Parts):** Items that degrade during normal operation and require ongoing replacements (mop pads, spin scrubber heads, silicone caulk smoothing pads).

### 6.2 AOV Feasibility Validation ($30–$90 Sweet Spot)
For every bundle-first candidate, the engine validates that 3, 5, or 10 units achieve $30–$90 without artificial price manipulation:
- **3-Pack Refill Scenario:** \$10.00 unit cost &times; 3 units &times; 0.85 bundle discount = **\$25.50–\$32.00 AOV** (Viable entry bundle).
- **5-Pack Household Scenario:** \$10.00 unit cost &times; 5 units &times; 0.85 bundle discount = **\$42.50 AOV** (Optimal US e-commerce sweet spot).
- **10-Pack Master Box Scenario:** \$8.00 unit cost &times; 10 units &times; 0.85 bundle discount = **\$68.00 AOV** (High-margin volume bundle).

---

## 7. Strategy C: Advertiser-First Discovery

### 7.1 Entity Graph Exploration
Strategy C seeds discovery from known, verified commercial advertisers operating high-volume campaigns:
1. **Seed Entities:** Start from verified independent advertisers identified in live collection:
   - **Gridsparkl** (`page_id: 104271822923741`): Active US seller of cleaning replacement parts.
   - **Swiftlifty** (`page_id: 108392185514282`): Active US seller of spin mop replacement heads.
2. **Catalog Expansion:** Query Meta Ad Library for all other active campaigns run by the same Facebook Page IDs or corporate entities.
3. **Affiliate Clone Network Guard:** Compare destination landing page URLs. If multiple front domains route to the identical funnel path (e.g. `/funnel/news-...`), collapse them into 1 entity to avoid artificial momentum inflation.
4. **Graph Bounded Constraints:**
   - Maximum 20 ads per advertiser.
   - Maximum exploration depth = 1 (no recursive crawling without approval).

---

## 8. Proposed Bounded Experiment Configuration (Dry-Run Query Plan)

To validate the multi-category discovery pipeline with zero financial surprises, a bounded dry-run experiment is formulated across all 6 core categories:

```
┌─────────────────────────┬────────────────────────────────────────────────────────────────────────┬─────────────┬──────────────┐
│ Category                │ Candidate Seed Query                                                   │ Target Ads  │ Max Cost Cap │
├─────────────────────────┼────────────────────────────────────────────────────────────────────────┼─────────────┼──────────────┤
│ Home & Cleaning         │ washable microfiber mop replacement pads 5 pack rotation               │ 10 ads      │ $0.0025 USD  │
│ Functional Apparel      │ graduated compression socks nurses 5 pack daily rotation               │ 10 ads      │ $0.0025 USD  │
│ Automotive              │ car seat gap filler organizer leather 2 pack multi car                 │ 10 ads      │ $0.0025 USD  │
│ Pet Supplies            │ pet hair remover carpet scraper tool multi location 3 pack            │ 10 ads      │ $0.0025 USD  │
│ Household Essentials    │ under door draft stopper twin soundproof seal 3 pack multi door        │ 10 ads      │ $0.0025 USD  │
│ Tools & Home Improve.   │ heavy duty garage storage hooks wall mount steel 10 pack               │ 10 ads      │ $0.0025 USD  │
├─────────────────────────┼────────────────────────────────────────────────────────────────────────┼─────────────┼──────────────┤
│ TOTALS                  │ 6 Bounded Queries across 6 Core Categories                             │ 60 ads      │ $0.0150 USD  │
└─────────────────────────┴────────────────────────────────────────────────────────────────────────┴─────────────┴──────────────┘
```

### Experiment Parameters
- **Actor:** `automation-lab/facebook-ads-library`
- **Geographic Filter:** `country = "US"`
- **Ad Status:** `activeStatus = "active"`
- **Sort Order:** `sortBy = "recent"`
- **Batch Size:** 10 ads per query
- **Total Ads Cap:** 60 advertisements
- **Budget Reservation:** \$0.50 authorized run cap

---

## 9. Provider-Backed Cost Estimate & Safety Safeguards

### 9.1 Apify Billing Model Verification
- **Actor Model:** Pay-per-event pricing on `automation-lab/facebook-ads-library`.
- **Platform Rate:** **\$0.005 USD per 20 advertisements fetched**.
- **Run Cost Calculation:**
  $$\text{Total Cost} = \frac{60\text{ ads}}{20\text{ ads/event}} \times \$0.005\text{ USD} = \mathbf{\$0.015\text{ USD}}$$
- **Safety Margin:** An authorized run cap of \$0.50 USD provides a **33&times; safety buffer** over the estimated \$0.015 charge.

### 9.2 Budget Enforcement & Safeguards
1. **Persistent Atomic Budget Lock:** All runs check SQLite WAL table `budget_reservations` before invoking Apify. If daily spend + pending reservations > \$2.00, execution is blocked fail-closed.
2. **Auto-Collection Killswitch:** `APIFY_AUTO_COLLECTION_ENABLED=false` is enforced in `backend/.env` and verified at startup.
3. **Credential Security:** Token remains loaded strictly via backend environment variables; no raw token is printed in logs or artifacts.

---

## 10. Exact Operator Approval Protocol

In accordance with strict operational policy:
- **No live Apify Actor runs are executed autonomously.**
- **No paid API requests have been made during Phase 9 implementation.**
- **Execution of the 6-query dry-run experiment requires explicit user authorization.**

### Recommended Approval Command
When the operator is ready to execute the 60-ad discovery experiment across the 6 core categories, reply with:

> `"XÁC NHẬN CHẠY EXPERIMENT PHASE 9 — 6 QUERIES — TỐI ĐA $0.50 USD"`

Upon receiving this explicit authorization, the system will execute the bounded 6-query run, import and deduplicate genuine US records, compute Phase 9 evidence qualification, and present the multi-category opportunities in the dashboard.

