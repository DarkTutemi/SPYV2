import asyncio
import os
import sys
import json
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.database import async_session_factory
from app.models.models import CollectionRun

async def update_billing():
    with open("backend/apify_reconciliation_live.json", encoding="utf-8") as f:
        reconciled = json.load(f)

    rec_by_run = {r["run_id"]: r for r in reconciled}

    async with async_session_factory() as db:
        runs = (await db.execute(select(CollectionRun))).scalars().all()
        updated_count = 0
        total_spent = 0.0

        for r in runs:
            err = r.errors or {}
            run_id = err.get("apify_run_id")
            if run_id in rec_by_run:
                rec = rec_by_run[run_id]
                actual_cost = float(rec["usage_total_usd"])
                err["actual_cost_usd"] = actual_cost
                err["cost_status"] = "VERIFIED_CHARGED"
                if "billing" not in err:
                    err["billing"] = {}
                err["billing"]["actual_cost_usd"] = actual_cost
                err["billing"]["cost_status"] = "VERIFIED_CHARGED"
                err["billing"]["charged_event_counts"] = rec["charged_event_counts"]
                err["billing"]["usage_total_usd"] = actual_cost
                
                # Flag modified for SQLAlchemy JSON
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(r, "errors")
                updated_count += 1
                total_spent += actual_cost

        await db.commit()
        print(f"Updated {updated_count} CollectionRun records with verified Apify charges.")
        print(f"Total Verified Spend in DB: ${total_spent:.5f} USD")

if __name__ == "__main__":
    asyncio.run(update_billing())

