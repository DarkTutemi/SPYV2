# US WIN HUNTER — LATEST RUN STATUS & AUDIT TRAIL

**Last Updated:** 2026-11-12T15:40:00 ICT (`2026-11-12T08:40:00 UTC`)  
**Latest Completed Batch:** Batch 3 Commercial Validation (`31aabef`) + ECC Harness & Documentation Sync  
**Branch:** `master` (separate staged skills remain unmerged on `chore/antigravity-skills-staging` `25a6de3`)  
**Repository:** https://github.com/DarkTutemi/SPYV2

> **Note:** Section 0 below reflects the current live `data/winhunter.db` and test state as of `2026-11-12`. Sections 1–2 preserve the prior `2026-11-11` remediation checkpoint verbatim for audit continuity.

---

## 0. Current 2026-11-12 Production & Validation Snapshot

- **Batch 1 (`ingest_dtc_evidence.py`, commit `3a62039` / `7ac3264`):** Verified DTC/OEM evidence flows for Delta `GR150-SP` (`$174.70` `OEM_LIST_PRICE`), AstroAI `1000813` (`$9.99` `DTC_MANUFACTURER_OBSERVED_PRICE`), and ChomChom Roller (`$24.99` `DTC_MANUFACTURER_OBSERVED_PRICE` + unobserved merchant bundle), while Etekcity (`EL11`, `HTTP 429`) remains `RESEARCH_HYPOTHESIS`.
- **Batch 2 (`ingest_batch2_dtc_evidence.py`, commit `18d9dff`):** Added 5 multi-category US OEM captures (`GENIUS5` `$69.95`, `KPHJ320` `$39.99`, `DLC-2ABC` `$39.95`, `GS23L` `$41.52`, `841230028873` `$104.00`) under `OEM_LIST_PRICE` and `PARTIALLY_VALIDATED`.
- **Batch 3 + v2 Commercial Validation (`ingest_batch3_us_opportunities.py`, commit `31aabef`):** Isolated competitor retail benchmarks (`RuffRover $159.95`, `Aquasana $99.99`, `AquaBliss $64.99`, `Weddell Duo $79.99`, `Fanttik B10 Pro $49.99`) and corded category benchmark (`XPOWER A-2 $65.00`) from `OpportunityScore.observed_single_price_usd`; captured exact factory records (`Doglemi PD50128`/`PD50128-L`, `ZHONGHE ZH2087T` & matched handle-chamber cartridges, `HonkCare 29347` `$51.99` / `29334` `$37.99`).
- **Live SQLite (`data/winhunter.db`) Counts:** `132` canonical products (`84` `PROMISING`, `31` `DISCOVERED`, `11` `PARTIALLY_VALIDATED`, `3` `QUALIFIED_OPPORTUNITY`, `2` `NEEDS_SAFETY_VERIFICATION`, `1` `RESEARCH_HYPOTHESIS`), `72` advertisers, `145` Meta ads, `435` snapshots (`145` `VERIFIED_SOURCE_OBSERVATION` + `290` `DATABASE_DERIVED_SNAPSHOT`), `24` collection runs, `256` source records, `95` product offers, `16` bundle offers, `365` opportunity scores, `0` Apify spend reservations (`$0.00` spent).
- **Offline Test & Verification Posture:**
  - `152 passed / 1 failed` across 19 non-`app.main` pytest files; `8` `app.main`-importing test files currently fail collection strictly due to uncommitted pasted text in `backend/app/api/temporal.py` lines `189–313` (preserved untouched pending operator cleanup).
  - Frontend `npx tsc --noEmit`: `PASS` (`0` errors). Frontend `npm run lint` (`eslint`): `FAIL` (`26` pre-existing findings: `12` errors, `14` warnings).
  - `T+14` Experiment: **100% FROZEN** until after `2026-11-24 01:26:00 ICT`.

---

## Archive Checkpoint — 2026-11-11T22:05:00 ICT (Historical Baseline Prior to Batches 1–3)

**Last Updated:** 2026-11-11T22:05:00 ICT (2026-11-11T15:05:00 UTC)  
**Latest Completed Batch (Archived):** Body-Level Inspection, Mock Bypass Lockdown, and Database Candidate Reconciliation  

---

## 1. Executive Summary & Verification

