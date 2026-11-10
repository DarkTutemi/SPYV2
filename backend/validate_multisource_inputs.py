import urllib.request
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.core.config import get_settings

token = get_settings().apify_api_token
headers = {"User-Agent": "Mozilla/5.0", "Authorization": f"Bearer {token}"}

actors = [
    "steadyscrape~tiktok-creative-center-scraper",
    "tortuga~tiktok-shop-scraper",
    "scrapermagic~amazon-product-scraper",
    "apify~google-trends-scraper",
    "inimi~shopify-store-scraper",
    "offgrid-labs~reddit-scraper"
]

schemas = {}

for slug in actors:
    url = f"https://api.apify.com/v2/acts/{slug}/builds?limit=1&desc=true"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        builds = json.loads(resp.read().decode("utf-8")).get("data", {}).get("items", [])
        if builds:
            b_id = builds[0]["id"]
            url_b = f"https://api.apify.com/v2/acts/{slug}/builds/{b_id}"
            req_b = urllib.request.Request(url_b, headers=headers)
            with urllib.request.urlopen(req_b, timeout=10) as resp_b:
                b_data = json.loads(resp_b.read().decode("utf-8")).get("data", {})
                schema = b_data.get("inputSchema")
                if isinstance(schema, str):
                    schema = json.loads(schema)
                schemas[slug] = schema

with open("multisource_schemas.json", "w", encoding="utf-8") as f:
    json.dump(schemas, f, indent=2)

print(f"Dumped schemas for {len(schemas)} actors to multisource_schemas.json")
for slug, s in schemas.items():
    print(f"\n--- {slug} ---")
    props = s.get("properties", {})
    required = s.get("required", [])
    print(f"Required: {required}")
    for k, v in props.items():
        print(f"  {k} ({v.get('type')}) - {v.get('title')}")

