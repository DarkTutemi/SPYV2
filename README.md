# US WIN HUNTER — AI Product Intelligence Engine

Private, evidence-driven discovery of emerging **US physical products** with **natural multi-unit bundle demand** and a plausible **\$30–\$90 AOV**.

> ⚠️ No live data source is connected. The official Meta Ad Library API does **not** return US commercial ads (see `docs/DATA_SOURCE_FEASIBILITY.md`). The system works with **imported** datasets (e.g. Apify Meta Ad Library exports). The only bundled data is a clearly labeled synthetic fixture for demo/tests.

## Run locally (Windows, no Docker required)

```powershell
# Backend
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000
# API docs: http://127.0.0.1:8000/docs   DB: data/winhunter.db (auto-created)

# Frontend (new terminal)
cd frontend
npm install
npm run dev      # http://localhost:3000

# Tests
cd backend; .\.venv\Scripts\python -m pytest -q
```

Import data: dashboard → **Import Data**, or `POST /api/v1/import/file` (JSON/JSONL/CSV). Then **Recompute scores**.
Demo only: `POST /api/v1/import/meta-ads` with `{"source_type":"meta_ad_library","file_path":"<abs path>/backend/tests/fixtures/SYNTHETIC_demo_meta_ads.json","options":{"is_synthetic":true}}` — registered under a `_SYNTHETIC_DEMO` source and badged in Data Health.

## What works (verified)
- 24-table schema with provenance, evidence types and UTC timestamps; SQLite auto-init.
- Idempotent Meta-ad import: raw source records, duplicate detection by ad ID, advertiser dedup by Page ID, product extraction by exact normalized title (no similarity-based merging), geo confidence (USD alone = LOW).
- Deterministic Emergence / Evidence Confidence / Bundle Potential scores with per-component breakdown, configurable weights, weight snapshot, and a "needs verification" flag.
- REST API (products, ranked, report, advertisers, ads, bundles, pain, sources, health, import, score compute).
- 27 automated tests passing; end-to-end import → score → ranking verified against the live server.
- Dashboard: ranking, discovery feed, product intelligence report (with data gaps), advertiser explorer, import, data health.

## Not yet implemented
Daily snapshot/metrics aggregation job (Phase 3), image/semantic fingerprinting & merge-review UI (Phase 2), landing-page bundle extraction (Phase 4), pain/trends adapters (Phase 5, blocked on access), Alembic migrations, Docker Compose, LLM layer. See `docs/IMPLEMENTATION_PLAN.md`.

