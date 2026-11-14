# US WIN HUNTER (`SPYV2`) — AI Product Intelligence Engine

Evidence-driven discovery and commercial validation platform for emerging **US physical products** with **verifiable problem-solving utility**, **source-backed price provenance**, and **\$30–\$90 AOV** / multi-unit or hero unit economics.

> **Commercial Integrity Mandate:** Zero fabricated receipts, zero mocked prices promoted as observed evidence, and zero unauthorized paid scraping. Official Meta Ad Library API does not return general US commercial ads (`docs/DATA_SOURCE_FEASIBILITY.md`), and the **`T+14` Watchlist Monitoring Experiment is currently FROZEN (`APIFY_AUTO_COLLECTION_ENABLED=false`) until after `2026-11-24 01:26:00 ICT`** (`docs/T14_CONFIGURATION_FREEZE.md`).

For AI agent instructions, glossary definitions, and ECC workspace conventions, see [`AGENTS.md`](AGENTS.md), [`.gemini/GEMINI.md`](.gemini/GEMINI.md), and [`docs/ECC_OPTIMIZATION_AUDIT.md`](docs/ECC_OPTIMIZATION_AUDIT.md).

---

## Architecture & Core Capabilities

### Backend (`backend/` — FastAPI + SQLAlchemy 2 Async)
- **ENGINE A — Advertiser Graph Discovery (`engines/advertiser_graph.py`):** Maps advertisers, Facebook Page IDs, domains, shared products, and Product Ad Share (`Product Active Ads / Advertiser Total Active Ads` — advertising activity metric only, never revenue).
- **ENGINE B — Creative Fingerprinting & Human-Gated Clustering (`engines/fingerprinting.py`):** URL normalization, title normalization, perceptual hashes, candidate duplicate proposals, and reversible splits (`ProductMergeHistory`).
- **ENGINE C — Temporal Advertising Intelligence (`engines/temporal.py`):** 7/14/30/60/90-day tracking distinguishing `VERIFIED_SOURCE_OBSERVATION` from `DATABASE_DERIVED_SNAPSHOT`, flagging missing coverage explicitly.
- **ENGINE D — Pain Discovery & Search Trends (`services/pain_service.py`, `adapters/trends.py`):** Clusters consumer pain language across 5 categories alongside US Google Trends queries.
- **ENGINE E & F — Reverse Competitor Spy & Bundle Intelligence (`adapters/landing_page.py`, `engines/bundle_engine.py`, `services/llm_service.py`):** Extracts landing-page offers, classifies natural multi-unit mechanisms vs artificial seller bulk discounts, and checks \$30–\$90 AOV fit without conflating offered bundles with confirmed purchases.
- **Balanced Multimodel Scoring & Semantic Price Isolation (`engines/scoring.py`):**
  - Scores `MODEL_A_SINGLE_PRODUCT`, `MODEL_B_NATURAL_MULTI_UNIT`, and `MODEL_C_HIGH_AOV_OFFER` under `v4_balanced_multimodel`.
  - **Strict Price Semantics Separation:** `OBSERVED_CHECKOUT_PRICE`, `OBSERVED_RETAIL_LISTING_PRICE`, `DTC_MANUFACTURER_OBSERVED_PRICE`, and `OEM_LIST_PRICE` are separated from `SCENARIO_PRICE` hypotheses, `competitor_retail_benchmark` offers, `category_benchmark_corded` references, and `equivalent_sourcing_retail_listing` offers (`observed_single_price_usd` never inherits competitor retail prices or corded benchmarks).
- **Fail-Closed Provenance & Cost Controls (`services/evidence_verification.py`, `services/budget_manager.py`):**
  - `inspect_artifact_content()` & `verify_commercial_evidence_db()` bind disk HTML/JSON captures to `docs/run_reports/sanitized_acquisition_manifest.json` via SHA-256 digests, stripping assistant preambles/HTML comments and rejecting CAPTCHA/WAF/bot interstitials.
  - `budget_manager.py` enforces atomic Apify reservations (`apify_spend_reservations`) before paid actor launches.
- **Reproducible $0.00 Discovery & Validation Entrypoints (`backend/`):**
  - `reconcile_research_candidates.py` — reconciles manual research concepts as `RESEARCH_HYPOTHESIS` / `SCENARIO_PRICE`.
  - `ingest_dtc_evidence.py` — Batch 1 DTC/OEM captures (`Delta GR150-SP`, `AstroAI 1000813`, `ChomChom Roller`).
  - `ingest_batch2_dtc_evidence.py` — Batch 2 5 multi-category OEM captures (`GENIUS5`, `KPHJ320`, `DLC-2ABC`, `GS23L`, `841230028873`).
  - `ingest_batch3_us_opportunities.py` — Batch 3 + v2 commercial validation (Dog Seat Extender `PD50128`/`PD50128-L`, Showerhead `ZH2087T`, Air Duster `HonkCare 29347`/`Fanttik B10 Pro`/`XPOWER A-2` corded reclassification).

