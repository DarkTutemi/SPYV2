# Open-Source Repository Audit

Checked 2026-11-07 from documentation/README research. **No repository has been cloned or executed yet**; "last checked commit" will be filled when a shallow clone is made into `third_party/research/`.

| Repo | Purpose | License | Type | Cost / creds | Decision | Integration approach |
|---|---|---|---|---|---|---|
| unclecode/crawl4ai | Landing page product/price/bundle extraction | Apache-2.0 | Real library (Playwright) | Free; heavy browser deps | **EVALUATE FURTHER** (Phase 4) | Pinned pip dependency behind `LandingPageExtractor` adapter; robots.txt respected; no stealth/anti-detection features used |
| idealo/imagededup | pHash/dHash near-duplicate creatives | Apache-2.0 | Real library | Free; pulls torch for CNN mode | **ADOPT (hash mode)** Phase 2 | Pinned dependency; hashing only; benchmark on identical/cropped/variant images before trusting thresholds |
| dgtlmoon/changedetection.io | Offer/bundle page change monitoring | Apache-2.0 | Self-hosted app | Free | **REJECT for now** | Too heavy as embedded component; our `product_offers` history + periodic re-extraction covers the need. Could run separately and import webhooks later |
| langchain-ai/langgraph | Stateful AI workflows | MIT | Library | Free | **REJECT for now** | Pipeline is linear; plain Python is sufficient. Revisit if human-in-the-loop branching grows |
| flack0x/trendspyg | US Google Trends | (verify on clone) | Unofficial client | Free; fragile | **EVALUATE FURTHER** Phase 5 | Adapter; results tagged as unofficial; repeated-observation consistency test required |
| apify/apify-client-python | Provider datasets | Apache-2.0 | Official SDK | Apify plan + usage | **ADOPT (when token provided)** | Fetch existing dataset items only; never start paid actor runs without operator approval |
| themineworks/facebook-ad-library-scraper | Meta ad data via Apify actor | (verify) | Client wrapper for hosted provider, not an access method | Apify billing | **EVALUATE FURTHER** | Its output field shape is supported by `ImportService._import_meta_ads`; no code vendored |
| huggingface/sentence-transformers | Title/description & pain similarity | Apache-2.0 | Real library, local | Free; ~90MB model (all-MiniLM-L6-v2) | **ADOPT** Phase 2 | Pinned; similarity only *proposes* candidates — never auto-merges |

## Reused vs custom
- Reused (planned): imagededup, sentence-transformers, apify-client, optionally crawl4ai/trendspyg.
- Custom (core IP): US eligibility, geo confidence, advertiser graph, product identity rules, temporal metrics, bundle reasoning, all scoring.

