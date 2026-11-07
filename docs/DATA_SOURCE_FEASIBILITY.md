# Data Source Feasibility Audit

Audit date: 2026-11-07. Status legend: **CONFIRMED** = verified from official docs; **ASSUMED** = based on docs/third-party reports, not tested by us; **UNTESTED** = no credentials available.

> No live collector has been run. No credentials are configured. Every statement about data access below is a documentation finding, not a tested result.

## Summary matrix

| Source | US commercial ads? | Official API | Cost | Recurring collection | Decision |
|---|---|---|---|---|---|
| Meta Ad Library API (`/ads_archive`) | **No** — commercial ads are only returned for ads delivered in EU/UK (DSA). US-only commercial ads are not returned. | Yes (ID verification + app) | Free | Yes, but not for our use case | Adapter for EU/UK + political only; **not a US discovery source** |
| Meta Ad Library web UI | Yes (visible) | No | — | No sanctioned programmatic route | Manual research only; no scraping by us |
| Apify Meta Ad Library actors (e.g. themineworks wrapper) | Yes (scrapes web UI) | Apify API | ~$3–6 / 1K ads + platform plan | Yes | **Import-compatible adapter**; paid runs require operator approval; compliance risk is the provider's and operator's to accept |
| TikTok Creative Center | Top Ads visible for US | No public API for Top Ads; Commercial Content API is researcher/EU-oriented, application-gated | — | No | Deferred; file import only |
| Reddit API | n/a (pain discovery) | Yes, OAuth, 100 QPM free | Commercial use requires written approval / enterprise contract | Yes if approved | **Blocked for commercial use** until operator obtains approval; adapter + file import |
| Google Trends | n/a (demand signal) | Official API in gated alpha; `trendspy`/`trendspyg` are unofficial | Free | Fragile (rate limits) | Adapter planned (Phase 5); results labeled as unofficial |
| Amazon PA-API / Creators API | n/a | Yes, needs active Associates account w/ qualifying sales | Free if qualified | Yes | **Blocked** — operator has no qualifying account; no review scraping |
| Landing pages (crawl4ai) | Product/offer/bundle extraction from public pages | n/a | Free, self-hosted | Yes, respecting robots.txt | Evaluate further (Phase 2/4) |

## Key findings

1. **The official Meta Ad Library API does not provide US commercial-ad discovery.** This is the single most important constraint. The platform therefore treats *imported datasets* (operator-exported, or Apify-provider datasets) as the primary advertising input.
2. `ad_snapshot_url` from the API links to a rendered ad, not a raw creative file; spend/impressions are only for political/issue ads.
3. Ad counts from any source are **activity signals**, never sales, revenue, spend or ROAS.
4. Missing records in a later collection do not imply an ad stopped — coverage must be tracked per run (`collection_runs.coverage_notes`).

## Blockers

| # | Blocker | Workaround implemented |
|---|---|---|
| B1 | No US commercial-ad API from Meta | JSON/CSV/JSONL import pipeline accepting Apify/Meta field shapes (`/api/v1/import/*`) |
| B2 | No Apify token; paid runs need approval | Import adapter for Apify dataset exports; live client deferred |
| B3 | Reddit commercial-use approval | Schema + API for pain clusters; file import pathway |
| B4 | No Amazon Associates qualification | None; source disabled |
| B5 | Docker not installed on dev machine | SQLite + in-process jobs for local dev; PostgreSQL URL supported via `DATABASE_URL` |

