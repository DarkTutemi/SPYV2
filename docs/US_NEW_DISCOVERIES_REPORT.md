# US Win Hunter — Batch 2 Multi-Category Public US Product Discovery Report

**Discovery Batch:** `2026-11-12_multi_category_public_dtc`
**Collection Run ID:** `run_dtc_discovery_batch2_20261112`
**Acquisition Method:** Direct HTTP public request (`$0.00` spend, zero paid Apify runs, zero synthetic data)
**Manifest Reference:** [`docs/run_reports/sanitized_acquisition_manifest.json`](run_reports/sanitized_acquisition_manifest.json)

---

## Executive Summary

Following the scoring & evidence-boundary fix (`7ac3264`), discovery resumed immediately across **5 distinct US product categories** targeting non-overlapping, problem-solving physical products from accessible official OEM/DTC endpoints returning `HTTP 200`, zero bot challenges, valid Schema.org `Product` JSON-LD, explicit `USD` pricing, and explicit Schema.org `InStock` declarations:

| Category | Product & Identity | Observed OEM List Price | Availability (Schema.org) | Commercial Model | Balanced Core / Composite Score | Opportunity Status |
|---|---|---|---|---|---:|---|
| Ergonomics & Sleep Health | **Tempur-Pedic TEMPUR-Symphony Dual-Sided Support Pillow** (`841230028873`) | **$104.00 USD** | `In Stock` (`https://schema.org/InStock`) | `MODEL_A_SINGLE_PRODUCT` | 50.8 / **39.24** | `PARTIALLY_VALIDATED` |
| Automotive & Garage Maintenance | **NOCO GENIUS5 5-Amp 6V/12V Smart Battery Charger** (`GENIUS5`) | **$69.95 USD** | `In Stock` (`http://schema.org/InStock`) | `MODEL_A_SINGLE_PRODUCT` | 50.0 / **38.76** | `PARTIALLY_VALIDATED` |
| Apparel & Home Fabric Care | **Conair ExtremeSteam Handheld Fabric Steamer** (`GS23L`) | **$41.52 USD** | `In Stock` (`http://schema.org/InStock`) | `MODEL_A_SINGLE_PRODUCT` | 50.0 / **38.76** | `PARTIALLY_VALIDATED` |
| Tools & Home DIY | **Kreg Pocket-Hole Jig 320 Woodworking Joinery Kit** (`KPHJ320`) | **$39.99 USD** | `In Stock` (`http://schema.org/InStock`) | `MODEL_A_SINGLE_PRODUCT` | 50.0 / **38.76** | `PARTIALLY_VALIDATED` |
| Kitchen & Culinary Prep | **Cuisinart Mini-Prep Plus 3-Cup Food Processor** (`DLC-2ABC`) | **$39.95 USD** | `In Stock` (`http://schema.org/InStock`) | `MODEL_A_SINGLE_PRODUCT` | 50.0 / **38.76** | `PARTIALLY_VALIDATED` |

All 5 products:
- Passed `inspect_artifact_content` (disk SHA-256 integrity, HTML preamble binding, URL/identity/price/currency match, negative bot-gate check).
- Passed DB-backed `verify_commercial_evidence_db` (`Outcome: VERIFIED`, canonical capture signatures, linked `SourceRecord` + `CollectionRun`).
- Remain honestly capped at **`PARTIALLY_VALIDATED`** (`evidence_confidence = 46.75`) because paid Meta/TikTok advertiser counts (`0` active captured ads), actual customer checkout AOV, and landed supplier COGS remain `UNKNOWN` without paid Meta/Apify runs.

---

## Captured Evidence Artifacts & Digest Provenance

1. **NOCO GENIUS5 (`GENIUS5`)**
   - URL: `https://no.co/genius5`
   - Artifact: [`capture_GENIUS5_noco_dtc.html`](run_reports/artifacts/capture_GENIUS5_noco_dtc.html)
   - Disk SHA-256: `1ef3e101d3a8470c19f9e0f5a59528495bea17c7057caeaabe3ef41d247476fa`
   - Captured At (UTC): `2026-11-12T06:06:24.189755+00:00`
   - Evidence Classification: `OEM_LIST_PRICE` (`$69.95 USD`, `In Stock`)

