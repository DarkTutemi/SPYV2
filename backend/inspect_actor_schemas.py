import asyncio
import json
import httpx
from app.core.config import get_settings

ACTORS = [
    "steadyscrape/tiktok-creative-center-scraper",
    "tortuga/tiktok-shop-scraper",
    "scrapermagic/amazon-product-scraper",
    "apify/google-trends-scraper",
    "inimi/shopify-store-scraper",
    "offgrid-labs/reddit-scraper",
]

async def main():
    settings = get_settings()
    token = settings.apify_api_token
    headers = {"Authorization": f"Bearer {token}"}
    schemas = {}

    async with httpx.AsyncClient(timeout=30) as client:
        for actor in ACTORS:
            slug = actor.replace("/", "~")
            url = f"https://api.apify.com/v2/acts/{slug}"
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                build_id = data.get("taggedBuilds", {}).get("latest", {}).get("buildId")
                # fetch build schema
                if build_id:
                    build_resp = await client.get(f"https://api.apify.com/v2/actor-builds/{build_id}", headers=headers)
                    if build_resp.status_code == 200:
                        build_data = build_resp.json().get("data", {})
                        input_schema = build_data.get("inputSchema")
                        if isinstance(input_schema, str):
                            try:
                                input_schema = json.loads(input_schema)
                            except Exception:
                                pass
                        schemas[actor] = {
                            "title": data.get("title"),
                            "input_schema": input_schema,
                            "pricing": data.get("pricingInfos"),
                        }
                        continue
            print(f"Failed to fetch schema for {actor}: {resp.status_code}")

    with open("backend/multisource_schemas.json", "w", encoding="utf-8") as f:
        json.dump(schemas, f, indent=2)
    print("Saved schemas to backend/multisource_schemas.json")

if __name__ == "__main__":
    asyncio.run(main())

