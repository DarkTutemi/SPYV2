# US WIN HUNTER — LATEST RUN STATUS & AUDIT TRAIL

**Last Updated:** 2026-11-10T19:25:00 UTC (2026-11-11T02:25:00 ICT)  
**Latest Completed Batch:** BATCH 3 — Durable Apify Budget Safety, In-Flight Reservation & Crash Recovery  
**Branch:** `master`  
**Repository:** https://github.com/DarkTutemi/SPYV2  

---

## 1. Executive Summary & Verification

- **Authoritative Scoring Default (Batch 1):** `ScoringEngine` strictly defaults to `mode="balanced"`, producing `weights_version="v4_balanced_multimodel"`. Silent legacy overwrites blocked with `RuntimeError`. (Commit `4a6d591`)
- **Ingestion Pipeline Idempotency (Batch 2):** Enforce check-before-insert semantics across all tables. Canonical product count deduplicated to exactly **109** products in SQLite `winhunter.db`. Commercial price evidence categorized into `OBSERVED_CHECKOUT_PRICE`, `OBSERVED_RETAIL_LISTING_PRICE`, and `SCENARIO_PRICE`. (Commit `23814a5`)
- **Durable Budget Safety & Crash Recovery (Batch 3):** Implemented `ApifyBudgetManager` backed by SQLite table `apify_spend_reservations`. Enforces hard session ceiling ($2.00 max), daily limit ($2.00 max), and monthly limit ($10.00 max). Active in-flight runs block duplicate launches until reconciled. Missing or zero billing conservatively defaults to the reserved amount. Crash recovery restores orphaned runs from remote Apify status.
- **Test Pass Rate:** 150/150 total tests passing (including 5 new budget safety tests in `test_apify_budget_safety.py`).

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
| **Budget Safety Tests** | 5 passed / 0 failed (`test_apify_budget_safety.py`) |
| **Total Backend Tests** | 150 passed / 0 failed |
| **New Apify Paid Runs (Batch 3)** | 0 |
| **Actual New Spend (Batch 3)** | $0.00 USD |
| **Session Remaining Budget** | $1.9218 USD (from $2.00 authorized ceiling) |
| **T+14 Monitoring Status** | FROZEN (Execution locked until Nov 24, 2026 after 01:26 ICT) |

---

## 3. Work Batch Roadmap

- [x] **BATCH 1:** Fix balanced-scoring default and add regression tests. (Commit `4a6d591`)
- [x] **BATCH 2:** Fix ingestion idempotency and source/price evidence correctness. (Commit `23814a5`)
- [x] **BATCH 3:** Fix paid-run budget safety and interruption recovery.
- [ ] **BATCH 4:** Fix frontend commercial classification and honest data presentation.
