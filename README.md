# US WIN HUNTER — AI Product Intelligence Engine

Private, evidence-driven discovery of emerging **US physical products** with **natural multi-unit bundle demand** and a plausible **\$30–\$90 AOV**.

> ⚠️ No unauthorized scraping is performed. The official Meta Ad Library API does **not** return US commercial ads (see `docs/DATA_SOURCE_FEASIBILITY.md`). The system works with legitimate **imported** datasets (e.g. Apify Meta Ad Library exports). Synthetic fixtures for testing and demo are strictly partitioned under a `_SYNTHETIC_DEMO` source.

---

## Quick Start

### 1. Local Development (Windows / macOS / Linux)

```powershell
# Backend Setup
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000
# API docs: http://127.0.0.1:8000/docs
# Local SQLite database: data/winhunter.db (auto-created in WAL mode)

# Frontend Setup (new terminal)
cd frontend
npm install
npm run dev
# Dashboard: http://localhost:3000

# Automated Test Suite (72 tests passing)
cd backend
.\.venv\Scripts\python -m pytest tests/ -v -p no:warnings
```

### 2. Docker Compose (Production Stack with PostgreSQL)

```bash
docker compose up -d
# Backend: http://localhost:8000
# Frontend: http://localhost:3000
# PostgreSQL: port 5432
```

### 3. Alembic Database Migrations

```bash
cd backend
# Generate new migration
.\.venv\Scripts\alembic revision --autogenerate -m "Schema update"

# Apply migrations
.\.venv\Scripts\alembic upgrade head
```

---

## Architectural Engines & Verified Capabilities

### ENGINE A — Advertiser Graph Discovery
- Discovers advertisers and tracks Facebook Page IDs, domains, and active ads.
- Extracts observable relationships (shared landing domains, shared products) with confidence levels.
- Computes **Product Ad Share** (`Product Active Ads / Advertiser Total Active Ads`) as an advertising activity indicator (never a revenue metric).
- Dedicated Advertiser Explorer and graph relationship endpoints.

### ENGINE B — Creative Fingerprinting & Identity Management
- Multi-layered deduplication pipeline: Canonical URL normalization, title stop-word/punctuation stripping, perceptual hashing (pHash, dHash).
- Proposes duplicate candidate pairs for **manual human review** (strictly prevents unauthorized auto-merging).
- Reversible merge and split workflow with full historical audit trails in `ProductMergeHistory`.

### ENGINE C — Temporal Advertising Intelligence
- Daily advertisement status snapshots supporting 7, 14, 30, 60, and 90-day comparison windows.
- Aggregates daily metrics: active ad counts, new ad acceleration, unique advertisers, and collection coverage completeness.
- Emerging Radar detects products with accelerating marketing momentum.
- Low data coverage is explicitly flagged as a warning to prevent false trend spikes.

### ENGINE D — Pain Discovery & Search Trends
- Ingests public consumer discussions and reviews, clustering them across five language groups:
  1. Complaints
  2. Failed workarounds
  3. Purchase intent
  4. Product replacements
  5. Product failures
- Generates customer problem definitions, product hypotheses, and targeted search keywords.
- Google Trends adapter queries US relative search volume trajectories.

### ENGINE E — Reverse Competitor Spy
- Observes competitor landing pages, domains, advertised prices, and creative themes.
- Tracks advertiser ad concentration and newly observed competitor entries.

### ENGINE F — Bundle Intelligence
- Landing page offer extractor identifies bundle quantities, prices, and discount claims.
- Provider-agnostic LLM service (Gemini 2.0 Flash with deterministic heuristic fallbacks) classifies natural bundle mechanisms:
  - Daily rotation (e.g. underwear, socks, towels)
  - Multiple locations (e.g. chargers, night lights, organizers)
  - Frequent usage (e.g. kitchen sponges, cleaning scrubbers)
  - Consumable replenishment
  - Multi-person household / multi-pet use
- Evaluates **\$30–\$90 USD target AOV feasibility** for preferred quantities (3, 5, 10 units).
- Distinguishes observable competitor offers from proof of customer purchase quantities.

### Automated Scheduler & Anomaly Alerts
- In-process background asyncio scheduler executes daily pipeline: Snapshot → Aggregate → Score → Graph → Anomaly Alerts.
- Detects notable events: new advertiser entrants, creative spikes, sudden ad contractions, coverage gaps, and high emergence with low confidence.
- Real-time pipeline execution trigger and execution history in the UI.

---

## Frontend Web Application (Next.js 15)

- **Opportunity Ranking (`/`)**: Products ranked by deterministic composite score with filters for emergence and bundle potential.
- **Emerging Radar (`/emerging`)**: High-momentum products with accelerating ad signals.
- **Historical Analytics (`/analytics`)**: Persistent 7–90 day catalog overview and product deep-dive charts with coverage indicators.
- **Alerts & Pipeline (`/alerts`)**: Anomaly feed with severity badges, mark read/dismiss actions, and manual pipeline runner.
- **Pain & Trends (`/pain`)**: Consumer pain clusters, language breakdown, hypotheses, and Google Trends visualizer.
- **Discovery Feed (`/products`)**: Filterable US product catalog.
- **Product Report (`/products/[id]`)**: Full intelligence brief including natural bundle demand evaluation, \$30–\$90 AOV fit badge, competitor evidence links, and data gaps.
- **Product Clusters (`/clusters`)**: Candidate merge proposals, reviewed clusters, and reversible split audit trail.
- **Advertiser Explorer (`/advertisers`)**: Advertisers, domains, page IDs, and product ad shares.
- **Data Import (`/import`)**: File and dataset ingestion with synthetic test badges.
- **Data Health (`/health`)**: System counts, data source status, and synthetic data partitioning.
- **Configuration & Weights (`/settings`)**: Configurable scoring weights, collection parameters, and integration statuses.

---

## Non-Negotiable Operating Principles

1. **Ad count ≠ sales**: Advertising volume represents observable marketing investment, not verified sales, revenue, or profitability.
2. **Bundle offered ≠ bundle purchased**: Competitor quantity discounts are not treated as verified customer preference without purchase evidence.
3. **first_seen_at ≠ launch date**: Records reflect when the engine first observed an ad, not when a product was invented.
4. **Unknown state preservation**: Incomplete or unverified data is displayed as "Unknown" or "Insufficient evidence", never fabricated.
5. **No CAPTCHA bypass or unauthorized scraping**: Uses documented APIs and imported datasets only.