2. **Kreg Pocket-Hole Jig 320 (`KPHJ320`)**
   - URL: `https://www.kregtool.com/shop/pocket-hole-joinery/pocket-hole-jigs/kreg-pocket-hole-jig-320/KPHJ320.html`
   - Artifact: [`capture_KPHJ320_kreg_dtc.html`](run_reports/artifacts/capture_KPHJ320_kreg_dtc.html)
   - Disk SHA-256: `b3b12fcf61c552c317340b0465e00cf14b9a3eb9014481af806f2f13bd57ed8d`
   - Captured At (UTC): `2026-11-12T06:06:32.505044+00:00`
   - Evidence Classification: `OEM_LIST_PRICE` (`$39.99 USD`, `In Stock`)

3. **Cuisinart Mini-Prep Plus (`DLC-2ABC`)**
   - URL: `https://www.cuisinart.com/mini-prep-plus-food-processor/DLC-2ABC.html`
   - Artifact: [`capture_DLC-2ABC_cuisinart_dtc.html`](run_reports/artifacts/capture_DLC-2ABC_cuisinart_dtc.html)
   - Disk SHA-256: `822ba865dc2ca41db364acada5cd9150a79f87e9860573321d5306cc248daeba`
   - Captured At (UTC): `2026-11-12T06:06:35.149289+00:00`
   - Evidence Classification: `OEM_LIST_PRICE` (`$39.95 USD`, `In Stock`)

4. **Conair ExtremeSteam Handheld Fabric Steamer (`GS23L`)**
   - URL: `https://www.conair.com/handheld-fabric-steamer/GS23L.html?lang=en_US`
   - Artifact: [`capture_GS23L_conair_dtc.html`](run_reports/artifacts/capture_GS23L_conair_dtc.html)
   - Disk SHA-256: `43bfb1b96a7fee7ad7b3381f8fc85552dba08ed2cd6b416fde9e6477c78d8f15`
   - Captured At (UTC): `2026-11-12T06:06:36.406863+00:00`
   - Evidence Classification: `OEM_LIST_PRICE` (`$41.52 USD`, `In Stock`)

5. **Tempur-Pedic TEMPUR-Symphony Pillow (`841230028873`)**
   - URL: `https://www.tempurpedic.com/shop-pillows/symphony-pillow/v/1381/`
   - Artifact: [`capture_841230028873_tempurpedic_dtc.html`](run_reports/artifacts/capture_841230028873_tempurpedic_dtc.html)
   - Disk SHA-256: `a31a59812912b6eff9bc09af5f08bbe566d79e2fddc96e14bfe19f5f1fbdbe89`
   - Captured At (UTC): `2026-11-12T06:06:38.211579+00:00`
   - Evidence Classification: `OEM_LIST_PRICE` (`$104.00 USD`, `In Stock`)

---

## Database & Operational Invariants Verified

- **Total Products:** `129` (`124` prior + `5` deduplicated Batch 2 captures)
- **Meta Advertisements:** `145` (unchanged)
- **Advertisement Snapshots:** `435` (`145 VERIFIED_SOURCE_OBSERVATION` + `290 DATABASE_DERIVED_SNAPSHOT`, unchanged)
- **Frozen `T+14` Experiment:** Untouched
- **Apify Spend Reservations / Paid Spend:** `0` (`$0.00 USD`)
- **Non-Accessible Public Endpoints Honestly Recorded:** Shopify `/products/*` rate limits (`HTTP 429` on Etekcity, Fanttik, ThermoWorks, Zulay, Uproot, Loop, Renpho, Leatherman retry, HOTO, Simplehuman) and Cloudflare Turnstile/challenges (`HTTP 403` on Bissell, Oster, Sunbeam, Coleman, Hydro Flask, SharkClean) were observed honestly without circumvention.
