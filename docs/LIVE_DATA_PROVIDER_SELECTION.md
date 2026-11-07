# US WIN HUNTER — Live Data Provider Selection & Technical Evaluation

**Document Version:** 1.0  
**Phase:** 6 — Autonomous Live Discovery Engine  
**Target Market:** United States (US Only)  
**Evaluated Date:** 2026-11-07  

---

## 1. Executive Summary & Objective

The **US WIN HUNTER Real-World Capability Audit** established that the official Meta Ad Library Graph API (`graph.facebook.com/v21.0/ads_archive`) deliberately restricts commercial product advertising in the United States, granting API access exclusively for political, electoral, and social issue ads. 

To power an autonomous, evidence-backed discovery pipeline from an empty production database without relying on fabricated mock records or manual file imports, we evaluated four commercial scraper providers operating on the Apify platform.

### Selected Architecture
- **Primary Live Provider:** `automation-lab/facebook-ads-library`
- **Fallback Live Provider:** `curious_coder/facebook-ads-library-scraper`
- **Fail-Safe Mechanism:** Automatic fallback upon primary error/rate limit, with fail-closed spend caps and strict US geographic verification.

---

## 2. In-Depth Comparative Matrix

| Evaluation Dimension | Primary: `automation-lab/facebook-ads-library` | Fallback: `curious_coder/facebook-ads-library-scraper` | Candidate 3: `vero-api/facebook-ad-library-scraper` | Candidate 4: `agenttoolworks/ad-library-scraper` |
| :--- | :--- | :--- | :--- | :--- |
| **Current Availability** | Active & Maintained (Apify Verified) | Active & Stable (Apify Veteran) | Active | Active |
| **US Commercial Ad Access** | Full via direct web runner | Full via direct search URLs | Full | Partial (Cross-network) |
| **Native Keyword Search** | Direct `searchQueries: ["keyword"]` | Via `startUrls` construction | Direct `search_term` | Aggregated keywords |
| **Advertiser Page Lookup** | Direct `pageUrls: ["url"]` | Direct `pageIds: ["id"]` | Via profile URL | Via account ID |
| **Country Targeting Filter** | Hard `country: "US"` parameter | Query string `country=US` | Filter param `country: "US"` | Generic platform param |
| **Native Creative Extraction** | Image/Video URLs, CTA, Carousel | Link images, video sources, text | High-res media URLs | Thumbnails, generic copy |
| **Landing Page Domain** | Direct `linkUrl` & CTA destination | Direct `link_url` | Extracted redirect link | Intermediate tracking URL |
| **Ad Delivery Dates** | `startDate`, `endDate`, `isActive` | `ad_delivery_start_time`, status | ISO timestamps | Timestamp strings |
| **Cost Profile** | ~$1.00 – $1.50 per 1,000 ads | ~$0.75 – $1.00 per 1,000 ads | ~$1.50 – $2.00 per 1,000 ads | ~$0.50 / run + compute |
| **Pagination Handling** | Cursor-based automatic scrolling | Dataset-chunked streaming | Offset pagination | Polled batches |
| **Error / Anti-Bot Handling** | Residential US Proxy rotation | Datacenter / Residential proxy | Proxy pool | Built-in proxy |
| **Verdict** | **SELECTED PRIMARY** | **SELECTED FALLBACK** | REJECTED (Cost / schema instability) | REJECTED (High latency / loose schemas) |

---

## 3. Primary Provider Deep-Dive: `automation-lab/facebook-ads-library`

### 3.1 Input Mapping Specification
The actor accepts a clean JSON schema that directly supports autonomous discovery:

```json
{
  "searchQueries": ["magnetic socket organizer", "washable rotation couch cover"],
  "pageUrls": ["https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&view_all_page_id=1092837482"],
  "country": "US",
  "activeStatus": "ACTIVE",
  "adTypes": "ALL",
  "maxAds": 100,
  "proxy": {
    "useApifyProxy": true,
    "apifyProxyGroups": ["RESIDENTIAL"],
    "apifyProxyCountry": "US"
  }
}
```

