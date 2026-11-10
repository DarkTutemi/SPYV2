# US WIN HUNTER — LATEST RUN STATUS & AUDIT TRAIL

**Last Updated:** 2026-11-10T19:15:00 UTC (2026-11-11T02:15:00 ICT)  
**Latest Completed Batch:** BATCH 2 — Enforce Ingestion Idempotency & Commercial Price Evidence Taxonomy  
**Branch:** `master`  
**Repository:** https://github.com/DarkTutemi/SPYV2  

---

## 1. Executive Summary & Verification

- **Authoritative Scoring Default (Batch 1):** `ScoringEngine` strictly defaults to `mode="balanced"`, producing `weights_version="v4_balanced_multimodel"`. Silent legacy overwrites blocked with `RuntimeError`.
- **Ingestion Pipeline Idempotency (Batch 2):** `backend/ingest_multisource_pilot.py` and `backend/ingest_new_research.py` enforce check-before-insert semantics across all tables (`CollectionRun`, `SourceRecord`, `Product`, `ProductOffer`, `BundleOffer`, `EvidenceLink`).
- **Database Normalization (Batch 2):** Canonical product count deduplicated to exactly **109** products in SQLite `winhunter.db` (purged duplicate `trends_door_draft_stopper`).
- **Commercial Price Taxonomy (Batch 2):** Introduced `PriceEvidenceType` enum separating `OBSERVED_CHECKOUT_PRICE`, `OBSERVED_RETAIL_LISTING_PRICE`, `ADVERTISED_PRICE_ONLY`, `SUPPLIER_LISTED_PRICE`, and `SCENARIO_PRICE`. Removed invalid Google Trends search URLs from price offers; linked verified Amazon US retail benchmark listing ($19.99) and 2-door scenario bundle ($39.99).
- **Test Pass Rate:** 145/145 tests passing (100% pass rate in 111s), including new regression test `test_ingestion_idempotency.py`.

---

## 2. Machine-Readable Audit Metrics

| Metric | Current Production Value |
|---|:---:|
| **Canonical Products** | 109 |
| **Advertisements (Meta Baseline)** | 145 (100% preserved) |
| **T0 Baseline Snapshots** | 145 distinct (290 total, 100% preserved) |
| **Source Records** | 213 |
| **Product Offers** | 50 (Shopify checkout / Amazon retail benchmark) |
| **Bundle Offers** | 6 (5 verified checkout variants + 1 modeled scenario) |
| **Evidence Links** | 35 |
| **Backend Tests Executed** | 145 passed / 0 failed |
| **New Apify Paid Runs (Batch 2)** | 0 |
| **Actual New Spend (Batch 2)** | $0.00 USD |
| **Session Remaining Budget** | $1.9219 USD (from $2.00 authorized ceiling) |
| **T+14 Monitoring Status** | FROZEN (Execution locked until Nov 24, 2026 after 01:26 ICT) |

---

## 3. Work Batch Roadmap

- [x] **BATCH 1:** Fix balanced-scoring default and add regression tests. (Commit `4a6d591`)
- [x] **BATCH 2:** Fix ingestion idempotency and source/price evidence correctness.
- [ ] **BATCH 3:** Fix paid-run budget safety and interruption recovery.
- [ ] **BATCH 4:** Fix frontend commercial classification and honest data presentation.
