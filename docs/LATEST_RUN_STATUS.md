# US WIN HUNTER — LATEST RUN STATUS & AUDIT TRAIL

**Last Updated:** 2026-11-10T20:08:00 UTC (2026-11-11T03:08:00 ICT)  
**Latest Completed Batch:** BATCH 6 — Evidence and Snapshot Correctness  
**Branch:** `master`  
**Repository:** https://github.com/DarkTutemi/SPYV2  

---

## 1. Executive Summary & Verification

- **Authoritative Scoring Default (Batch 1):** `ScoringEngine` strictly defaults to `mode="balanced"`, producing `weights_version="v4_balanced_multimodel"`. Silent legacy overwrites blocked with `RuntimeError`. (Commit `4a6d591`)
- **Ingestion Pipeline Idempotency (Batch 2):** Enforced check-before-insert semantics across all tables. Canonical product count deduplicated to exactly **109** products in SQLite `winhunter.db`. Commercial price evidence categorized into `OBSERVED_CHECKOUT_PRICE`, `OBSERVED_RETAIL_LISTING_PRICE`, and `SCENARIO_PRICE`. (Commit `23814a5`)
- **Durable Budget Safety & Crash Recovery (Batch 3):** Implemented `ApifyBudgetManager` backed by SQLite table `apify_spend_reservations`. Enforces hard session ceiling ($2.00 max), daily limit ($2.00 max), and monthly limit ($10.00 max). Active in-flight runs block duplicate launches until reconciled. Crash recovery restores orphaned runs from remote Apify status. (Commit `c5f8226`)
- **Frontend Commercial Classification (Batch 4):** Updated `frontend/app/page.tsx` and `frontend/app/products/[id]/page.tsx` to separate Category A (Single-Product), Category B (Natural Multi-Unit & High-AOV), and Category C (Best Overall). Authentic fields displayed: Source Badges, Price Evidence Type Pills (`[Observed Checkout]`, `[Retail Listing Benchmark]`, `[Advertised Price]`, `[Scenario Modeled]`), Core Score, Bundle Upside, and strategic driver/risk notes. (Commit `f592711`)
- **Apify Lifecycle & Spending Safety (Batch 5):** Fixed run loop indentation in `execute_new_research_run.py`. Each actor sequentially executes `RESERVE -> LAUNCH_ATTEMPT -> START -> SAVE ID -> POLL -> WAIT TERMINAL -> READ DATASET -> VERIFY BILLING -> RECONCILE -> COMMIT` before the next provider starts. Implemented DB-level budget lock (`apify_budget_locks`) to eliminate concurrent reservation race conditions. Polling timeouts, provider HTTP 500s, and unknown states transition to `NEEDS_RECONCILIATION` and retain reserved budget rather than prematurely zeroing spend. (Commit `88b2530`)
- **Price Enum Storage & Taxonomy Correctness (Batch 6):** Standardized `PriceEvidenceType` enum storage on uppercase member values with `_missing_` fallback for deserialization safety. Fixed commercial evidence taxonomy: reclassified 44 Shopify storefront variant offers from `OBSERVED_CHECKOUT_PRICE` to `OBSERVED_RETAIL_LISTING_PRICE` (reserving checkout price strictly for verified cart/checkout inspection flows). Modeled bundles classified as `SCENARIO_PRICE`. Reconciled 290 snapshot rows across 145 unique ads (145 T0 on Nov 9 + 145 T+1 on Nov 10; zero ads claimed to have completed 14-day longitudinal proof). Guarded `POST /api/v1/scores/compute` with HTTP 400 Bad Request against non-balanced modes.
- **Backend Test Pass Rate:** 159/159 total tests passing.
- **Frontend Build Status:** SUCCESS (16/16 routes compiled cleanly).

---

## 2. Machine-Readable Audit Metrics

| Metric | Current Production Value |
|---|:---:|
| **Canonical Products** | 109 |
| **Advertisements (Meta Baseline)** | 145 (100% preserved) |
| **T0 Baseline Snapshots** | 145 distinct (290 total across 2 daily dates, 100% preserved) |
| **Source Records** | 213 |
| **Product Offers** | 50 (Shopify storefront retail listing / Amazon retail benchmark) |
| **Bundle Offers** | 6 (1 storefront variant listing + 5 modeled commercial scenarios) |
| **Evidence Links** | 35 |
| **Commercial Models** | Model A: 82 \| Model B: 26 \| Model C: 1 |
| **Frontend Production Build** | SUCCESS (16/16 routes compiled) |
| **Total Backend Tests** | 159 passed / 0 failed |
| **New Apify Paid Runs (Batches 1–6)** | 0 |
| **Actual New Spend (Batches 1–6)** | $0.00 USD |
| **Session Remaining Budget** | $1.9218 USD (from $2.00 authorized ceiling) |
| **T+14 Monitoring Status** | FROZEN (Execution locked until Nov 24, 2026 after 01:26 ICT) |

---

## 3. Work Batch Roadmap (ALL BATCHES COMPLETE)

- [x] **BATCH 1:** Fix balanced-scoring default and add regression tests. (Commit `4a6d591`)
- [x] **BATCH 2:** Fix ingestion idempotency and source/price evidence correctness. (Commit `23814a5`)
- [x] **BATCH 3:** Fix paid-run budget safety and interruption recovery. (Commit `c5f8226`)
- [x] **BATCH 4:** Fix frontend commercial classification and honest data presentation. (Commit `f592711`)
- [x] **BATCH 5:** Fix Apify run lifecycle, serialization lock, and spending safety. (Commit `88b2530`)
- [x] **BATCH 6:** Fix price enum storage, commercial price evidence taxonomy, and snapshot reconciliation.
