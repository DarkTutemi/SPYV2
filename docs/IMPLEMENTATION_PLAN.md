# Implementation Plan

| Phase | Content | Status |
|---|---|---|
| 0 | Feasibility + architecture docs | Done |
| 1 | Backend, schema, import pipeline, explorers API, scoring, tests, frontend slice | In progress — see README "What works" |
| 2 | Title normalization, imagededup pHash, sentence-transformers similarity, merge/split review UI, advertiser graph expansion | Not started |
| 3 | Daily snapshot job, `product_daily_metrics` aggregation, coverage-aware 7/14/30/60/90 windows, alerts | Not started (schema ready) |
| 4 | crawl4ai landing-page bundle extraction, mechanism classification (LLM, labeled as inference) | Not started (schema + scoring ready) |
| 5 | Pain clustering, Trends adapter, cross-source confidence | Blocked on source approvals (see feasibility) |

Next actions: Alembic baseline migration; snapshot job writing `advertisement_snapshots` on every import; daily metrics aggregator.

