import asyncio
import json
import os
import sys
import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.config import get_settings

async def check():
    settings = get_settings()
    token = settings.apify_api_token
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient() as client:
        # Check dataset from mgrbhLt82lm2ybAZn
        r = await client.get("https://api.apify.com/v2/actor-runs/mgrbhLt82lm2ybAZn", headers=headers)
        data = r.json().get("data", {})
        dataset_id = data.get("defaultDatasetId")
        print(f"Dataset ID: {dataset_id}")
        
        items_r = await client.get(f"https://api.apify.com/v2/datasets/{dataset_id}/items?limit=2", headers=headers)
        items = items_r.json()
        if items:
            print("First item keys:", list(items[0].keys()))
            print("\nFirst item preview:")
            for k, v in items[0].items():
                if isinstance(v, (str, int, float, bool)) or v is None:
                    print(f"  {k}: {v}")
                elif isinstance(v, list):
                    print(f"  {k}: list of {len(v)} items")
                elif isinstance(v, dict):
                    print(f"  {k}: dict with keys {list(v.keys())}")

if __name__ == "__main__":
    asyncio.run(check())

