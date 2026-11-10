# Facebook Ads Library Scraper

Scrape ads from the [Facebook Ad Library](https://www.facebook.com/ads/library/) / Meta Ad Library at scale: Facebook and Instagram ads from any advertiser. Search by keyword (any words or exact phrase), advertiser Facebook Page URL, pasted Ads Library results URL, or browse by country, sorted by impressions or Meta's "Most recent" ranking. Extract ad creatives, copy, destination links, images and videos in a flat, spreadsheet-ready format. Turn on **ad details** to add EU reach, reach by country/age/gender, targeting, payer and beneficiary, and advertiser Instagram followers at no extra cost per ad. No Facebook login, Meta app review, API token, or Ad Library API approval required.

## What does Facebook Ads Library Scraper do?

This actor searches the Facebook Ad Library and extracts structured data from every ad it finds. It loads the Ad Library's public data using HTTP with automatic real-browser (Playwright) recovery, and outputs clean, flattened records you can immediately use in spreadsheets, databases, or downstream workflows. Use it as the Meta/Facebook source in an ad monitoring stack with Google Ads Transparency Center and LinkedIn Ad Library data.

Each search query extracts ads from the initial results page and paginates to load more. Set the `maxAds` parameter to control how many ads to extract per search (safety cap: 500 per task). Optional `onlyAdsNewerThan` and `onlyAdsOlderThan` inputs collect ads whose activity interval overlaps an inclusive campaign date window; pagination continues until `maxAds` matching ads are found or Facebook has no more results. To collect more ads, use multiple search keywords or advertiser page URLs — the actor processes up to 20 tasks per run, logs progress per task/page, and combines all results into a single dataset. Overlapping results are deduplicated by Facebook Ad Library ID before output and per-ad charging.

## Diagnostic privacy

Failed operations send sanitized diagnostic input, exceptions, and Actor/build/run IDs to our private GlitchTip service for repair. Secret fields and URL queries are removed; reports are retained for 30 days.

## Who is it for?

- **Digital marketers** — Research competitor ad strategies, discover winning ad creatives, and find inspiration for your own campaigns.
- **Competitive intelligence teams** — Monitor what competitors are advertising, how much they spend, and which platforms they target.
- **Brand monitoring professionals** — Track unauthorized use of your brand in ads, or monitor how partners represent your brand.
- **Agencies** — Audit client competitors' ad presence across Facebook, Instagram, Messenger, and Audience Network.
- **Researchers & journalists** — Analyze political advertising, track ad transparency, and study advertising trends at scale.

## Why use Facebook Ads Library Scraper?

- **No Meta API setup** — Skip Meta app creation, review, access approvals, and token management. The actor works from the public Ad Library experience.
- **No login required** — The Facebook Ad Library is publicly accessible. No Facebook account needed.
- **Structured output** — All ad data is flattened into clean rows with consistent field names. Ready for Google Sheets, Excel, Airtable, or any database.
- **Multiple search modes** — Search by keyword, advertiser Facebook Page URL, pasted Ads Library results URL, or any combination. Filter by country, ad status (active/inactive), and media type.
- **Inclusive campaign windows** — Set `onlyAdsNewerThan`, `onlyAdsOlderThan`, or both using `YYYY-MM-DD` or relative values such as `30 days`; an ad matches when its activity interval overlaps the requested window.
- **Rich media extraction** — Get direct URLs for ad images, videos, and video preview thumbnails.
- **Ad details: EU reach and targeting** — Optional `includeAdDetails` adds Meta's "See ad details" data: EU total reach, reach by country, age and gender, targeted locations, ages and gender, payer and beneficiary, and the advertiser's Instagram username, followers and verification. Same price per ad.
- **Most recent ranking** — `sortBy: "recent"` uses Meta's "Most recent" ranking, which favours recently launched creatives and is useful for monitoring competitors' new ads. Meta groups results by month and relevance, so the output is not in strict start-date order; sort by `startDate` yourself if you need exact chronology.
- **Exact-phrase search** — `searchType: "keyword_exact_phrase"` sends Meta's exact-phrase search, which returns far more ads using your whole phrase than the default any-words search. Meta can match the phrase in an ad variant, media or text that is not exported, so not every row's exported text visibly contains the phrase.
- **Clean catalog ads** — Catalog (dynamic product) ads show the real product card text, never `{{product.name}}` placeholders, and are marked with `isCatalogAd`.
- **Spend and impressions data** — Meta publishes spend ranges and impressions only for political and social-issue ads; for commercial ads use `adDetails.euTotalReach`.
- **Platform breakdown** — See which platforms each ad runs on (Facebook, Instagram, Messenger, Audience Network).

## What data can you extract?

| Field | Type | Description |
|-------|------|-------------|
| `adArchiveId` | string | Unique Ad Library ID |
| `adLibraryUrl` | string | Direct link to the ad in Ad Library |
| `pageId` | string | Facebook page ID of the advertiser |
| `pageName` | string | Name of the advertiser page |
| `pageUrl` | string | URL of the advertiser's Facebook page |
| `pageProfilePictureUrl` | string | Advertiser's profile picture URL |
| `pageCategories` | array | Categories of the advertiser page |
| `pageLikeCount` | number | Number of page likes |
| `isActive` | boolean | Whether the ad is currently running |
| `startDate` | string | Date the ad started running (YYYY-MM-DD) |
| `endDate` | string | Date the ad stopped running (YYYY-MM-DD) |
| `platforms` | array | Platforms where the ad runs (facebook, instagram, messenger, audience_network) |
| `bodyText` | string | Main ad copy / body text |
| `title` | string | Ad headline / title |
| `ctaText` | string | Call-to-action button text (e.g., "Shop Now") |
| `ctaType` | string | Call-to-action type identifier |
| `linkUrl` | string | Destination URL the ad links to |
| `linkCaption` | string | Display URL caption |
| `linkDescription` | string | Link description text |
| `displayFormat` | string | Ad format (e.g., "image", "video", "carousel") |
| `imageUrls` | array | Direct URLs to ad images |
| `videoUrls` | array | Direct URLs to ad videos (HD preferred) |
| `videoPreviewUrls` | array | Video thumbnail/preview image URLs |
| `categories` | array | Ad categories (e.g., "EMPLOYMENT", "HOUSING") |
| `containsAiMedia` | boolean | Whether the ad contains AI-generated media |
| `impressions` | string | Impression count text (political/issue ads only) |
| `spend` | object | Estimated spend range (`lowerBound`, `upperBound`; political/issue ads only) |
| `currency` | string | Currency code for spend data |
| `gatedType` | string | Gated content type (if applicable) |
| `collationCount` | number | Number of ad variations in this collation group |
| `cardsCount` | number | Number of carousel cards |
| `collationId` | string | Group ID shared by identical ad variations |
| `pageIsDeleted` | boolean | Whether the advertiser's Page was deleted |
| `isCatalogAd` | boolean | Catalog (dynamic product) ad; text comes from the first product card |
| `adDetails` | object | With `includeAdDetails`: `euTotalReach`, `reachBreakdown` (country, ageRange, male, female, unknown), `targetedLocations`, `targetedGender`, `targetedAgeMin`, `targetedAgeMax`, `payerBeneficiary`, `advertiser` (pageAlias, pageCategory, pageVerification, pageLikes, instagramUsername, instagramFollowers, instagramVerified, about). `null` when off |

## How much does it cost to scrape Facebook ads?

Facebook Ads Library Scraper uses [pay-per-event pricing](https://docs.apify.com/platform/actors/running/pay-per-event). You only pay for what you use — no monthly minimums.

| Charge event | Price (Bronze) | Description |
|-------------|---------------|-------------|
| **Run started** | $0.005 | One-time charge per actor run |
| **Ad scraped** | $0.0005/ad | Per ad extracted |

**Volume discounts** are available on higher Apify plans:

| Plan | Per-ad price | Discount |
|------|-------------|----------|
| Free | $0.000575 | — |
| Bronze (Starter) | $0.0005 | Baseline |
| Silver (Scale) | $0.00039 | 22% off |
| Gold (Business) | $0.0003 | 40% off |
| Platinum (Enterprise) | $0.0002 | 60% off |
| Diamond (Enterprise+) | $0.00014 | 72% off |

**Example cost**: Scraping 50 ads from one search query costs approximately **$0.005 + (50 x $0.0005) = $0.030** on the Bronze plan.

## How to scrape Facebook ads

1. Go to [Facebook Ads Library Scraper](https://apify.com/automation-lab/facebook-ads-library) on Apify Store.
2. Click **Try for free** to open the actor in Apify Console.
3. Enter your search keywords (e.g., "running shoes", "shopify"), advertiser Facebook Page URLs, or Facebook Ads Library results URLs copied from your browser.
4. Optionally set the country code (default: US), ad status, media type, and inclusive activity date bounds. Direct Ads Library URLs use their embedded country/status/media filters, while validated date bounds come from `onlyAdsNewerThan` and `onlyAdsOlderThan`.
5. Click **Start** and wait for the run to finish.
6. Download your data as JSON, CSV, Excel, or connect to any integration.

## Input parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `searchQueries` | array of strings | — | Keywords to search for in the Ad Library. Up to 20 total tasks per run. |
| `pageUrls` | array of strings | — | Facebook Page URLs (`facebook.com/nike`, `profile.php?id=...`, `/people/...`, `/p/...`) or numeric Page IDs. Each Page is resolved to its Ads Library Page ID and only that advertiser's ads are returned. A Page we can't identify with certainty is skipped, not guessed from its name: paste its Ads Library URL (with `view_all_page_id`) instead. Skipped inputs, including non-Facebook or non-Page URLs, get a status message and are never charged. Up to 20 total tasks per run. |
| `adsLibraryUrls` | array of strings | — | Facebook Ads Library result URLs copied from `facebook.com/ads/library/`. Up to 20 total tasks per run. |
| `country` | string | `"US"` | ISO country code (e.g., "US", "GB", "DE") or "ALL" for all countries |
| `activeStatus` | enum | `"all"` | Filter by status: "all", "active", or "inactive" |
| `mediaType` | enum | `"all"` | Filter by media: "all", "image_and_meme", or "video" |
| `onlyAdsNewerThan` | string | `""` | Inclusive lower activity bound as `YYYY-MM-DD` or a positive relative duration such as `30 days` |
| `onlyAdsOlderThan` | string | `""` | Inclusive upper activity bound as `YYYY-MM-DD` or a positive relative duration such as `90 days` |
| `searchType` | enum | `"keyword_unordered"` | Keyword match: `"keyword_unordered"` (any words, Facebook's default) or `"keyword_exact_phrase"` (Meta's exact-phrase search; the phrase may not appear in every row's exported text) |
| `sortBy` | enum | `"impressions"` | `"impressions"` (Facebook's default order) or `"recent"` (Meta's "Most recent" ranking; favours recent ads but not strict start-date order). A sort in a pasted Ads Library URL is kept |
| `maxAds` | integer | 100 | Max matching ads per search query, page URL, or Ads Library URL. Safety cap: 500 per task; split larger exports into smaller runs. |
| `includeAdDetails` | boolean | `false` | Add the `adDetails` object (EU reach, targeting, payer/beneficiary, advertiser Instagram info) to each ad. Same price per ad; adds about 1 second per 6 ads. If Facebook refuses details, ads are still saved with `adDetails: null` and the status message says so |

**Tip**: You must provide at least one search keyword, advertiser Facebook Page URL, or Ads Library result URL. You can mix all three — results from all sources are combined into one dataset, and duplicate ads found by overlapping inputs are emitted and charged only once per run, based on Facebook Ad Library ID.

**Direct Ads Library URLs**: Paste URLs whose host is `facebook.com`, `www.facebook.com`, or `m.facebook.com` and path is `/ads/library/` (with or without the trailing slash). The actor preserves supported URL filters: `q`, `view_all_page_id`, `country`, `active_status`, `media_type`, `search_type`, `sort_data`, and supported `ad_type` values (`all`, `political_and_issue_ads`). Date parameters embedded in a URL are not preserved; set validated date bounds with `onlyAdsNewerThan` and `onlyAdsOlderThan`. Other unsupported parameters such as language, platform, region, or special filters are ignored with a warning so pagination stays deterministic.
A URL needs a keyword (`q`) or advertiser (`view_all_page_id`) filter. Single-ad links (`?id=...`) are skipped with a warning; paste the search results URL or the advertiser Page URL instead.

**Field names from other tools**: `urls`, `startUrls` (strings or `{ "url": ... }` objects) and `adLibraryUrls` are read as Ads Library or Page URLs, `pageIds` as advertiser Page IDs and `searchQuery` as a keyword. The run log notes the mapping.

## Output example

```json
{
  "adArchiveId": "123456789012345",
  "adLibraryUrl": "https://www.facebook.com/ads/library/?id=123456789012345",
  "pageId": "987654321",
  "pageName": "Shopify",
  "pageUrl": "https://www.facebook.com/shopify/",
  "pageProfilePictureUrl": "https://scontent.xx.fbcdn.net/...",
  "pageCategories": ["E-commerce website"],
  "pageLikeCount": 4200000,
  "isActive": true,
  "startDate": "2025-11-15",
  "endDate": null,
  "platforms": ["facebook", "instagram"],
  "bodyText": "Start your online store today. No coding required.",
  "title": "Free Trial — Start Selling Online",
  "ctaText": "Sign Up",
  "ctaType": "SIGN_UP",
  "linkUrl": "https://www.shopify.com/free-trial",
  "linkCaption": "shopify.com",
  "linkDescription": "Try Shopify free for 3 days.",
  "displayFormat": "image",
  "imageUrls": ["https://scontent.xx.fbcdn.net/..."],
  "videoUrls": [],
  "videoPreviewUrls": [],
  "categories": [],
  "containsAiMedia": false,
  "impressions": null,
  "spend": null,
  "currency": "USD",
  "gatedType": null,
  "collationCount": 1,
  "cardsCount": 0,
  "collationId": "777407455176430",
  "pageIsDeleted": false,
  "isCatalogAd": false,
  "adDetails": null
}
```

With `includeAdDetails: true`, `adDetails` looks like this (EU-delivered ad, trimmed):

```json
{
  "euTotalReach": 18878266,
  "targetedLocations": [{ "name": "France", "type": "countries", "excluded": false }],
  "targetedGender": "All",
  "targetedAgeMin": 18,
  "targetedAgeMax": 65,
  "reachBreakdown": [{ "country": "FR", "ageRange": "45-54", "male": 1894943, "female": 1500000, "unknown": null }],
  "payerBeneficiary": [{ "payer": "HONG KONG CIFNEWS LIMITED", "beneficiary": "Temu" }],
  "advertiser": { "pageAlias": "shoptemu", "pageCategory": "Shopping Service", "pageVerification": "BLUE_VERIFIED", "pageLikes": 12441820,
    "instagramUsername": "temu", "instagramFollowers": 13782082, "instagramVerified": true, "about": "..." }
}
```

## Tips for best results

- **Use specific keywords** — Broad terms like "shoes" return many results. Try "Nike running shoes" or "Allbirds" for more targeted ads.
- **Search by advertiser page URL** — If you know the exact advertiser, use their Facebook page URL for precise results.
- **Combine search modes** — Use both keywords and page URLs in a single run to collect ads from multiple angles.
- **Use multiple keywords for more data** — Each keyword search paginates to your `maxAds` limit. Run related keywords in one batch (up to 20 total tasks) to cover a broader range of ads while keeping progress visible.
- **Filter by status** — Use "active" to see only currently running ads, or "inactive" to study past campaigns.
- **Filter by campaign period** — Use one or both inclusive date bounds. An ad is included when its activity interval overlaps the window; an ad with no `endDate` is treated as still active. Filtered-out ads are not charged.
- **Filter by media type** — Use "video" to focus on video ads or "image_and_meme" for static creatives.
- **Check different countries** — The same advertiser may run different ads in different markets. Try US, GB, DE, etc.
- **Monitor new creatives** — Combine `sortBy: "recent"` with `activeStatus: "active"` in a scheduled run to see what competitors launched this week.
- **Measure reach** — Turn on `includeAdDetails` and sort or filter by `adDetails.euTotalReach` to find the ads Meta delivered most widely in the EU.

## Integrations

Connect Facebook Ads Library Scraper to your existing tools:

- **Google Sheets** — Automatically export scraped ads to a spreadsheet for team review.
- **Slack** — Get notifications when new competitor ads are detected.
- **Airtable** — Build a competitive ad library with rich media attachments.
- **Zapier / Make / n8n** — Trigger downstream workflows when new ads are found.
- **Webhooks** — Send results to your own API endpoint for custom processing.
- **Google BigQuery / Snowflake** — Load ad data into your data warehouse for analysis.

### Example workflows

- **Cross-channel ad monitoring**: Pair this actor with [Google Ads Scraper](https://apify.com/automation-lab/google-ads-scraper) for Google Ads Transparency Center data and [LinkedIn Ad Library Scraper](https://apify.com/automation-lab/linkedin-ad-library-scraper) for B2B LinkedIn ads. Schedule all three actors and join datasets by advertiser, creative text, date, country, and destination URL.
- **Competitor monitoring**: Schedule daily runs with competitor brand names. Compare new ads against previous runs to spot new campaigns.
- **Ad creative research**: Search for product categories ("protein powder", "SaaS tools") to build a library of ad inspiration.
- **Brand protection**: Search for your brand name to detect unauthorized ads using your trademark.
- **Market research**: Compare ad strategies across countries for the same advertiser.

## Using the Apify API

You can start and retrieve results programmatically using the [Apify API](https://docs.apify.com/api/v2).

### Node.js

```javascript
import { ApifyClient } from 'apify-client';

const client = new ApifyClient({ token: 'YOUR_API_TOKEN' });

const run = await client.actor('automation-lab/facebook-ads-library').call({
    searchQueries: ['shopify'],
    country: 'US',
    maxAds: 30,
});

const { items } = await client.dataset(run.defaultDatasetId).listItems();
console.log(items);
```

### Python

```python
from apify_client import ApifyClient

client = ApifyClient('YOUR_API_TOKEN')

run = client.actor('automation-lab/facebook-ads-library').call(run_input={
    'searchQueries': ['shopify'],
    'country': 'US',
    'maxAds': 30,
})

items = client.dataset(run['defaultDatasetId']).list_items().items
print(items)
```

### cURL

```bash
# Start a run
curl -X POST "https://api.apify.com/v2/acts/automation-lab~facebook-ads-library/runs?token=YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"searchQueries": ["shopify"], "country": "US", "maxAds": 30}'

# Get results (replace RUN_ID with the actual run ID)
curl "https://api.apify.com/v2/datasets/DATASET_ID/items?token=YOUR_API_TOKEN"
```

## Use with Claude AI (MCP)

This actor is available as a tool in Claude AI through the Model Context Protocol (MCP). Add it to Claude Desktop, Cursor, Windsurf, or any MCP-compatible client.

### Setup for Claude Code

```bash
claude mcp add --transport http apify "https://mcp.apify.com?tools=automation-lab/facebook-ads-library"
```

### Setup for Claude Desktop, Cursor, or VS Code

Add this to your MCP config file:

```json
{
    "mcpServers": {
        "apify": {
            "url": "https://mcp.apify.com?tools=automation-lab/facebook-ads-library"
        }
    }
}
```

### Example prompts

- "Find all active Facebook ads from Nike in the US and summarize their messaging strategy"
- "Search for Facebook ads about electric vehicles in Germany and list the top advertisers by number of ads"
- "Pull the latest ads from this competitor's Facebook page and tell me what offers and formats they're running"

Learn more in the [Apify MCP documentation](https://docs.apify.com/platform/integrations/mcp).

## Data handling, AI, and third-party services

- **No AI processing:** the actor does not call an AI model or send input or scraped data to an AI provider. The `containsAiMedia` field is metadata reported by Facebook, not an actor-generated classification.
- **Data recipients:** search terms, public page identifiers, selected filters, and ordinary request metadata are sent to Facebook through Apify's datacenter and residential proxy services. Facebook and Apify process that traffic under their respective terms and privacy policies.
- **Storage and retention:** results are stored only in the run's default Apify dataset. The actor creates no separate cross-run ad cache or backup. Run input, logs, and dataset retention follow your Apify plan and deletion settings; you can delete them in Apify Console or through the API.
- **Credentials:** no Facebook login, cookie, API token, or other Facebook credential is accepted or stored.
- **Support:** report reproducible problems through the **Issues** tab on this Actor's Apify Store page.

Facebook and Meta are nominative references to the public data source. This Actor is not endorsed by, sponsored by, affiliated with, or operated by Meta.

## Is it legal to scrape Facebook Ad Library?

The [Facebook Ad Library](https://www.facebook.com/ads/library/) is a **public transparency tool** created by Meta to provide public access to all ads running across Facebook, Instagram, Messenger, and Audience Network. It was created in response to regulatory requirements for ad transparency.

- The Ad Library is publicly accessible without a Facebook account.
- All data in the Ad Library is intentionally made public by Meta.
- This actor accesses only publicly available data from the Ad Library.

Always review and comply with Meta's [Terms of Service](https://www.facebook.com/terms.php) and applicable laws in your jurisdiction before using this actor.

## Legality

This actor accesses publicly available data through official or public APIs. API usage is subject to each service's Terms of Service and rate limits. Always review the API provider's usage policies before running at scale.

## FAQ

**Q: How many ads can I scrape per run?**
The actor automatically paginates to load more results up to your `maxAds` limit (up to 500 per search/page task). For broader coverage, use multiple search keywords in a single run — each keyword runs a separate search, up to 20 tasks per run.

**Q: Can I scrape all ads from a specific advertiser?**
Yes. Enter the advertiser's Facebook Page URL (e.g., `https://www.facebook.com/nike`) in the "Advertiser page URLs" field. The actor looks up that Page's Ads Library Page ID and returns only ads run by that Page. If the Page cannot be found (deleted, private, a personal profile, or a non-Facebook URL), nothing is searched or charged for it and the run's status message says why.

**Q: Does it support pagination beyond the first page?**
Yes — the actor paginates automatically to load more results up to your `maxAds` limit. The default is 100 ads per search query and the per-task safety cap is 500.

**Q: Do I need a Facebook account?**
No. The Facebook Ad Library is publicly accessible. No login or authentication is needed.

**Q: What countries are supported?**
All countries available in the Facebook Ad Library are supported. Use the ISO country code (e.g., "US", "GB", "DE", "BR", "IN") or "ALL" to search globally.

**Q: Why are some fields null?**
Not all ads have all data. Meta publishes spend and impression data only for ads about social issues, elections, or politics. EU reach and targeting (`adDetails`) exist only for ads delivered in the EU. Catalog ads with no product card text have `null` text fields instead of `{{product.*}}` placeholders. Some ads may not have video URLs, CTA buttons, or link descriptions.

**Q: Can I get ad reach, targeting and age/gender data?**
Yes. Turn on `includeAdDetails`. Each ad gets an `adDetails` object with the EU total reach, reach by country, age range and gender, targeted locations, ages and gender, payer and beneficiary, and advertiser info such as Instagram followers. This is the data behind Meta's "See ad details" button. It costs nothing extra per ad.

**Q: The actor returned 0 ads. What should I do?**
- Check that your search keyword matches ads in the [Facebook Ad Library](https://www.facebook.com/ads/library/) directly.
- Try a broader keyword or different country.
- If searching by page URL, make sure the URL is a public Facebook Page. If the run reports that a Page could not be found, paste the advertiser's Ads Library URL (with `view_all_page_id`) instead.
- The Ad Library can report a result count but show no ads, because Facebook withholds some ads from every visitor. The actor follows every results page and finishes successfully with an empty result when Facebook shows none.

**Q: Can I filter by date range?**
Yes. Set `onlyAdsNewerThan`, `onlyAdsOlderThan`, or both to an absolute `YYYY-MM-DD` date or positive relative duration such as `30 days`. Bounds are inclusive: an ad matches when its `startDate`/`endDate` activity interval overlaps the requested window, and a missing `endDate` means the ad is still active. If both inputs are empty, default behavior is unchanged.

**Q: How often can I run this actor?**
As often as you need. There are no built-in rate limits. However, very frequent runs against the same search terms may trigger Facebook's anti-bot measures.

## Related ad monitoring and marketing scrapers from Automation Lab

- [Google Ads Scraper](https://apify.com/automation-lab/google-ads-scraper) — Scrape Google Ads Transparency Center creatives by advertiser name, domain, advertiser ID, and region.
- [LinkedIn Ad Library Scraper](https://apify.com/automation-lab/linkedin-ad-library-scraper) — Extract LinkedIn ad creatives, headlines, CTAs, funding entities, and media URLs for B2B ad monitoring.
- [Instagram Scraper](https://apify.com/automation-lab/instagram-scraper) — Extract profiles, posts, comments, and hashtag results from Instagram.
- [TikTok Scraper](https://apify.com/automation-lab/tiktok-scraper) — Scrape TikTok profiles, videos, and engagement data.
- [Twitter/X Scraper](https://apify.com/automation-lab/twitter-scraper) — Extract tweets, profiles, and engagement metrics.
- [Reddit Scraper](https://apify.com/automation-lab/reddit-scraper) — Scrape Reddit posts, comments, and subreddit data.
- [Google Maps Lead Finder](https://apify.com/automation-lab/google-maps-lead-finder) — Find local business leads with contact info from Google Maps.
- [YouTube Scraper](https://apify.com/automation-lab/youtube-scraper) — Extract video metadata, channel info, and comments from YouTube.

## Use with AI agents via x402 (no Apify account)

Agent workflows can run this actor through Apify MCP without an Apify account when the MCP client uses a funded x402 wallet. Use the actor-specific MCP endpoint:

`https://mcp.apify.com?tools=automation-lab/facebook-ads-library&payment=x402`

This keeps existing Apify MCP/API usage unchanged; x402 only changes payment/authentication for clients that support it. Learn more in Apify's [x402 integration docs](https://docs.apify.com/platform/integrations/x402).
