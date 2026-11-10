"""
US WIN HUNTER — Multi-Source Apify Pilot Executor
Executes sequential discovery & validation runs across 6 approved Apify actors
under strict $1.80 USD total spending ceiling with provider-side maxTotalChargeUsd enforcement.
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.adapters.apify import ApifyProviderAdapter, APIFY_BASE_URL
from app.core.config import get_settings
from app.core.database import async_session_factory
from app.models.models import CollectionJobStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("multisource_pilot")

PILOT_BUDGET_CEILING_USD = 1.80

ACTOR_CONFIGS = [
    {
        "key": "tiktok_creative_center",
        "actor_id": "steadyscrape/tiktok-creative-center-scraper",
        "budget_cap": 0.40,
        "input": {
            "countries": ["US"],
            "period": "30",
            "keywords": [
                # 40% Watchlist verification
                "washable pee pad",
                "leakproof boxer",
                "spin mop",
                "chair leg protectors",
                "car detailing towels",
                "rug gripper",
                # 60% New candidate discovery
                "dog paw cleaner",
                "door draft stopper",
                "stripped screw remover",
                "couch cushion support",
            ],
            "maxAdsPerSearch": 6,
            "includeDetails": False,
            "sortBy": "for_you",
            "adLanguage": "any",
        },
    },
    {
        "key": "tiktok_shop_us",
        "actor_id": "tortuga/tiktok-shop-scraper",
        "budget_cap": 0.50,
        "input": {
            "searchTerms": [
                # 40% Watchlist verification
                "washable dog pee pad",
                "leakproof boxer briefs men",
                "spin mop replacement head",
                "silicone chair leg protectors",
                "car drying microfiber towel",
                "rug gripper non slip",
                # 60% New candidate discovery
                "paw cleaner dog cup",
                "under door draft stopper",
                "damaged screw extractor set",
                "couch cushion support board",
            ],
            "maxItems": 40,
            "includeDetails": False,
            "sortBy": "sales",
            "maxPagesPerSource": 1,
        },
    },
    {
        "key": "amazon_us",
        "actor_id": "scrapermagic/amazon-product-scraper",
        "budget_cap": 0.30,
        "input": {
            "country": "US",
            "searchQueries": [
                # 40% Watchlist
                "washable pee pads for dogs 3 pack",
                "incontinence boxer briefs men",
                "spin mop replacement heads pack",
                "chair leg floor protectors silicone",
                "microfiber drying towels car detailing",
                "rug grippers for hardwood floors",
                # 60% Discovery
                "muddy paw cleaner dog",
                "door draft stopper bottom of door",
                "screw extractor set stripped",
                "furniture sofa support inserts",
            ],
            "maxPagesPerQuery": 1,
            "maxItems": 40,
        },
    },
    {
        "key": "google_trends",
        "actor_id": "apify/google-trends-scraper",
        "budget_cap": 0.20,
        "input": {
            "searchTerms": [
                # Watchlist
                "washable dog pee pads",
                "leakproof underwear",
                "spin mop",
                "chair leg protectors",
                "car detailing towels",
                "rug grippers",
                # Discovery
                "dog paw cleaner",
                "door draft stopper",
                "screw extractor",
                "sofa cushion support",
            ],
            "geo": "US",
            "timeRange": "today 3-m",
            "maxItems": 10,
        },
    },
    {
        "key": "shopify_catalog",
        "actor_id": "inimi/shopify-store-scraper",
        "budget_cap": 0.20,
        "input": {
            "stores": [
                "diegospaws.com",
                "swiftlifty.com",
                "alexcove.com",
            ],
            "maxProductsPerStore": 20,
            "onlyAvailable": True,
            "includeDescription": True,
        },
    },
    {
        "key": "reddit_discussions",
        "actor_id": "offgrid-labs/reddit-scraper",
        "budget_cap": 0.20,
        "input": {
            "searchQueries": [
                "washable pee pads dogs",
                "leakproof boxers",
                "spin mop replacement",
                "chair leg protectors hardwood",
                "microfiber car towel",
                "rug grippers hardwood",
                "dog paw cleaner review",
                "door draft stopper",
            ],
            "subreddits": [
                "CleaningTips",
                "organization",
                "BuyItForLife",
                "Frugal",
                "dogs",
                "AutoDetailing",
            ],
            "searchInSubreddits": [
                "CleaningTips",
                "organization",
                "BuyItForLife",
                "Frugal",
                "dogs",
                "AutoDetailing",
            ],
            "sort": "hot",
            "timeFilter": "year",
            "maxItemsPerSource": 5,
            "includeComments": True,
            "maxCommentsPerPost": 3,
            "publicRequestBudget": 40,
        },
    },
]


async def run_single_actor(
    session,
    adapter: ApifyProviderAdapter,
    cfg: Dict[str, Any],
    cumulative_spend: float,
) -> Dict[str, Any]:
    key = cfg["key"]
    actor_id = cfg["actor_id"]
    budget_cap = cfg["budget_cap"]
    run_input = cfg["input"]

    # Calculate remaining headroom
    headroom = round(PILOT_BUDGET_CEILING_USD - cumulative_spend, 4)
    if headroom <= 0.01:
        logger.warning(f"Skipping {key}: cumulative spend ${cumulative_spend:.4f} reached ceiling ${PILOT_BUDGET_CEILING_USD:.2f}")
        return {
            "key": key,
            "actor_id": actor_id,
            "status": "SKIPPED_BUDGET_CEILING",
            "actual_cost_usd": 0.0,
            "records_fetched": 0,
            "items_saved": 0,
        }

    charge_limit = round(min(budget_cap, headroom), 4)
    logger.info(f"=== Starting {key} ({actor_id}) with maxTotalChargeUsd=${charge_limit:.4f} ===")

    # Database reservation
    can_reserve, run, job, budget_msg = await adapter.reserve_budget(
        job_name=f"pilot_{key}_{datetime.now(timezone.utc).strftime('%H%M%S')}",
        actor_name=actor_id,
        reservation_amount_usd=charge_limit,
        config={"pilot_key": key, "actor": actor_id, "budget_cap": charge_limit},
    )

    if not can_reserve or not run:
        logger.error(f"Failed to reserve budget in DB for {key}: {budget_msg}")
        return {
            "key": key,
            "actor_id": actor_id,
            "status": "RESERVATION_FAILED",
            "error": budget_msg,
            "actual_cost_usd": 0.0,
            "records_fetched": 0,
            "items_saved": 0,
        }

    apify_run_id = None
    try:
        actor_slug = actor_id.replace("/", "~")
        # 1. Start run with maxTotalChargeUsd parameter
        run_data = await adapter._start_actor_run(actor_slug, run_input, max_charge_usd=charge_limit)
        apify_run_id = run_data.get("id")
        dataset_id = run_data.get("defaultDatasetId")

        logger.info(f"Started Apify run {apify_run_id} (dataset: {dataset_id})")
        run.errors = {"apify_run_id": apify_run_id, "reserved_cost_usd": charge_limit, "cost_status": "RESERVED"}
        await session.commit()

        # 2. Wait for completion (max 240 seconds per actor)
        final_run = await adapter._wait_for_run_completion(apify_run_id, poll_interval=3.0, max_wait=240.0)
        final_status = final_run.get("status")
        logger.info(f"Apify run {apify_run_id} finished with status: {final_status}")

        # 3. Fetch Dataset Records
        raw_items = []
        if dataset_id:
            raw_items = await adapter.fetch_dataset(dataset_id)
        logger.info(f"Fetched {len(raw_items)} items from dataset {dataset_id}")

        # 4. Extract verified billing details
        billing = adapter.extract_billing_details(final_run, len(raw_items))
        actual_cost = float(billing.get("actual_cost_usd") or 0.0)
        logger.info(f"Billing for {key}: ${actual_cost:.4f} USD ({billing.get('cost_status')})")

        # 5. Save raw items to disk for audit & processing
        raw_file = Path(__file__).resolve().parent / f"pilot_raw_{key}.json"
        with open(raw_file, "w", encoding="utf-8") as f:
            json.dump(raw_items, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(raw_items)} items to {raw_file}")

        # 6. Update database record
        run.status = CollectionJobStatus.COMPLETED if final_status == "SUCCEEDED" else CollectionJobStatus.FAILED
        run.completed_at = datetime.now(timezone.utc)
        run.records_fetched = len(raw_items)
        run.coverage_notes = f"Multi-source pilot: {key} | ${actual_cost:.4f} USD ({billing.get('cost_status')})"
        run.errors = {
            "actual_cost_usd": actual_cost,
            "cost_status": billing.get("cost_status"),
            "billing": billing,
            "apify_run_id": apify_run_id,
            "dataset_id": dataset_id,
            "raw_file": str(raw_file),
        }
        await session.commit()

        return {
            "key": key,
            "actor_id": actor_id,
            "apify_run_id": apify_run_id,
            "dataset_id": dataset_id,
            "status": final_status,
            "actual_cost_usd": actual_cost,
            "cost_status": billing.get("cost_status"),
            "billing": billing,
            "records_fetched": len(raw_items),
            "raw_file": str(raw_file),
        }

    except Exception as e:
        logger.exception(f"Error during run {key}: {e}")
        held_cost = 0.0
        if apify_run_id:
            try:
                await adapter.abort_actor_run(apify_run_id)
            except Exception:
                pass
            held_cost = charge_limit

        run.status = CollectionJobStatus.FAILED
        run.completed_at = datetime.now(timezone.utc)
        run.errors = {
            "error": str(e),
            "cost_status": "FAILED_HELD" if held_cost > 0 else "FAILED",
            "actual_cost_usd": held_cost,
            "apify_run_id": apify_run_id,
        }
        await session.commit()

        return {
            "key": key,
            "actor_id": actor_id,
            "apify_run_id": apify_run_id,
            "status": "FAILED",
            "error": str(e),
            "actual_cost_usd": held_cost,
            "records_fetched": 0,
        }


async def main():
    logger.info(f"Starting Multi-Source Apify Pilot Execution (Ceiling: ${PILOT_BUDGET_CEILING_USD:.2f} USD)")
    manifest = {
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "budget_ceiling_usd": PILOT_BUDGET_CEILING_USD,
        "runs": [],
        "total_actual_cost_usd": 0.0,
    }

    cumulative_spend = 0.0

    async with async_session_factory() as session:
        adapter = ApifyProviderAdapter(db=session)

        for cfg in ACTOR_CONFIGS:
            res = await run_single_actor(session, adapter, cfg, cumulative_spend)
            manifest["runs"].append(res)
            run_cost = float(res.get("actual_cost_usd") or 0.0)
            cumulative_spend += run_cost
            manifest["total_actual_cost_usd"] = round(cumulative_spend, 4)
            logger.info(f"Cumulative spend so far: ${cumulative_spend:.4f} / ${PILOT_BUDGET_CEILING_USD:.2f}")

            # Sleep 2s between runs for rate limits
            await asyncio.sleep(2)

    manifest_file = Path(__file__).resolve().parent / "multisource_pilot_manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    logger.info(f"Pilot execution finished! Manifest written to {manifest_file}")
    logger.info(f"Final Total Cost: ${manifest['total_actual_cost_usd']:.4f} USD")


if __name__ == "__main__":
    asyncio.run(main())

