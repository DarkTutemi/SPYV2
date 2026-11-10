import urllib.request
import urllib.error
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.core.config import get_settings

settings = get_settings()
token = settings.apify_api_token
if not token:
    print("ERROR: No Apify token found in config.")
    sys.exit(1)

headers = {
    "User-Agent": "Mozilla/5.0",
    "Authorization": f"Bearer {token}"
}

print("=== 1. CHECK APIFY USER & ACCOUNT LIMITS ===")
try:
    req = urllib.request.Request("https://api.apify.com/v2/users/me", headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        user_data = json.loads(resp.read().decode("utf-8")).get("data", {})
        username = user_data.get("username")
        plan = user_data.get("plan", {})
        print(f"Username: {username}")
        print(f"Plan ID: {plan.get('id')}")
        print(f"Plan name: {plan.get('name')}")
        print(f"Plan isFree: {plan.get('isFree')}")
        print(f"Pricing model: {user_data.get('pricingModel')}")
        # Limits and credit
        limits = user_data.get("limits", {})
        print(f"Monthly usage USD limit: {limits.get('monthlyUsageUsd')}")
        print(f"Max monthly spend USD: {limits.get('maxMonthlyUsageUsd')}")
except Exception as e:
    print(f"Error checking user account: {e}")

# Check current usage this month:
try:
    req = urllib.request.Request("https://api.apify.com/v2/users/me/usage/monthly", headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        usage_data = json.loads(resp.read().decode("utf-8")).get("data", {})
        print(f"Current monthly usage USD: {usage_data.get('usageTotalUsd')}")
except Exception as e:
    print(f"Note on monthly usage endpoint: {e}")

candidate_actors = [
    ("steadyscrape/tiktok-creative-center-scraper", 0.40),
    ("tortuga/tiktok-shop-scraper", 0.50),
    ("scrapermagic/amazon-product-scraper", 0.30),
    ("apify/google-trends-scraper", 0.20),
    ("inimi/shopify-store-scraper", 0.20),
    ("offgrid-labs/reddit-scraper", 0.20),
]

print("\n=== 2. INSPECT 6 CANDIDATE ACTORS ===")
actor_reports = []

for actor_id, budget in candidate_actors:
    actor_slug = actor_id.replace("/", "~")
    url = f"https://api.apify.com/v2/acts/{actor_slug}"
    print(f"\nAuditing: {actor_id} (Budget cap: ${budget:.2f})")
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8")).get("data", {})
            title = data.get("title")
            pricing_infos = data.get("pricingInfos", [])
            is_public = data.get("isPublic")
            is_deprecated = data.get("isDeprecated")
            example_input = data.get("exampleRunInput", {})
            
            # Check pricing model
            print(f"  Title: {title}")
            print(f"  Public: {is_public}, Deprecated: {is_deprecated}")
            print(f"  Pricing info count: {len(pricing_infos)}")
            pricing_summary = []
            for p in pricing_infos:
                p_model = p.get("pricingModel")
                p_started = p.get("startedAt")
                p_events = p.get("pricingPerEvent", {})
                pricing_summary.append({"model": p_model, "events": list(p_events.get("actorChargeEvents", {}).keys()) if p_events else None})
                print(f"    Pricing model: {p_model}")
                if p_model == "PAY_PER_EVENT":
                    events = p_events.get("actorChargeEvents", {})
                    for ev_name, ev_data in events.items():
                        print(f"      Event '{ev_name}': price={ev_data.get('eventPriceUsd')} | tiered={ev_data.get('eventTieredPricingUsd')}")
                elif p_model == "PAY_PER_DATASET_ITEM":
                    print(f"      Per item price: {p.get('pricePerUnitUsd')}")
                elif p_model == "RENTAL":
                    print(f"      Rental price: {p.get('pricePerUnitUsd')}")
            
            # Fetch latest build input schema
            schema_url = f"https://api.apify.com/v2/acts/{actor_slug}/builds?limit=1&desc=true"
            req_b = urllib.request.Request(schema_url, headers=headers)
            properties = []
            with urllib.request.urlopen(req_b, timeout=10) as resp_b:
                builds = json.loads(resp_b.read().decode("utf-8")).get("data", {}).get("items", [])
                if builds:
                    b_id = builds[0].get("id")
                    b_detail_url = f"https://api.apify.com/v2/acts/{actor_slug}/builds/{b_id}"
                    req_bd = urllib.request.Request(b_detail_url, headers=headers)
                    with urllib.request.urlopen(req_bd, timeout=10) as resp_bd:
                        b_data = json.loads(resp_bd.read().decode("utf-8")).get("data", {})
                        raw_schema = b_data.get("inputSchema")
                        if raw_schema:
                            if isinstance(raw_schema, str):
                                raw_schema = json.loads(raw_schema)
                            properties = list(raw_schema.get("properties", {}).keys())
            print(f"  Input Schema Properties: {properties}")
            
            actor_reports.append({
                "actor_id": actor_id,
                "title": title,
                "status": "ACCESSIBLE",
                "budget_cap": budget,
                "pricing": pricing_summary,
                "properties": properties,
                "example_input": example_input.get("body") if isinstance(example_input, dict) else str(example_input)
            })
    except urllib.error.HTTPError as e:
        print(f"  HTTP Error {e.code}: {e.reason}")
        actor_reports.append({
            "actor_id": actor_id,
            "status": f"HTTP_ERROR_{e.code}",
            "error": str(e),
            "budget_cap": budget
        })
    except Exception as e:
        print(f"  Error: {e}")
        actor_reports.append({
            "actor_id": actor_id,
            "status": "ERROR",
            "error": str(e),
            "budget_cap": budget
        })

with open("multisource_actors_preflight.json", "w", encoding="utf-8") as f:
    json.dump(actor_reports, f, indent=2)

print("\nAudit written to multisource_actors_preflight.json")

