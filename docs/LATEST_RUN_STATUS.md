# US WIN HUNTER — LATEST RUN STATUS & AUDIT TRAIL

**Last Updated:** 2026-11-11T12:28:00 ICT (2026-11-11T05:28:00 UTC)  
**Latest Completed Batch:** P0 HOTFIX — Source Provenance & Unified Paid Collection Safety  
**Branch:** `master`  
**Repository:** https://github.com/DarkTutemi/SPYV2  

---

## 1. Executive Summary & Verification

- **Authoritative Scoring Default (Batch 1):** `ScoringEngine` strictly defaults to `mode="balanced"`, producing `weights_version="v4_balanced_multimodel"`. Silent legacy overwrites blocked with `RuntimeError`. (Commit `4a6d591`)
- **Ingestion Pipeline Idempotency (Batch 2):** Enforced check-before-insert semantics across all tables. Canonical product count deduplicated to exactly **109** products in SQLite `winhunter.db`. Commercial price evidence categorized into `OBSERVED_CHECKOUT_PRICE`, `OBSERVED_RETAIL_LISTING_PRICE`, and `SCENARIO_PRICE`. (Commit `23814a5`)
- **Durable Budget Safety & Crash Recovery (Batch 3):** Implemented `ApifyBudgetManager` backed by SQLite table `apify_spend_reservations`. Enforces hard session ceiling ($2.00 max), daily limit ($2.00 max), and monthly limit ($10.00 max). Active in-flight runs block duplicate launches until reconciled. Crash recovery restores orphaned runs from remote Apify status. (Commit `c5f8226`)
- **Frontend Commercial Classification (Batch 4):** Updated `frontend/app/page.tsx` and `frontend/app/products/[id]/page.tsx` to separate Category A (Single-Product), Category B (Natural Multi-Unit & High-AOV), and Category C (Best Overall). Authentic fields displayed: Source Badges, Price Evidence Type Pills (`[Observed Checkout]`, `[Retail Listing Benchmark]`, `[Advertised Price]`, `[Scenario Modeled]`), Core Score, Bundle Upside, and strategic driver/risk notes. (Commit `f592711`)
- **Apify Lifecycle & Spending Safety (Batch 5):** Fixed run loop indentation in `execute_new_research_run.py`. Each actor sequentially executes `RESERVE -> LAUNCH_ATTEMPT -> START -> SAVE ID -> POLL -> WAIT TERMINAL -> READ DATASET -> VERIFY BILLING -> RECONCILE -> COMMIT` before the next provider starts. Implemented DB-level budget lock (`apify_budget_locks`) to eliminate concurrent reservation race conditions. Polling timeouts, provider HTTP 500s, and unknown states transition to `NEEDS_RECONCILIATION` and retain reserved budget rather than prematurely zeroing spend. (Commit `88b2530`)
- **Price Enum Storage & Taxonomy Correctness (Batch 6):** Standardized `PriceEvidenceType` enum storage on uppercase member values with `_missing_` fallback for deserialization safety. Fixed commercial evidence taxonomy: reclassified 44 Shopify storefront variant offers from `OBSERVED_CHECKOUT_PRICE` to `OBSERVED_RETAIL_LISTING_PRICE`. Guarded `POST /api/v1/scores/compute` with HTTP 400 against non-balanced modes. (Commit `51f1eb3`)
- **Temporal Evidence Integrity & Fail-Closed Hardening (Batch 7):**
  1. *Observation Quality Provenance:* Classified all snapshots into `SnapshotObservationQuality` (`GENUINE_SOURCE_OBSERVATION`, `DATABASE_DERIVED_SNAPSHOT`, `UNKNOWN`). Preserved all 145 unique Meta ads and 435 total snapshots (145 genuine T0 baseline, 290 analytical projections).
  2. *Removed Stale Fallback:* `_compute_product_daily_metric` strictly requires genuine source observations for confirmed active ads. Removed the fallback to `advertisements` table when active snapshots are zero; confirmed zero active ads strictly remains zero.
  3. *Scheduler Step 1 Hardening:* Analytical pipeline cycles skip daily snapshot generation when no live Meta collection run was completed.
  4. *Budget Lock Fail-Closed:* `_acquire_db_lock()` checks table existence and raises `BudgetLockError` on any contention/error, refusing reservations without swallowing exceptions.
  5. *Actor Start Hardening:* Ambiguous provider failures (HTTP 5xx, network drops, malformed JSON, missing `data.id`) transition to `NEEDS_RECONCILIATION`, preserve full budget cap, and halt sequence. Missing `usageTotalUsd` in billing check retains budget cap and is never assumed to be verified $0.00. (Commit `472acdf`)
