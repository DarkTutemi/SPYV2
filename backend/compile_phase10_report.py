import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.database import async_session_factory
from app.services.phase10_experiment import Phase10ExperimentService
from sqlalchemy import select
from app.models.models import CollectionRun

async def main():
    async with async_session_factory() as db:
        service = Phase10ExperimentService(db)
        # Find all 14 runs
        runs = (await db.execute(select(CollectionRun).order_by(CollectionRun.created_at.desc()).limit(20))).scalars().all()
        
        p10_runs = []
        for r in runs:
            err = r.errors or {}
            if "query" in err and "strategy" in err and "apify_run_id" in err:
                p10_runs.append(r)
        
        # Sort by task_id ascending
        p10_runs.sort(key=lambda x: (x.errors or {}).get("task_id", 0))
        
        task_results = []
        total_billed = 0.0
        exp_id = "exp_p10_20261109_182255"
        
        for r in p10_runs:
            err = r.errors or {}
            cost = float(err.get("actual_cost_usd", 0.0))
            total_billed += cost
            task_results.append({
                "task_id": err.get("task_id"),
                "strategy": err.get("strategy"),
                "category": err.get("category"),
                "query_or_seed": err.get("query"),
                "status": "SUCCEEDED",
                "apify_run_id": err.get("apify_run_id"),
                "dataset_id": err.get("dataset_id"),
                "ads_fetched": r.records_fetched,
                "ads_valid": r.records_fetched,
                "ads_new": r.records_new,
                "ads_duplicate": r.records_duplicate,
                "actual_cost_usd": cost,
                "billing": err.get("billing", {}),
            })
            
        print(f"Compiling report for {len(task_results)} tasks, exp_id={exp_id}, total_billed=${total_billed:.4f}...")
        report = await service.generate_experiment_report(exp_id, task_results, round(total_billed, 4))
        print("Report compiled successfully!")
        print(f"Total Billed USD:      ${report['total_billed_usd']:.4f}")
        print(f"Total Ads Collected:   {report['total_ads_collected']}")
        print(f"Total Unique Ads:      {report['total_unique_ads']}")
        print(f"Total Unique Products: {report['total_unique_products']}")
        print(f"Shortlist Count:       {report['shortlist_count']}")
        print(f"Report Path:           {report['report_path']}")

if __name__ == "__main__":
    asyncio.run(main())