- **Elimination of Production Evidence-Verification Bypasses:**
  1. *Disallowed Mock Signature Prefixes:* In `backend/app/services/evidence_verification.py`, prefixes such as `sha256_mock_sig_` and `mock_` are strictly rejected as arbitrary/mock.
  2. *Disallowed Caller-Generated SHA-256 Hashes as Sole Proof:* Verification rejects in-memory caller SHA-256 hashes unless bound to an authentic inspectable acquisition artifact file on disk or an authorized Apify dataset item.
  3. *Removed Trust in HTTP 200 / verified_source Alone:* Flags like `raw_http_status=200` or `verified_source=True` are no longer accepted as proof of capture.
  4. *Expanded Regression Suite:* Added Scenarios 12, 13, and 14 to `backend/tests/test_evidence_lockdown.py` verifying that caller-generated hashes without artifacts, mock signature prefixes, and nonexistent artifact paths fail closed.

- **Response Body-Level Inspection & Artifact Capture:**
  1. *Body Inspection (HTTP 200 != VERIFIED):* Upgraded `backend/collect_external_product_evidence.py` to inspect response bodies. Probes correctly detect that Amazon US returns a 3.7 KB Robot Check / CAPTCHA under HTTP 200, Cloudflare challenges under HTTP 200, and rate-limiting HTTP 429 on deep product links.
  2. *Sanitized Disk Artifacts Saved:* Saved inspectable HTML artifacts for all 9 candidate probes into `docs/run_reports/artifacts/` with cryptographic SHA-256 digests.
  3. *Zero Fabricated Receipts:* Honest reporting reflects `source_verified_count = 0` and `extracted_price = PRICE_UNKNOWN` for bot-gated endpoints.

- **Database Reconciliation of Missing Research Candidates:**
  1. *Idempotent Reconciliation:* Created `backend/reconcile_research_candidates.py` to reconcile the 3 missing candidates:
     - AstroAI Digital Tire Pressure Gauge 150 PSI (ASIN `B01J8880D0`)
     - ChomChom Roller Pet Hair Remover (ASIN `B00BAGT4TK`)
     - Etekcity Digital Luggage Scale 110 lbs (ASIN `B00NW62PCA`)
  2. *Fail-Closed Status in DB:* Stored as `opportunity_status = "RESEARCH_HYPOTHESIS"`, `source_type = MANUAL_IMPORT`, and `price_evidence_type = "SCENARIO_PRICE"` (never observed).
  3. *Balanced Commercial Scoring:* Ran `ScoringEngine(mode="balanced")` to calculate and persist `OpportunityScore` records in SQLite, making them visible on API and dashboard.
  4. *Preserved All Database Invariants:* Exactly 145 unique Meta advertisements and 435 temporal snapshots remain 100% intact. Zero new paid Apify spend ($0.00).

- **Backend Test Suite:** 226 passed / 0 failed (100% pass rate).
- **Frontend Production Build:** SUCCESS (16/16 routes compiled cleanly, HTTP 200).

---

## 2. Machine-Readable Audit Metrics

| Metric | Current Production Value |
|---|:---:|
| **Canonical Products** | 124 (109 baseline + 6 quarantined hypotheses + 9 reconciled candidates) |
| **Source-Verified Products** | **0** (Honest reporting: zero unblocked listing prices via unproxied scripts under $0.00 spend) |
| **Partially Validated Candidates** | 9 (`RESEARCH_HYPOTHESIS`, `SCENARIO_PRICE`, all 9 in SQLite) |
| **Research Hypotheses Quarantined** | 6 (`UNVERIFIED_IMPORT`, `SCENARIO_PRICE`) |
| **Advertisements (Meta Baseline)** | 145 (100% preserved) |
| **Total Snapshots** | 435 (145 Verified Source Observations + 290 Database Derived Snapshots) |
| **Inspectable Disk Artifacts** | 9 HTML capture artifacts in `docs/run_reports/artifacts/` |
| **Product Offers** | 80 (50 baseline observed + 30 scenario price) |
| **Bundle Offers** | 21 (6 baseline + 15 modeled scenario) |
| **Commercial Opportunity Scores** | 227 (All products scored under balanced multimodel engine) |
| **Frontend Production Build** | SUCCESS (16/16 routes compiled) |
| **Total Backend Tests** | 226 passed / 0 failed (100% pass rate) |
| **New Apify Paid Runs** | 0 |
| **Actual Paid Apify Spend** | $0.00 USD |
| **T+14 Experiment Status** | 100% FROZEN (Locked until Nov 24, 2026 after 01:26 ICT) |
