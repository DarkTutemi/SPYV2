# US WIN HUNTER — LATEST RUN STATUS & AUDIT TRAIL

**Last Updated:** 2026-11-11T16:55:00 ICT (2026-11-11T09:55:00 UTC)  
**Latest Completed Batch:** TARGETED PATCH — Ad Status Provenance, Billing De-duplication, Scheduler Alignment  
**Branch:** `master`  
**Repository:** https://github.com/DarkTutemi/SPYV2  

---

## 1. Executive Summary & Verification

- **Targeted Patch (Commit Pending):**
  1. *Ad Status Provenance:* `TemporalEngine.create_daily_snapshot()` strictly extracts active/inactive status from authentic `SourceRecord.raw_data` via `extract_ad_status()` supporting all standard Actor output fields (`isActive`, `is_active`, `activeStatus`, `status`). Preserves explicit `False`. Missing or ambiguous status evaluates to `UNKNOWN` and skips snapshot creation (never defaults to `True` or `False`). Authentic timestamps preserved without manufacturing synthetic timestamps.
  2. *Apify Billing Double-Counting Eliminated:* `ApifyProviderAdapter.extract_billing_details()` uses authoritative `usageTotalUsd` as the complete run cost, eliminating double-counting of `eventUsageTotalUsd`. Estimated billing is flagged as unverified (`is_verified=False`). Missing billing retains reservation cap (`HELD_RESERVATION_CAP`).
  3. *Scheduler Collection Status Alignment:* `SchedulerService._execute_pipeline()` aligns status evaluation with `run_collection_cycle()` output (`"completed"` and `"partial"`), replacing the obsolete `"success"` check. Genuine snapshots are strictly associated with specific completed collection runs and authentic `SourceRecord`s. Empty collection cycles (0 records) skip snapshot creation.
- **P0 Hotfix: Source Provenance and Unified Paid Collection Safety (Commit `8757b3a`):**
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
- **Backend Test Pass Rate:** 192/192 total tests passing (0 failures).
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
| **Total Backend Tests** | 192 passed / 0 failed (100% pass rate) |
| **Targeted Patch Tests** | 11 passed / 0 failed (100% pass rate) |
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
- [x] **P0 HOTFIX:** Source provenance verification and unified paid collection safety. (Commit `8757b3a`)
- [x] **TARGETED PATCH:** Ad status provenance, billing de-duplication, and scheduler status alignment. (Commit pending)
