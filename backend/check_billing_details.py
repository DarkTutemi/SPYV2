import asyncio
import os
import sys
import json
from collections import defaultdict
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.database import async_session_factory
from app.models.models import CollectionRun

async def check_billing():
    async with async_session_factory() as db:
        runs = (await db.execute(select(CollectionRun).order_by(CollectionRun.created_at.asc()))).scalars().all()
        p10_runs = [r for r in runs if r.errors and "apify_run_id" in r.errors and r.errors.get("apify_run_id") != "mgrbhLt82lm2ybAZn"]
        
        print(f"=== BILLING RECONCILIATION FOR {len(p10_runs)} RUNS ===")
        total_billed = 0.0
        total_start_events = 0
        total_ad_events = 0
        
        for i, r in enumerate(p10_runs):
            err = r.errors or {}
            billing = err.get("billing", {})
            counts = billing.get("charged_event_counts", {})
            start_cnt = counts.get("start", 0)
            ad_cnt = counts.get("ad-scraped", 0)
            cost = float(err.get("actual_cost_usd", 0.0))
            total_billed += cost
            total_start_events += start_cnt
            total_ad_events += ad_cnt
            print(f"Task {i+1:2d} | Run: {err.get('apify_run_id')} | Query: {err.get('query')[:25]:25s} | Fetched: {r.records_fetched:2d} | Starts: {start_cnt} | Ads: {ad_cnt:2d} | Cost: ${cost:.4f} | Status: {billing.get('cost_status')}")

        print("--------------------------------------------------------------------------------")
        print(f"TOTALS: Runs={len(p10_runs)} | Fetched Ads={sum(r.records_fetched for r in p10_runs)} | Start Events={total_start_events} | Ad-Scraped Events={total_ad_events}")
        print(f"Total Database Reported Cost: ${total_billed:.4f}")
        
        # Calculate public pricing
        # Public pricing per event: start = $0.005, ad-scraped = $0.000575
        expected_free_tier = (total_start_events * 0.005) + (total_ad_events * 0.000575)
        print(f"Expected at Public Rate ($0.005/start + $0.000575/ad): ${expected_free_tier:.5f}")

if __name__ == "__main__":
    asyncio.run(check_billing())

