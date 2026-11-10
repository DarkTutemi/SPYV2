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
        # Check run mgrbhLt82lm2ybAZn
        r = await client.get("https://api.apify.com/v2/actor-runs/mgrbhLt82lm2ybAZn", headers=headers)
        if r.status_code != 200:
            print(f"Error fetching run: {r.status_code} {r.text}")
            return
        data = r.json().get("data", {})
        keys_to_show = [
            "id", "actId", "status", "startedAt", "finishedAt",
            "usageTotalUsd", "eventUsageTotalUsd", "chargedTotalUsd",
            "pricingInfo", "chargedEventCounts", "stats", "options"
        ]
        filtered = {k: data.get(k) for k in keys_to_show}
        print("=== RUN DETAILS (mgrbhLt82lm2ybAZn) ===")
        print(json.dumps(filtered, indent=2))
        
        # Check actor pricing info
        act_r = await client.get("https://api.apify.com/v2/acts/automation-lab~facebook-ads-library", headers=headers)
        if act_r.status_code == 200:
            act_data = act_r.json().get("data", {})
            print("\n=== ACTOR PRICING INFO ===")
            print("Pricing Infos:", json.dumps(act_data.get("pricingInfos"), indent=2))
            print("Current Pricing:", json.dumps(act_data.get("currentPricingInfo"), indent=2))
            print("Stats:", json.dumps(act_data.get("stats"), indent=2))

if __name__ == "__main__":
    asyncio.run(check())

