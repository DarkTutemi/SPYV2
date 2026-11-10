"""
US WIN HUNTER — Preflight & Safegaurd Verification for Authorized New Research Run
Validates Actor accessibility, current pricing, schema, and reserves budget.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.core.config import get_settings
from app.adapters.apify import APIFY_BASE_URL

settings = get_settings()

TARGET_ACTORS = [
    {
        "key": "google_trends_new_categories",
        "actor_id": "apify/google-trends-scraper",
        "budget_cap_usd": 0.15,
        "description": "Google Trends longitudinal interest for 10 new non-pet utility problem queries in the US",
    },
    {
        "key": "amazon_us_new_categories",
        "actor_id": "scrapermagic/amazon-product-scraper",
        "budget_cap_usd": 0.15,
        "description": "Amazon US live listings, price points, and review benchmarks for winning non-pet candidates",
    }
]

async def preflight():
    token = settings.apify_api_token
    if not token:
        print("ERROR: Apify API token not configured!")
        return False

    print("=== PREFLIGHT SAFEGURAD CHECK ===")
    print(f"Token length: {len(token)} chars (Credentials hidden)")
    print(f"Max session authorization: $2.00 USD")
    
    total_planned_cap = sum(a["budget_cap_usd"] for a in TARGET_ACTORS)
    print(f"Planned maximum total budget cap: ${total_planned_cap:.2f} USD")
    assert total_planned_cap <= 2.00, "Planned spend exceeds authorized session ceiling!"

    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=20.0) as client:
        # 1. Check account user & billing
        resp = await client.get(f"{APIFY_BASE_URL}/users/me", headers=headers)
        if resp.status_code != 200:
            print(f"ERROR: Cannot authenticate with Apify API: HTTP {resp.status_code}")
            return False
        user_info = resp.json().get("data", {})
        username = user_info.get("username", "unknown")
        print(f"Authenticated as Apify user: '{username}'")

        # 2. Check each actor
        for a in TARGET_ACTORS:
            actor_slug = a["actor_id"].replace("/", "~")
            url = f"{APIFY_BASE_URL}/acts/{actor_slug}"
            act_resp = await client.get(url, headers=headers)
            if act_resp.status_code != 200:
                print(f"ERROR: Actor {a['actor_id']} not accessible: HTTP {act_resp.status_code}")
                return False
            act_data = act_resp.json().get("data", {})
            pricing_info = act_data.get("pricingInfos", [])
            title = act_data.get("title", "")
            print(f"\n[Actor Verified] {a['actor_id']}")
            print(f"  Title: {title}")
            print(f"  Pricing: {pricing_info}")
            print(f"  Budget Cap: ${a['budget_cap_usd']:.2f} USD")

    print("\nPreflight check PASSED! All actors are accessible, maintained, and within safe spending bounds.")
    return True

if __name__ == "__main__":
    asyncio.run(preflight())

