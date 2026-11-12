# Security Policy & Commercial Integrity Safeguards — US WIN HUNTER (`SPYV2`)

## 1. Credential & Repository Secret Hygiene

- All runtime secrets (`META_ACCESS_TOKEN`, `APIFY_API_TOKEN`, `LLM_API_KEY`, `SECRET_KEY`, `DATABASE_URL`) reside strictly in `.env` and are excluded via `.gitignore` (`*.db`, `.env`, `.env.local`, `.env.production`).
- Sanitized HTML captures in `docs/run_reports/artifacts/` pass through `sanitize_html_content()` in `backend/collect_external_product_evidence.py`, which redacts tracking scripts, session/CSRF tokens, cookies, and email PII prior to manifest hashing.

## 2. Fail-Closed Commercial Provenance Controls

- **Content Inspection Gate (`backend/app/services/evidence_verification.py`):**
  - Verifies disk file existence, SHA-256 integrity against `docs/run_reports/sanitized_acquisition_manifest.json`, normalized host/canonical URL binding, product identity presence, exact currency & price presence, and captures stripped of assistant preambles/HTML comments.
  - Rejects WAF interstitials, CAPTCHAs, Cloudflare challenges, Amazon Robot Checks, synthetic/mock signature prefixes (`mock_`, `sha256_mock_sig_`), and mismatched timestamps.
- **Zero Synthetic Promotion:** Unverified manual imports stay quarantined as `RESEARCH_HYPOTHESIS` / `UNVERIFIED_IMPORT` (`evidence_confidence <= 10.0`).

## 3. Financial Spend & Collection Locks (`T+14` Freeze)

- `backend/app/services/budget_manager.py` enforces atomic SQLite/PostgreSQL budget reservations (`apify_spend_reservations`) before any external Apify actor invocation.
- `APIFY_AUTO_COLLECTION_ENABLED` defaults to `false` (`backend/app/core/config.py`).
- Under the `T+14` Configuration Freeze (`docs/T14_CONFIGURATION_FREEZE.md`), automated paid collection remains locked until after **2026-11-24 01:26:00 ICT**.

## 4. Access Controls & Anti-Circumvention

- Automated collectors do **not** bypass CAPTCHAs, Cloudflare Turnstile, PerimeterX, or login gates (`HTTP 403` / `HTTP 429` outcomes are recorded as unverified/blocked).
- Staged skill tooling on `chore/antigravity-skills-staging` must remain sandboxed and unexecuted against production hosts unless reviewed per security audit policy.

## Reporting Issues

Do not commit real tokens, raw session cookies, or unredacted `.db` files when reporting defects. Flag any accidental secret exposure or dirty-file conflict immediately before committing.

