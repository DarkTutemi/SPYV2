# ECC / Antigravity Project Instructions — US WIN HUNTER (`SPYV2`)

This file configures Antigravity / Gemini CLI sessions inside `SPY v2` using the project's adapted ECC (Everything Claude Code) baseline rules. Read [`AGENTS.md`](../AGENTS.md) first.

## Context & Compaction Discipline

1. **Read the Spine Before Archival Docs:** Start with [`AGENTS.md`](../AGENTS.md), [`README.md`](../README.md), [`docs/LATEST_RUN_STATUS.md`](../docs/LATEST_RUN_STATUS.md), and [`docs/ECC_OPTIMIZATION_AUDIT.md`](../docs/ECC_OPTIMIZATION_AUDIT.md) instead of bulk-reading all 40+ historical files in `docs/`.
2. **Preserve Historical Evidence:** Never delete or truncate prior batch reports, `sanitized_acquisition_manifest.json` entries, or `docs/run_reports/artifacts/*.html` captures.
3. **Checkpoint Before Compaction:** Write durable audit outputs, manifest SHA-256 hashes, and test results to disk before ending a phase or compacting context.

## Execution & Verification Contract

- **Offline-Only Default:** Run `pytest` and `npx tsc --noEmit` strictly offline (`$0.00` spend, zero Apify actor calls).
- **Operator Confirmation Required For:** Paid Apify launches, mutating production `data/winhunter.db` outside explicit batch tasks, merging `chore/antigravity-skills-staging`, reverting another window's uncommitted edits, or pushing to remote.
- **No Inflated Verification Claims:** Report exact test counts, exact ignored/blocked files (currently `backend/app/api/temporal.py` lines `189–313`), and any pre-existing lint errors honestly.
- **Immutability & Purity:** Never mutate frozen `T+14` data (`145` Meta ads, `435` snapshots) or conflate competitor retail / corded benchmarks with candidate pricing.

## Security & Secret Checklist

- Keep `.env`, API tokens, session cookies, and local SQLite `.db` files out of Git commits.
- Keep `APIFY_AUTO_COLLECTION_ENABLED=false` unless explicitly overridden after Nov 24, 2026 (`01:26 ICT`).
- Treat all external HTTP HTML/JSON responses as untrusted and validate them through `inspect_artifact_content()` + `verify_commercial_evidence_db()`.