### 3.2 Output Record Normalization
Raw output keys mapped to US WIN HUNTER domain models:

| Provider Key | Type | Model Target | Transform / Validation |
| :--- | :--- | :--- | :--- |
| `id` | `str` | `Advertisement.external_id` | Must be numeric Meta Ad Archive ID |
| `pageId` | `str` | `Advertiser.facebook_page_id` | Extracted numeric Page ID |
| `pageName` | `str` | `Advertiser.name` | Stripped whitespace, normalized |
| `snapshotUrl` | `str` | `Advertisement.ad_url` | Validated `facebook.com/ads/library` URI |
| `startDate` | `str` | `Advertisement.advertiser_start_date` | Parsed to UTC `datetime` |
| `isActive` | `bool` | `Advertisement.is_active` | Direct boolean mapping |
| `linkUrl` | `str` | `Advertisement.landing_page_url` | Stripped UTM params, domain extracted for `Advertiser.domain` |
| `title` | `str` | `Advertisement.title` | Cleaned product headline |
| `bodies` | `list[str]` | `Advertisement.body` | Joined with single newline |
| `images` | `list[str]` | `Advertisement.creative_url` | Primary image URL (first item) |
| `videos` | `list[dict]` | `Advertisement.creative_type` | Marked as `"video"` if present |
| `targetCountries`| `list[str]` | `Advertisement.target_country` | Must contain `"US"`; reject non-US records |

---

## 4. Fallback Provider Deep-Dive: `curious_coder/facebook-ads-library-scraper`

### 4.1 Input Mapping Specification
Used when primary encounters transient outages, actor maintenance, or rate throttling:

```json
{
  "startUrls": [
    {
      "url": "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&q=magnetic%20socket%20organizer&search_type=keyword_unordered&media_type=all"
    }
  ],
  "pageIds": ["1092837482"],
  "maxAds": 100,
  "scrapeDetails": true,
  "proxyConfiguration": {
    "useApifyProxy": true,
    "apifyProxyCountry": "US"
  }
}
```

### 4.2 Output Record Normalization
Mapped through existing `_import_meta_ads` fallback fields in `backend/app/services/import_service.py`:
- `adArchiveID` → `external_id`
- `page_id` → `facebook_page_id`
- `page_name` → `name`
- `ad_snapshot_url` → `ad_url`
- `ad_delivery_start_time` → `advertiser_start_date`
- `ad_creative_link_images` → `creative_url`
- `ad_creative_bodies` → `body`
- `link_url` → `landing_page_url`
- `delivery_by_region` → validated for US states/territories

---

## 5. Economic & Cost Management Architecture

1. **Unit Economics:**
   - 1,000 ad records = ~$0.75 – $1.50 USD.
   - Per targeted query run (50–100 ads): ~$0.05 – $0.15 USD.
   - Cost per valid new product: ~$0.20 – $0.50 USD.
2. **Hard Spend Limits:**
   - Default daily maximum budget: `$5.00 USD` (configurable in Settings).
   - Default monthly maximum budget: `$50.00 USD` (configurable in Settings).
3. **Fail-Closed Policy:**
   - If `APIFY_API_TOKEN` is unset or empty, the adapter transitions to `NOT_CONFIGURED` and aborts all network executions without crashing.
   - If estimated monthly spend exceeds the configured budget limit, the scheduler halts automatic collection and transitions to `BLOCKED` with an alert.
   - No auto-upgrades or unmetered external calls.

---

## 6. Legal, Compliance & Data Retention Position

1. **Meta Terms of Service Consideration:**
   - Scraping commercial ads is subject to Meta's public ad library policies. Scraping is executed strictly through authorized commercial proxy runners on Apify, abstracting direct scraping liability.
2. **Data Minimization & Public Commercial Scope:**
   - Only publicly broadcasted commercial advertisements targeted to US consumers are collected.
   - Zero private user data, personal communications, or demographic user profiles are touched or stored.
   - All collected ad creatives and copy are public marketplace communications retained solely for competitive market intelligence and bundle feasibility evaluation under fair research principles.