- **P0 Hotfix: Source Provenance and Unified Paid Collection Safety:**
  1. *Sanitized Snapshot Quality Inputs:* Removed caller-controlled `observation_quality` parameter from `/api/v1/temporal/snapshot` and `TemporalEngine.create_daily_snapshot()`. Observation quality is strictly server-derived and evidence-validated (`VERIFIED_SOURCE_OBSERVATION`, `DATABASE_DERIVED_SNAPSHOT`, `UNKNOWN`).
  2. *Run Date & Per-Ad Provenance Validation:* Validates that `CollectionRun.status == COMPLETED` and run execution date matches `snapshot_date`. Scopes snapshot creation strictly to advertisements present in that collection run via `SourceRecord`. Omitted ad IDs remain `UNKNOWN`, never defaulting to `False` / inactive.
  3. *Derived Overwrite Protection:* Subsequent derived snapshot passes strictly preserve existing `VERIFIED_SOURCE_OBSERVATION` evidence.
  4. *Snapshot Audit & T0 Baseline Discrepancy Reconciled:* Audited all 435 snapshots individually against `source_records` in SQLite `data/winhunter.db`. Reconciled 145 T0 baseline snapshots (2026-11-09) to authentic `SourceRecord.collection_run_id` -> `VERIFIED_SOURCE_OBSERVATION`. Classified 2026-11-10 (145) and 2026-11-11 (145) as `DATABASE_DERIVED_SNAPSHOT`. All 145 unique ads preserved.
  5. *Unified Apify Budget Control:* Routed all paid Actor calls (`discover_by_keywords`, `discover_by_advertisers`, `_execute_and_process`) through `ApifyBudgetManager.create_reservation()` and `apify_budget_locks`.
  6. *Eliminated Swallowed Accounting Errors:* `get_status()` and `_calculate_current_spend()` query `ApifyBudgetManager` and fail closed (`status=BLOCKED`, returning ceiling budgets, never 0.0) upon DB contention or error.
  7. *In-Flight Lock Protection:* Unresolved in-flight runs block subsequent paid collection.
  8. *Eliminated Automatic Start Retries & Fallback:* Removed 3x retries on start (immediate classification: 4xx definitive client rejection -> FAILED $0.00 release vs 5xx/network ambiguous -> NEEDS_RECONCILIATION held budget cap). Removed silent secondary actor fallback.
  9. *Polling Timeout & Billing Extraction Safeguards:* Timeouts transition to `NEEDS_RECONCILIATION` holding reservation cap. Missing/None `usageTotalUsd` retains budget cap.
  10. *Scheduler Collection Guardrail:* `SchedulerService.run_collection_cycle()` strictly requires explicit `operator_authorized=True`; internal `force=True` cannot bypass authorization.
- **Backend Test Pass Rate:** 181/181 total tests passing (0 failures).
- **Frontend Build Status:** SUCCESS (16/16 routes compiled cleanly, HTTP 200).

---

## 2. Machine-Readable Audit Metrics

| Metric | Current Production Value |
|---|:---:|
| **Canonical Products** | 109 |
| **Advertisements (Meta Baseline)** | 145 (100% preserved) |
| **Total Snapshots** | 435 (145 Verified Source Observations + 290 Database Derived Snapshots) |
| **Source Records** | 213 |
| **Product Offers** | 50 (Shopify storefront retail listing / Amazon retail benchmark) |
| **Bundle Offers** | 6 (1 storefront variant listing + 5 modeled commercial scenarios) |
| **Evidence Links** | 35 |
| **Commercial Models** | Model A: 82 \| Model B: 26 \| Model C: 1 |
| **Frontend Production Build** | SUCCESS (16/16 routes compiled) |
| **Total Backend Tests** | 181 passed / 0 failed (100% pass rate) |
| **P0 Hotfix Regression Tests** | 14 passed / 0 failed (100% pass rate) |
| **New Apify Paid Runs** | 0 |
| **Actual New Spend** | $0.00 USD |
| **Session Remaining Budget** | $1.9218 USD (from $2.00 authorized ceiling) |
| **T+14 Monitoring Status** | FROZEN (Execution locked until Nov 24, 2026 after 01:26 ICT) |

---

## 3. Work Batch Roadmap (ALL BATCHES COMPLETE)

- [x] **BATCH 1:** Fix balanced-scoring default and add regression tests. (Commit `4a6d591`)
- [x] **BATCH 2:** Fix ingestion idempotency and source/price evidence correctness. (Commit `23814a5`)
- [x] **BATCH 3:** Fix paid-run budget safety and interruption recovery. (Commit `c5f8226`)
- [x] **BATCH 4:** Fix frontend commercial classification and honest data presentation. (Commit `f592711`)
- [x] **BATCH 5:** Fix Apify run lifecycle, serialization lock, and spending safety. (Commit `88b2530`)
- [x] **BATCH 6:** Fix price enum storage, commercial price evidence taxonomy, and snapshot reconciliation. (Commit `51f1eb3`)
- [x] **BATCH 7:** Temporal evidence integrity, zero-fallback elimination, and Apify fail-closed hardening. (Commit `472acdf`)
- [x] **P0 HOTFIX:** Source provenance verification and unified paid collection safety. (Commit pending)
