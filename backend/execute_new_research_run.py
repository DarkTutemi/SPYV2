"""
US WIN HUNTER — Autonomous New Research Run Execution
Executes bounded new multi-source discovery across 10 fresh non-pet problem solvers.
- Run 1: Google Trends US (apify/google-trends-scraper, max $0.15)
- Run 2: Amazon US Benchmark (scrapermagic/amazon-product-scraper, max $0.15)
Total ceiling: $0.30 USD (within $2.00 session authorization).
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.core.config import get_settings
from app.core.database import async_session_factory
from app.models.models import (
    CollectionJob,
    CollectionRun,
    CollectionJobStatus,
    DataSource,
    DataSourceType,
)
from app.adapters.apify import APIFY_BASE_URL

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("new_research")

settings = get_settings()

MAX_TOTAL_SESSION_CAP = 2.00

NEW_RUNS_SPEC = [
    {
        "key": "google_trends_new_categories",
        "actor_id": "apify/google-trends-scraper",
        "budget_cap_usd": 0.15,
        "raw_output_file": "new_research_raw_trends.json",
        "input": {
            "searchTerms": [
                "stud finder wall scanner",
                "glass rinser for kitchen sink",
                "contour gauge profile tool",
                "oil dispenser with silicone brush",
                "drain clog remover tool snake",
                "blind spot mirrors car",
                "under couch toy blocker",
                "electric jar opener for seniors",
                "drywall repair patch kit",
                "car windshield defroster 12v",
            ],
            "geo": "US",
            "timeRange": "today 3-m",
            "maxItems": 10,
        },
    },
    {
        "key": "amazon_us_new_categories",
        "actor_id": "scrapermagic/amazon-product-scraper",
        "budget_cap_usd": 0.15,
        "raw_output_file": "new_research_raw_amazon.json",
        "input": {
            "country": "US",
            "searchQueries": [
                "glass rinser for kitchen sink metal",
                "contour gauge tool with lock",
                "electric jar opener for seniors hands free",
                "under bed blocker for toys clear",
            ],
            "maxPagesPerQuery": 1,
            "maxItems": 24,
        },
    },
]

async def execute_run():
    token = settings.apify_api_token
    if not token:
        logger.error("APIFY_API_TOKEN is missing!")
        return False

    base_dir = Path(__file__).resolve().parent
    headers = {"Authorization": f"Bearer {token}"}

    manifest = {
        "session_start_time": datetime.now(timezone.utc).isoformat(),
        "authorized_ceiling_usd": MAX_TOTAL_SESSION_CAP,
        "runs": [],
        "total_actual_cost_usd": 0.0,
    }

    cumulative_spend = 0.0

    async with httpx.AsyncClient(timeout=30.0) as client:
        for spec in NEW_RUNS_SPEC:
            key = spec["key"]
            actor_id = spec["actor_id"]
            budget_cap = spec["budget_cap_usd"]
            raw_file = base_dir / spec["raw_output_file"]
            run_input = spec["input"]

            remaining_headroom = round(MAX_TOTAL_SESSION_CAP - cumulative_spend, 4)
            if remaining_headroom <= 0.02:
                logger.warning(f"Skipping {key}: remaining headroom ${remaining_headroom} too low.")
                break

            actual_cap = min(budget_cap, remaining_headroom)
            logger.info(f"\n=======================================================")
            logger.info(f"STARTING RUN: {key} ({actor_id})")
            logger.info(f"Target Budget Cap: ${actual_cap:.4f} USD")

            actor_slug = actor_id.replace("/", "~")
            # 1. Start run with maxTotalChargeUsd parameter
            start_url = f"{APIFY_BASE_URL}/acts/{actor_slug}/runs?maxTotalChargeUsd={actual_cap}"
            start_resp = await client.post(start_url, json=run_input, headers=headers)
            if start_resp.status_code not in (200, 201):
                logger.error(f"Failed to start actor run {actor_id}: HTTP {start_resp.status_code} - {start_resp.text}")
                continue

            run_data = start_resp.json().get("data", {})
            apify_run_id = run_data.get("id")
            dataset_id = run_data.get("defaultDatasetId")
            logger.info(f"Apify Run ID: {apify_run_id} | Default Dataset: {dataset_id}")

            # 2. Wait for completion (max 180s)
            run_status = "RUNNING"
            poll_count = 0
            final_run_data = {}
            while run_status in ("RUNNING", "READY") and poll_count < 60:
                await asyncio.sleep(3.0)
                poll_count += 1
                poll_resp = await client.get(f"{APIFY_BASE_URL}/actor-runs/{apify_run_id}", headers=headers)
                if poll_resp.status_code == 200:
                    final_run_data = poll_resp.json().get("data", {})
                    run_status = final_run_data.get("status")
                    if poll_count % 5 == 0:
                        logger.info(f"Polling {key} (Run {apify_run_id}): status={run_status} ({poll_count*3}s)")

            logger.info(f"Run {apify_run_id} finished with status: {run_status}")

            # 3. Fetch Dataset Records
            items = []
            if dataset_id:
                ds_resp = await client.get(f"{APIFY_BASE_URL}/datasets/{dataset_id}/items?limit=100", headers=headers)
                if ds_resp.status_code == 200:
                    items = ds_resp.json()
            logger.info(f"Fetched {len(items)} items from dataset {dataset_id}")

            # Save raw dataset
            with open(raw_file, "w", encoding="utf-8") as f:
                json.dump(items, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved raw payload to {raw_file}")

            # 4. Extract verified billing
            usage_usd = float(final_run_data.get("usageTotalUsd", 0.0))
            charged_events = final_run_data.get("chargedEventCounts", {})
            logger.info(f"Verified Apify Run Cost: ${usage_usd:.4f} USD | Charged Events: {charged_events}")

            cumulative_spend += usage_usd

            run_entry = {
                "key": key,
                "actor_id": actor_id,
                "apify_run_id": apify_run_id,
                "dataset_id": dataset_id,
                "status": run_status,
                "records_fetched": len(items),
                "actual_cost_usd": round(usage_usd, 4),
                "charged_events": charged_events,
                "raw_file": str(raw_file.name),
            }
            manifest["runs"].append(run_entry)

    manifest["total_actual_cost_usd"] = round(cumulative_spend, 4)
    manifest["remaining_budget_usd"] = round(MAX_TOTAL_SESSION_CAP - cumulative_spend, 4)

    manifest_file = base_dir / "new_research_manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    logger.info(f"\n=======================================================")
    logger.info(f"NEW RESEARCH RUN COMPLETE!")
    logger.info(f"Total spent in this session: ${cumulative_spend:.4f} USD")
    logger.info(f"Remaining authorized budget: ${manifest['remaining_budget_usd']:.4f} USD")
    logger.info(f"Manifest written to {manifest_file}")

if __name__ == "__main__":
    asyncio.run(execute_run())