### Frontend (`frontend/` — Next.js 15 + React 19 + TypeScript 5)
App Router pages under `frontend/app/`:
- `/` (Opportunity Ranking), `/emerging` (Emerging Radar), `/analytics` (7–90d Historical Analytics), `/alerts` (Anomaly Feed & Pipeline Runner), `/pain` (Consumer Pain & Trends), `/products` (Discovery Catalog), `/products/[id]` (Product Intelligence Brief & Provenance Offers), `/clusters` (Merge Proposals & Split Audit Trail), `/advertisers` (Advertiser Explorer), `/reviews` (Manual Review Queue), `/import` (Dataset Ingestion), `/health` (System Counts & Synthetic Partitioning), `/settings` (Scoring Weights & Safeguard Config).

---

## Current Database Snapshot (`data/winhunter.db` as of `2026-11-12`)

- **Canonical Products:** `132` (`84` `PROMISING`, `31` `DISCOVERED`, `11` `PARTIALLY_VALIDATED`, `3` `QUALIFIED_OPPORTUNITY`, `2` `NEEDS_SAFETY_VERIFICATION`, `1` `RESEARCH_HYPOTHESIS`)
- **Meta Baseline (Frozen `T+14`):** `72` advertisers, `145` ads, `435` snapshots (`145` `VERIFIED_SOURCE_OBSERVATION` + `290` `DATABASE_DERIVED_SNAPSHOT`)
- **Commercial Provenance Ledger:** `24` collection runs, `256` source records, `95` product offers (`50` `OBSERVED_RETAIL_LISTING_PRICE`, `30` `SCENARIO_PRICE`, `9` `OEM_LIST_PRICE`, `6` `DTC_MANUFACTURER_OBSERVED_PRICE`), `16` bundle offers, `365` opportunity scores
- **Apify Paid Reservations Since Freeze:** `0` (`$0.00 USD`)

---

## Implementation & Verification Matrix

| Category | Component / Workflow | Exact Observed Evidence |
|---|---|---|
| **1. Đã chạy thành công & xác minh thực tế** *(Verified in Runtime / DB / CLI)* | Batches 1–3 ingestion (`ingest_dtc_evidence.py`, `ingest_batch2_dtc_evidence.py`, `ingest_batch3_us_opportunities.py`) + `inspect_artifact_content` + `verify_commercial_evidence_db` | Executed idempotently against `data/winhunter.db` (`31aabef`); all Batch 1–3 manifest entries pass disk SHA-256 + content inspection; `ProductOffer` & `OpportunityScore` persisted accurately |
| **1. Đã chạy thành công & xác minh thực tế** | Products FastAPI Router (`/api/products/{id}/report`, `/api/products/ranked`) & `ScoringEngine(mode="balanced")` | Verified via `TestClient(app.api.products.router)` against `data/winhunter.db` returning `HTTP 200`, `obs_single=None` on competitor-only Batch 3 candidates, and `$51.99` on `HonkCare 29347` |
| **1. Đã chạy thành công & xác minh thực tế** | Frontend TypeScript typecheck (`npx tsc --noEmit`) | Passed with `exit 0` (`2026-11-12`) |
| **2. Đã có tests tự động offline** *(Automated Pytest Coverage)* | Provenance lockdown, DTC/Batch2/Batch3 pipelines, balanced scoring, Apify budget safety, `T+14` freeze, quarantine & temporal integrity (`19` test modules) | `152 passed / 1 failed` in offline pytest run (`2026-11-12`, `$0.00` spend); core Batch 1–3 + scoring/lockdown subset (`7` files) passes `53/53` |
| **3. Chưa được xác minh / Đang bị chặn** *(Unverified, Gated, or Dirty Blocker)* | Full `app.main` FastAPI boot & `8` `app.main`-importing test files (`test_core.py`, `test_phase3..9.py`, `test_price_enum_storage.py`) + `1` test in `test_provenance_and_unified_safety.py` | **Blocked locally** because uncommitted user-editor lines `189–313` in `backend/app/api/temporal.py` cause `SyntaxError` (preserved intentionally pending operator cleanup) |
| **3. Chưa được xác minh / Đang bị chặn** | Frontend ESLint (`npm run lint`) | Currently fails with `26` pre-existing findings (`12` errors, `14` warnings) across 8 `app/` pages |
| **3. Chưa được xác minh / Đang bị chặn** | Live Meta Ad Library US scraping, Amazon/Walmart unproxied scraping, & factory B2B USD FOB/landed US cost quotes | Meta Ad Library returned `HTTP 403`; Amazon/Walmart/Alibaba RFQ/shipping quotes for `PD50128`, `ZH2087T`, and `HonkCare` remain `UNKNOWN` (`$0.00` spend; zero bypassing) |
| **3. Chưa được xác minh / Đang bị chặn** | Visual browser verification of Batch 3 dashboard UI in Chrome DevTools | Not executed for Batch 3 (`CHROME_CONNECTION_ERROR`: Chrome remote debugging `DevToolsActivePort` not active) |
| **4. Mới đề xuất / Đang ở Staging** *(Proposed / Staged Only)* | Selective Agent Skills Suite (7 skills on local branch `chore/antigravity-skills-staging` at `25a6de3`) | Staged locally for security audit; **not** merged or pushed to `master` |
| **4. Mới đề xuất / Đang ở Staging** | Automated `.github/workflows` CI & post-`2026-11-24` `T+14` Watchlist monitoring run | Recommended / scheduled only after clearing `temporal.py` syntax blocker, ESLint errors, and `T+14` freeze window |

