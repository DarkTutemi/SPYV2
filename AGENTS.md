# AGENTS.md — US WIN HUNTER (`SPYV2`) Agent Operating Instructions

Authoritative workspace entry point for AI coding and research agents operating inside `SPY v2` (`https://github.com/DarkTutemi/SPYV2`).

---

## 1. Repository & Stack Overview

- **Backend (`backend/`):** Python 3.14, FastAPI, SQLAlchemy 2 Async (`data/winhunter.db` SQLite WAL default; PostgreSQL + Alembic supported via `DATABASE_URL`), Pydantic Settings (`backend/app/core/config.py`).
- **Frontend (`frontend/`):** Next.js 15 App Router, React 19, TypeScript 5, Tailwind CSS 4 (`npm run dev` / `npm run build` on port `3000`).
- **Core Intelligence & Evidence Layer (`backend/app/`):**
  - `engines/scoring.py`: `ScoringEngine` (`balanced` multimodel `v4_balanced_multimodel` + legacy `v3_phase9`), strictly separating candidate observed prices from competitor/category benchmarks and `SCENARIO_PRICE`.
  - `services/evidence_verification.py`: Content-based HTML/JSON-LD inspection (`inspect_artifact_content`) + DB provenance gate (`verify_commercial_evidence_db`, `validate_commercial_evidence_strict_db`).
  - `services/budget_manager.py` & `services/t14_monitoring.py`: Fail-closed Apify budget reservations and frozen `T+14` watchlist monitoring safeguards.
  - Reproducible CLI pipelines (`backend/`): `reconcile_research_candidates.py`, `ingest_dtc_evidence.py` (Batch 1), `ingest_batch2_dtc_evidence.py` (Batch 2), `ingest_batch3_us_opportunities.py` (Batch 3 + v2).

---

## 2. Non-Negotiable Commercial Integrity & Safety Rules

1. **Zero Fabricated Receipts or Synthetic Commercial Evidence:**
   - Never treat mocks, test fixtures (`_SYNTHETIC_DEMO`, `DATA_SOURCE_TYPE.OTHER` without manifest backing), `SCENARIO_PRICE`, `HTTP 200` alone, or self-generated flags as verified commercial pricing.
   - Never infer `"In Stock"` solely from presence of a price; extract explicit availability or set `"UNKNOWN"`.
2. **Strict Competitor vs. Candidate Pricing Isolation:**
   - Competitor retail prices (`offer_role = "competitor_retail_benchmark"`) and corded benchmarks (`offer_role = "category_benchmark_corded"`) must **never** populate `OpportunityScore.observed_single_price_usd` or masquerade as the generic candidate's own price.
   - Always keep separate: **Observed competitor retail price**, **Proposed selling price**, **Equivalent sourcing retail price**, **Supplier FOB quote**, **Landed US cost**, and **Customer AOV (`None` unless order data exists)**.
3. **Zero Unauthorized Spend & `T+14` Freeze:**
   - `APIFY_AUTO_COLLECTION_ENABLED` must stay `false` in development/testing.
   - **NEVER** execute paid Apify runs, paid APIs, or production mutations during offline validation.
   - Keep the `T+14` Watchlist experiment **100% frozen** until **after 01:26:00 ICT on 2026-11-24** (`145` Meta ads, `435` historical snapshots, `0` unapproved spend reservations). See `docs/T14_CONFIGURATION_FREEZE.md`.
4. **No Bot/CAPTCHA Circumvention:**
   - Never bypass CAPTCHAs, Cloudflare Turnstile, PerimeterX, or WAF blocks. Record `HTTP 403` / `HTTP 429` honestly as blocked/unverified.
5. **Preserve Concurrent & Uncommitted Work:**
   - Never silently overwrite uncommitted changes from the user or another Antigravity window/branch. Reconcile and preserve state first.

---

## 3. Canonical Domain Glossary (Keep Terms Consistent)

