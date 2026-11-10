import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.adapters.apify import ApifyProviderAdapter
from app.core.database import async_session_factory
from app.models.models import CollectionJobStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("complete_tortuga")

RUN_ID = "U5nF1DlcD8gcsi9l3"
ACTOR_ID = "tortuga/tiktok-shop-scraper"
DATASET_ID = "i99KQUNfi3BAfYBOp"

async def main():
    async with async_session_factory() as session:
        adapter = ApifyProviderAdapter(db=session)
        logger.info(f"Waiting for {RUN_ID} to complete...")
        final_run = await adapter._wait_for_run_completion(RUN_ID, poll_interval=3.0, max_wait=240.0)
        final_status = final_run.get("status")
        logger.info(f"Run {RUN_ID} finished with status: {final_status}")

        raw_items = await adapter.fetch_dataset(DATASET_ID)
        logger.info(f"Fetched {len(raw_items)} items from dataset {DATASET_ID}")

        billing = adapter.extract_billing_details(final_run, len(raw_items))
        actual_cost = float(billing.get("actual_cost_usd") or 0.0)
        logger.info(f"Billing: ${actual_cost:.4f} USD ({billing.get('cost_status')})")

        raw_file = Path(__file__).resolve().parent / "pilot_raw_tiktok_shop_us.json"
        with open(raw_file, "w", encoding="utf-8") as f:
            json.dump(raw_items, f, indent=2, ensure_ascii=False)

        # Database record
        can_res, run, job, _ = await adapter.reserve_budget(
            job_name=f"pilot_tiktok_shop_us_completed",
            actor_name=ACTOR_ID,
            reservation_amount_usd=actual_cost if actual_cost > 0 else 0.05,
            config={"actor": ACTOR_ID, "run_id": RUN_ID},
        )
        if run:
            run.status = CollectionJobStatus.COMPLETED if final_status == "SUCCEEDED" else CollectionJobStatus.FAILED
            run.completed_at = datetime.now(timezone.utc)
            run.records_fetched = len(raw_items)
            run.coverage_notes = f"Multi-source pilot: tiktok_shop_us | ${actual_cost:.4f} USD ({billing.get('cost_status')})"
            run.errors = {
                "actual_cost_usd": actual_cost,
                "cost_status": billing.get("cost_status"),
                "billing": billing,
                "apify_run_id": RUN_ID,
                "dataset_id": DATASET_ID,
                "raw_file": str(raw_file),
            }
            await session.commit()

        # Update manifest
        manifest_file = Path(__file__).resolve().parent / "multisource_pilot_manifest.json"
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        # Replace or update the tiktok_shop_us entry
        new_entry = {
            "key": "tiktok_shop_us",
            "actor_id": ACTOR_ID,
            "apify_run_id": RUN_ID,
            "dataset_id": DATASET_ID,
            "status": final_status,
            "actual_cost_usd": actual_cost,
            "cost_status": billing.get("cost_status"),
            "billing": billing,
            "records_fetched": len(raw_items),
            "raw_file": str(raw_file),
        }

        updated_runs = []
        for r in manifest.get("runs", []):
            if r.get("key") == "tiktok_shop_us":
                updated_runs.append(new_entry)
            else:
                updated_runs.append(r)
        manifest["runs"] = updated_runs

        # Recalculate total cost
        total_cost = sum(float(r.get("actual_cost_usd") or 0.0) for r in updated_runs)
        manifest["total_actual_cost_usd"] = round(total_cost, 4)

        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        logger.info(f"Manifest successfully updated! New Total Pilot Cost: ${manifest['total_actual_cost_usd']:.4f} USD")

if __name__ == "__main__":
    asyncio.run(main())

