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
from app.services.budget_manager import ApifyBudgetManager, BudgetExceededError

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

    async with async_session_factory() as db_session:
        bm = ApifyBudgetManager(
            db=db_session,
            api_token=token,
            session_ceiling_usd=MAX_TOTAL_SESSION_CAP,
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            for spec in NEW_RUNS_SPEC:
                key = spec["key"]
                actor_id = spec["actor_id"]
                budget_cap = spec["budget_cap_usd"]
                raw_file = base_dir / spec["raw_output_file"]
                run_input = spec["input"]

                # 1. RESERVE: Check durable budget availability
                can_run, reason, metrics = await bm.check_budget_availability(
                    requested_reservation_usd=budget_cap,
                    session_id="new_research_autonomous",
                )
                if not can_run:
                    logger.warning(f"Skipping {key}: durable budget gate rejected: {reason}")
                    break

                # Create durable spend reservation (RESERVED)
                reservation = await bm.create_reservation(
                    actor_id=actor_id,
                    reserved_amount_usd=budget_cap,
                    input_payload=run_input,
                    session_id="new_research_autonomous",
                )
                await db_session.commit()

                logger.info(f"\n=======================================================")
                logger.info(f"STARTING RUN: {key} ({actor_id}) [Reservation: {reservation.id}]")
                logger.info(f"Target Budget Cap: ${budget_cap:.4f} USD")

                # 2. MARK LAUNCH ATTEMPTED (A3 crash-after-start protection)
                await bm.mark_launch_attempted(reservation.id)
                await db_session.commit()

                actor_slug = actor_id.replace("/", "~")
                start_url = f"{APIFY_BASE_URL}/acts/{actor_slug}/runs?maxTotalChargeUsd={budget_cap}"

                try:
                    start_resp = await client.post(start_url, json=run_input, headers=headers)
                except Exception as e:
                    logger.error(f"Network exception starting {actor_id}: {e}")
                    # Could not reach network at all, but launch was attempted -> mark NEEDS_RECONCILIATION
                    await bm.reconcile_run(
                        reservation_id=reservation.id,
                        final_status="NEEDS_RECONCILIATION",
                        actual_cost_usd=budget_cap,
                        notes=f"Network exception during dispatch: {e}. Preserved reservation.",
                    )
                    await db_session.commit()
                    break

                if start_resp.status_code not in (200, 201):
                    # Ambiguous vs definitive start failures (Issue 3 hardening)
                    if 400 <= start_resp.status_code < 500:
                        logger.error(f"Definitive client error starting {actor_id}: HTTP {start_resp.status_code} - {start_resp.text}")
                        await bm.reconcile_run(
                            reservation_id=reservation.id,
                            final_status="FAILED",
                            actual_cost_usd=0.0,
                            billing_detail={
                                "http_status": start_resp.status_code,
                                "definitive_client_rejection": True,
                                "response_text": start_resp.text[:500],
                            },
                            notes=f"HTTP {start_resp.status_code} definitive client rejection by Apify on start (no run created)",
                        )
                        await db_session.commit()
                        if start_resp.status_code in (401, 403):
                            logger.error(f"Fatal auth error HTTP {start_resp.status_code}. Halting run sequence.")
                            break
                        continue
                    else:
                        logger.error(f"Ambiguous server error starting {actor_id}: HTTP {start_resp.status_code} - {start_resp.text}")
                        await bm.reconcile_run(
                            reservation_id=reservation.id,
                            final_status="NEEDS_RECONCILIATION",
                            actual_cost_usd=budget_cap,
                            billing_detail={
                                "http_status": start_resp.status_code,
                                "ambiguous_failure": True,
                                "response_text": start_resp.text[:500],
                            },
                            notes=f"HTTP {start_resp.status_code} ambiguous provider error during dispatch. Preserved full budget cap.",
                        )
                        await db_session.commit()
                        logger.warning("Ambiguous launch failure encountered. Halting sequence to prevent overspend.")
                        break

                try:
                    run_data = start_resp.json().get("data", {})
                except Exception as json_err:
                    logger.error(f"Failed to parse JSON from start response for {actor_id}: {json_err}")
                    await bm.reconcile_run(
                        reservation_id=reservation.id,
                        final_status="NEEDS_RECONCILIATION",
                        actual_cost_usd=budget_cap,
                        notes=f"Failed to parse JSON from start response: {json_err}. Preserved full budget cap.",
                    )
                    await db_session.commit()
                    break

                apify_run_id = run_data.get("id")
                dataset_id = run_data.get("defaultDatasetId")

                if not apify_run_id:
                    logger.error(f"Start response succeeded (HTTP {start_resp.status_code}) but omitted run id!")
                    await bm.reconcile_run(
                        reservation_id=reservation.id,
                        final_status="NEEDS_RECONCILIATION",
                        actual_cost_usd=budget_cap,
                        notes="Start response succeeded but omitted data.id. Preserved full budget cap.",
                    )
                    await db_session.commit()
                    break

                logger.info(f"Apify Run ID: {apify_run_id} | Default Dataset: {dataset_id}")

                # 3. SAVE REMOTE RUN ID & TRANSITION TO RUNNING
                await bm.mark_run_started(reservation.id, apify_run_id=apify_run_id)
                await db_session.commit()

                # 4. POLL & WAIT FOR TERMINAL STATE
                run_status = "RUNNING"
                poll_count = 0
                final_run_data = {}
                max_polls = 60  # 180 seconds total
                while run_status in ("RUNNING", "READY") and poll_count < max_polls:
                    await asyncio.sleep(3.0)
                    poll_count += 1
                    try:
                        poll_resp = await client.get(f"{APIFY_BASE_URL}/actor-runs/{apify_run_id}", headers=headers)
                        if poll_resp.status_code == 200:
                            final_run_data = poll_resp.json().get("data", {})
                            run_status = final_run_data.get("status")
                            if poll_count % 5 == 0:
                                logger.info(f"Polling {key} (Run {apify_run_id}): status={run_status} ({poll_count*3}s)")
                    except Exception as poll_err:
                        logger.warning(f"Transient polling error for {apify_run_id}: {poll_err}")

                logger.info(f"Run {apify_run_id} finished polling with status: {run_status}")

                # 5. HANDLE POLLING TIMEOUT (A4)
                if run_status in ("RUNNING", "READY"):
                    logger.warning(
                        f"Run {apify_run_id} did not terminate within {max_polls*3}s. "
                        "Marking NEEDS_RECONCILIATION and halting further runs."
                    )
                    await bm.mark_polling_timeout(
                        reservation_id=reservation.id,
                        apify_run_id=apify_run_id,
                        notes=f"Local polling window expired after {max_polls*3}s while Actor was still {run_status}",
                    )
                    await db_session.commit()
                    # Halting: do NOT start next provider while previous is unresolved
                    break

                # 6. READ DATASET (only if SUCCEEDED)
                items = []
                if run_status == "SUCCEEDED" and dataset_id:
                    try:
                        ds_resp = await client.get(f"{APIFY_BASE_URL}/datasets/{dataset_id}/items?limit=100", headers=headers)
                        if ds_resp.status_code == 200:
                            items = ds_resp.json()
                    except Exception as ds_err:
                        logger.error(f"Error fetching dataset {dataset_id}: {ds_err}")

                logger.info(f"Fetched {len(items)} items from dataset {dataset_id}")

                if items:
                    with open(raw_file, "w", encoding="utf-8") as f:
                        json.dump(items, f, indent=2, ensure_ascii=False)
                    logger.info(f"Saved raw payload to {raw_file}")

                # 7. VERIFY BILLING & RECONCILE
                usage_raw = final_run_data.get("usageTotalUsd")
                charged_events = final_run_data.get("chargedEventCounts", {})

                if usage_raw is None:
                    logger.warning(
                        f"Run {apify_run_id} missing usageTotalUsd in billing response! "
                        f"Retaining full budget cap ${budget_cap:.4f} USD to prevent overspend."
                    )
                    usage_usd = budget_cap
                    has_explicit_zero = False
                    billing_notes = "Missing usageTotalUsd in provider response; retained reserved budget cap."
                else:
                    usage_usd = float(usage_raw)
                    has_explicit_zero = (usage_usd == 0.0 and (
                        charged_events != {}
                        or final_run_data.get("is_free_tier") is True
                        or final_run_data.get("pricingInfo", {}).get("pricingModel") == "FREE"
                    ))
                    billing_notes = f"Verified provider usage: ${usage_usd:.4f} USD"

                logger.info(f"Verified Apify Run Cost: ${usage_usd:.4f} USD | Charged Events: {charged_events}")

                terminal_status = "SUCCEEDED" if run_status == "SUCCEEDED" else "FAILED"
                detail_payload = dict(final_run_data)
                if has_explicit_zero:
                    detail_payload["explicit_zero_charge_confirmed"] = True

                await bm.reconcile_run(
                    reservation_id=reservation.id,
                    final_status=terminal_status,
                    actual_cost_usd=usage_usd,
                    billing_detail=detail_payload,
                    notes=billing_notes,
                )
                await db_session.commit()

                # 8. UPDATE MANIFEST & ACCUMULATOR
                reconciled_res = await db_session.get(ApifySpendReservation, reservation.id)
                actual_spent = reconciled_res.actual_amount_usd if reconciled_res.actual_amount_usd is not None else usage_usd
                cumulative_spend += actual_spent

                run_entry = {
                    "key": key,
                    "actor_id": actor_id,
                    "apify_run_id": apify_run_id,
                    "dataset_id": dataset_id,
                    "status": run_status,
                    "records_fetched": len(items),
                    "actual_cost_usd": round(actual_spent, 4),
                    "charged_events": charged_events,
                    "raw_file": str(raw_file.name),
                }
                manifest["runs"].append(run_entry)

                # 9. CHECK TERMINAL STATUS: Only proceed to next provider if previous was cleanly resolved!
                if terminal_status != "SUCCEEDED":
                    logger.warning(f"Run {apify_run_id} finished with non-success status ({terminal_status}). Halting sequence.")
                    break

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