| Term | Exact Definition | Code / Schema Source |
|---|---|---|
| `OBSERVED_CHECKOUT_PRICE` | Price verified during an actual cart/checkout flow | `PriceEvidenceType.OBSERVED_CHECKOUT_PRICE` |
| `OBSERVED_RETAIL_LISTING_PRICE` | Observed live retail product listing price backed by `SourceRecord` | `PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE` |
| `DTC_MANUFACTURER_OBSERVED_PRICE` | Observed manufacturer storefront price with disk artifact + SHA-256 | `PriceEvidenceType.DTC_MANUFACTURER_OBSERVED_PRICE` |
| `OEM_LIST_PRICE` | Branded OEM catalog / 1-unit factory storefront list price (distinct from bulk FOB & dropship retail) | `PriceEvidenceType.OEM_LIST_PRICE` |
| `SCENARIO_PRICE` | Research hypothesis / target assumption (never counted as observed price) | `PriceEvidenceType.SCENARIO_PRICE` |
| `competitor_retail_benchmark` | Verified rival brand retail price attached for comparison only (`obs_single` excluded) | `ProductOffer.raw_data["offer_role"]` |
| `category_benchmark_corded` | Corded AC benchmark (e.g., `XPOWER A-2`) separated from cordless candidates | `ProductOffer.raw_data["offer_role"]` |
| `equivalent_sourcing_retail_listing` | Verified 1-unit OEM storefront price for an equivalent sourced SKU | `ProductOffer.raw_data["offer_role"]` |
| `VERIFIED_SOURCE_OBSERVATION` | Ad snapshot observed in an authentic provider run | `AdvertisementSnapshot` |
| `DATABASE_DERIVED_SNAPSHOT` | Longitudinal snapshot derived from local DB rows (explicitly non-primary) | `AdvertisementSnapshot` |
| `PARTIALLY_VALIDATED` | Verified external price or competitor benchmark exists, while local DB Meta ads (`0`), FOB, landed cost, and AOV remain unverified | `OpportunityScore.opportunity_status` |
| `RESEARCH_HYPOTHESIS` | Unverified research candidate without external price confirmation (`confidence <= 10`) | `OpportunityScore.opportunity_status` |

---

## 4. Current Workspace State & Known Caveats

- **Authoritative Data Snapshot (`data/winhunter.db`):** `132` products (`84` `PROMISING`, `31` `DISCOVERED`, `11` `PARTIALLY_VALIDATED`, `3` `QUALIFIED_OPPORTUNITY`, `2` `NEEDS_SAFETY_VERIFICATION`, `1` `RESEARCH_HYPOTHESIS`), `72` advertisers, `145` Meta ads, `435` snapshots, `24` collection runs, `256` source records, `95` offers, `365` scores, `0` Apify spend reservations.
- **Unmerged Local Staging Branch:** `chore/antigravity-skills-staging` (`25a6de3`) holds 7 audited `.agents/skills/*` modules pending operator review; do not force-merge onto `master` without approval.
- **Active Uncommitted Blocker (`backend/app/api/temporal.py`):** Lines `189–313` currently hold un-commented pasted text from an operator prompt (`# TASK — AUDIT AND SELECTIVELY INTEGRATE CLAUDE SUPER KIT INTO ANTIGRAVITY`), causing a `SyntaxError` on `app.main` import and `8` `app.main`-dependent pytest modules (+ `1` `test_provenance_and_unified_safety.py` assertion). Do **not** discard without operator confirmation.

---

## 5. Standard Offline Verification Commands

```powershell
# Backend targeted verified suites (does not hit dirty temporal.py)
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_batch3_us_opportunities.py backend\tests\test_batch2_reproducible_ingestion.py backend\tests\test_dtc_pipeline.py backend\tests\test_evidence_lockdown.py backend\tests\test_discovery_provenance_and_quarantine.py backend\tests\test_balanced_scoring.py backend\tests\test_t14_configuration.py -v

# Backend full suite excluding modules blocked solely by uncommitted temporal.py lines 189-313
.\backend\.venv\Scripts\python.exe -m pytest backend\tests --ignore=backend\tests\test_core.py --ignore=backend\tests\test_phase3.py --ignore=backend\tests\test_phase4.py --ignore=backend\tests\test_phase5.py --ignore=backend\tests\test_phase6.py --ignore=backend\tests\test_phase8.py --ignore=backend\tests\test_phase9.py --ignore=backend\tests\test_price_enum_storage.py -v -p no:warnings

# Frontend TypeScript check (offline)
cd frontend; npx tsc --noEmit
```

---

## 6. Authoritative Documentation Map

- Architecture & Status Overview: [`README.md`](README.md), [`docs/LATEST_RUN_STATUS.md`](docs/LATEST_RUN_STATUS.md)
- ECC Harness Audit & Doc Index: [`docs/ECC_OPTIMIZATION_AUDIT.md`](docs/ECC_OPTIMIZATION_AUDIT.md)
- Provenance Manifest & Artifacts: [`docs/run_reports/sanitized_acquisition_manifest.json`](docs/run_reports/sanitized_acquisition_manifest.json)
- Batch Discovery Reports: [`docs/US_WIN_HUNTER_OPPORTUNITIES_BATCH3.md`](docs/US_WIN_HUNTER_OPPORTUNITIES_BATCH3.md), [`docs/US_NEW_DISCOVERIES_REPORT.md`](docs/US_NEW_DISCOVERIES_REPORT.md), [`docs/VERIFIED_US_PRODUCT_EVIDENCE.md`](docs/VERIFIED_US_PRODUCT_EVIDENCE.md)
- Safety & `T+14` Safeguards: [`SECURITY.md`](SECURITY.md), [`docs/T14_CONFIGURATION_FREEZE.md`](docs/T14_CONFIGURATION_FREEZE.md)