---

## Quick Start (Local Development — Offline Safe)

### 1. Environment Configuration
Copy `.env.example` to `.env` (keep `APIFY_AUTO_COLLECTION_ENABLED=false` during offline work).

### 2. Backend & Reproducible Pipelines
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

# Offline test suites (excluding modules currently blocked by uncommitted temporal.py lines 189-313)
.\.venv\Scripts\python -m pytest tests --ignore=tests\test_core.py --ignore=tests\test_phase3.py --ignore=tests\test_phase4.py --ignore=tests\test_phase5.py --ignore=tests\test_phase6.py --ignore=tests\test_phase8.py --ignore=tests\test_phase9.py --ignore=tests\test_price_enum_storage.py -v -p no:warnings

# Reproducible Batch 1-3 ingestion (creates automatic SQLite backup first; $0.00 spend)
.\.venv\Scripts\python ingest_dtc_evidence.py --db ..\data\winhunter.db
.\.venv\Scripts\python ingest_batch2_dtc_evidence.py --db ..\data\winhunter.db
.\.venv\Scripts\python ingest_batch3_us_opportunities.py --db ..\data\winhunter.db

# API Server (requires clean backend/app/api/temporal.py first)
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

### 3. Frontend
```powershell
cd frontend
npm install
npx tsc --noEmit
npm run dev
# Dashboard: http://localhost:3000
```

### 4. Docker Compose (PostgreSQL Production Profile)
```bash
docker compose up -d
# Backend: http://localhost:8000 | Frontend: http://localhost:3000 | PostgreSQL: 5432
```

---

## Non-Negotiable Operating Principles

1. **Ad count != sales:** Advertising volume reflects observed creative presence, never revenue, orders, or ROAS.
2. **Competitor price != candidate price:** Competitor retail benchmarks and corded category benchmarks (`XPOWER A-2`) never populate candidate `observed_single_price_usd`.
3. **Bundle offered != bundle purchased:** Quantity discounts never prove customer AOV without order confirmation.
4. **`first_seen_at` != launch date:** Timestamps record first engine observation only.
5. **Unknown state preservation:** Unverified stock (`UNKNOWN`), missing FOB/landed costs, and uncollected Meta ad data (`UNKNOWN DEMAND EVIDENCE`) are never fabricated or guessed.
6. **Zero CAPTCHA/WAF circumvention:** Gated endpoints fail closed cleanly.

---

## Authoritative Documentation Map & Flagship Engineering

- **Architecture & Status Overview:** [`README.md`](README.md), [`docs/LATEST_RUN_STATUS.md`](docs/LATEST_RUN_STATUS.md)
- **OEM Flagship Product Engineering:** [`docs/angle_development/full_spine_overnight/README.md`](docs/angle_development/full_spine_overnight/README.md) — **V4 — FULL-SPINE ULTRA OVERNIGHT™** (5-Layer Advanced System, 150–160 mL target absorbency, SideSeal™ Guard, 46 cm continuous shield).
- **Provenance Manifest & Artifacts:** [`docs/run_reports/sanitized_acquisition_manifest.json`](docs/run_reports/sanitized_acquisition_manifest.json)
- **Batch Discovery Reports:** [`docs/US_WIN_HUNTER_OPPORTUNITIES_BATCH3.md`](docs/US_WIN_HUNTER_OPPORTUNITIES_BATCH3.md), [`docs/US_NEW_DISCOVERIES_REPORT.md`](docs/US_NEW_DISCOVERIES_REPORT.md), [`docs/VERIFIED_US_PRODUCT_EVIDENCE.md`](docs/VERIFIED_US_PRODUCT_EVIDENCE.md)
- **Safety & T+14 Safeguards:** [`SECURITY.md`](SECURITY.md), [`docs/T14_CONFIGURATION_FREEZE.md`](docs/T14_CONFIGURATION_FREEZE.md)
