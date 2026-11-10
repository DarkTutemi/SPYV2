import asyncio
import os
import sys
import json
from collections import defaultdict
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.database import async_session_factory
from app.models.models import CollectionRun, SourceRecord, Advertisement, Product, Advertiser

async def check():
    async with async_session_factory() as db:
        runs = (await db.execute(select(CollectionRun).order_by(CollectionRun.created_at.desc()).limit(25))).scalars().all()
        for r in reversed(runs):
            err = r.errors or {}
            if "apify_run_id" in err:
                print(f"Run {err.get('apify_run_id')} | Query: '{err.get('query')}' | Strategy: {err.get('strategy')} | Fetched: {r.records_fetched} | Cost: ${err.get('actual_cost_usd')}")

        # Check raw data of source records from task 8 vs task 2
        # Find collection run for task 8
        t8_run = next((r for r in runs if (r.errors or {}).get("query") == "period underwear multipack"), None)
        if t8_run:
            print(f"Task 8 run errors: {t8_run.errors}")
            print(f"Task 8 notes: {t8_run.coverage_notes}")

if __name__ == "__main__":
    asyncio.run(check())

