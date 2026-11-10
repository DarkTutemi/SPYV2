# US WIN HUNTER — LATEST RUN STATUS & AUDIT TRAIL

**Last Updated:** 2026-11-10T19:46:00 UTC (2026-11-11T02:46:00 ICT)  
**Latest Completed Batch:** BATCH 5 — Apify Lifecycle & Spending Safety  
**Branch:** `master`  
**Repository:** https://github.com/DarkTutemi/SPYV2  

---

## 1. Executive Summary & Verification

- **Authoritative Scoring Default (Batch 1):** `ScoringEngine` strictly defaults to `mode="balanced"`, producing `weights_version="v4_balanced_multimodel"`. Silent legacy overwrites blocked with `RuntimeError`. (Commit `4a6d591`)
- **Ingestion Pipeline Idempotency (Batch 2):** Enforced check-before-insert semantics across all tables. Canonical product count deduplicated to exactly **109** products in SQLite `winhunter.db`. Commercial price evidence categorized into `OBSERVED_CHECKOUT_PRICE`, `OBSERVED_RETAIL_LISTING_PRICE`, and `SCENARIO_PRICE`. (Commit `23814a5`)
- **Durable Budget Safety & Crash Recovery (Batch 3):** Implemented `ApifyBudgetManager` backed by SQLite table `apify_spend_reservations`. Enforces hard session ceiling ($2.00 max), daily limit ($2.00 max), and monthly limit ($10.00 max). Active in-flight runs block duplicate launches until reconciled. Crash recovery restores orphaned runs from remote Apify status. (Commit `c5f8226`)
- **Frontend Commercial Classification (Batch 4):** Updated `frontend/app/page.tsx` and `frontend/app/products/[id]/page.tsx` to separate Category A (Single-Product), Category B (Natural Multi-Unit & High-AOV), and Category C (Best Overall). Authentic fields displayed: Source Badges, Price Evidence Type Pills (`[Observed Checkout]`, `[Retail Listing Benchmark]`, `[Advertised Price]`, `[Scenario Modeled]`), Core Score, Bundle Upside, and strategic driver/risk notes.
- **Apify Lifecycle & Spending Safety (Batch 5):** Fixed run loop indentation in `execute_new_research_run.py`. Each actor sequentially executes `RESERVE -> LAUNCH_ATTEMPT -> START -> SAVE ID -> POLL -> WAIT TERMINAL -> READ DATASET -> VERIFY BILLING -> RECONCILE -> COMMIT` before the next provider starts. Implemented DB-level budget lock (`apify_budget_locks`) to eliminate concurrent reservation race conditions. Polling timeouts, provider HTTP 500s, and unknown states transition to `NEEDS_RECONCILIATION` and retain reserved budget rather than prematurely zeroing spend. (10/10 regression tests passing).
- **Backend Test Pass Rate:** 155/155 total tests passing.

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
| **Commercial Models** | Model A: 82 \| Model B: 26 \| Model C: 1 |
| **Frontend Production Build** | SUCCESS (16/16 routes compiled) |
| **Total Backend Tests** | 155 passed / 0 failed |
| **New Apify Paid Runs (Batches 1–5)** | 0 |
| **Actual New Spend (Batches 1–5)** | $0.00 USD |
| **Session Remaining Budget** | $1.9218 USD (from $2.00 authorized ceiling) |
| **T+14 Monitoring Status** | FROZEN (Execution locked until Nov 24, 2026 after 01:26 ICT) |

---

## 3. Work Batch Roadmap

- [x] **BATCH 1:** Fix balanced-scoring default and add regression tests. (Commit `4a6d591`)
- [x] **BATCH 2:** Fix ingestion idempotency and source/price evidence correctness. (Commit `23814a5`)
- [x] **BATCH 3:** Fix paid-run budget safety and interruption recovery. (Commit `c5f8226`)
- [x] **BATCH 4:** Fix frontend commercial classification and honest data presentation. (Commit `f592711`)
- [x] **BATCH 5:** Fix Apify run lifecycle, serialization lock, and spending safety.
- [ ] **BATCH 6:** Fix price enum storage, commercial price evidence taxonomy, and snapshot reconciliation.
