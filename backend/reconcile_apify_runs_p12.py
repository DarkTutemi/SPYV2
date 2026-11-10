import os
import sys
import json
import httpx
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

from app.core.config import get_settings

RUN_IDS = [
    ("Task 1", "iKit22V8CY5Dz9wWY", "pet hair stuck couch"),
    ("Task 2", "qehEjtV11TkOyN8QX", "underwear leak protection"),
    ("Task 3", "Ruma7EqpH8aipja3k", "car seat gap filler"),
    ("Task 4", "lYOIuNsGXIzS0lBQM", "muddy dog paws"),
    ("Task 5", "vZVWITQFEpxskC2AD", "cold air under door"),
    ("Task 6", "HQVaKKuIp58pd0vrd", "stripped screw removal"),
    ("Task 7", "cN59YoChPokHAmBeK", "washable cleaning pads"),
    ("Task 8", "H6KOMcYxXwfA1Mwip", "period underwear multipack"),
    ("Task 9", "SlcHRWFRtuxKCcGpg", "microfiber car detailing towels"),
    ("Task 10", "Nc9crwWQYDaaq989I", "reusable dog pee pads"),
    ("Task 11", "XYDCzWuRH0190bngr", "silicone chair leg protectors"),
    ("Task 12", "7Ui2nPmmD9mh9CSof", "drill brush attachment set"),
    ("Task 13", "6dmsJGawCaTgkdbXd", "1427580890438766"),
    ("Task 14", "1NR6k5n7xhhlJOD05", "1238627265989998"),
]

def reconcile():
    settings = get_settings()
    token = settings.apify_api_token
    if not token:
        print("ERROR: No APIFY_API_TOKEN found in settings.")
        return

    headers = {"Authorization": f"Bearer {token}"}
    client = httpx.Client(timeout=30.0)

    results = []
    total_usage_usd = 0.0
    verified_count = 0
    unverified_count = 0

    print("Fetching read-only Apify Run metadata for all 14 Phase 10 runs...")
    for task_name, run_id, query in RUN_IDS:
        url = f"https://api.apify.com/v2/actor-runs/{run_id}"
        try:
            resp = client.get(url, headers=headers)
            if resp.status_code != 200:
                print(f"[{task_name}] HTTP {resp.status_code} for {run_id}")
                results.append({
                    "task": task_name,
                    "run_id": run_id,
                    "query": query,
                    "status": "ERROR_FETCHING",
                    "http_status": resp.status_code,
                    "usage_total_usd": None,
                    "cost_status": "UNVERIFIED"
                })
                unverified_count += 1
                continue

            data = resp.json().get("data", {})
            status = data.get("status")
            stats = data.get("stats", {})
            usage = data.get("usage", {})
            usage_total = data.get("usageTotalUsd")
            pricing_info = data.get("pricingInfo", {})
            charged_events = data.get("chargedEventCounts", {})

            # Sometimes charged events are inside stats or usage
            if not charged_events and "chargedEventCounts" in stats:
                charged_events = stats.get("chargedEventCounts", {})

            cost_status = "VERIFIED" if usage_total is not None else "UNVERIFIED"
            if usage_total is not None:
                total_usage_usd += float(usage_total)
                verified_count += 1
            else:
                unverified_count += 1

            results.append({
                "task": task_name,
                "run_id": run_id,
                "query": query,
                "status": status,
                "usage_total_usd": usage_total,
                "charged_event_counts": charged_events,
                "pricing_model": pricing_info.get("pricingModel"),
                "cost_status": cost_status,
                "dataset_id": data.get("defaultDatasetId"),
                "started_at": data.get("startedAt"),
                "finished_at": data.get("finishedAt")
            })

            print(f"[{task_name}] Run: {run_id} | Status: {status} | UsageTotalUsd: ${usage_total} | Events: {charged_events}")

        except Exception as e:
            print(f"[{task_name}] Exception fetching {run_id}: {e}")
            results.append({
                "task": task_name,
                "run_id": run_id,
                "query": query,
                "status": "EXCEPTION",
                "error": str(e),
                "cost_status": "UNVERIFIED"
            })
            unverified_count += 1

    print("\n------------------------------------------------------------")
    print(f"Reconciliation Complete: {verified_count} Verified, {unverified_count} Unverified.")
    print(f"Total Confirmed Apify usageTotalUsd: ${total_usage_usd:.6f} USD")

    output_path = backend_dir / "apify_reconciliation_live.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Saved to {output_path}")

if __name__ == "__main__":
    reconcile()
