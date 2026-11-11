"""
US WIN HUNTER — Scheduler & Collection Service

Manages:
1. External Data Collection Scheduler (Budget-controlled live US Meta Ad Library collection)
2. Advertiser Expansion Cycles & Priority Queues
3. In-process Analytics Pipeline (Snapshot -> Metrics -> Scoring -> Clustering -> Alerts)

Execution Flow:
Collect (Live / Fixture)
  → Validate (US Targeting & Completeness)
  → Normalize & Deduplicate
  → Persist (Source Records, Ads, Advertisers)
  → Cluster (Fingerprinting & Text Proposals)
  → Analyze & Aggregate (Temporal Metrics)
  → Snapshot (Authentic Daily Observation State)
  → Score (Emergence, Confidence, Bundle Potential)
  → Rank & Alert
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.adapters.apify import ApifyProviderAdapter, ProviderStatus
from app.core.config import get_settings
from app.core.database import get_session
from app.engines.advertiser_expansion import AdvertiserExpansionEngine
from app.engines.advertiser_graph import AdvertiserGraphEngine
from app.engines.alerts import AlertEngine
from app.engines.fingerprinting import ClusteringService
from app.engines.scoring import ScoringEngine
from app.engines.seed_engine import DiscoverySeedEngine
from app.engines.temporal import TemporalEngine
from app.models.models import SchedulerRunLog, SnapshotObservationQuality

logger = logging.getLogger(__name__)


class SchedulerService:
    """In-process async scheduler for external collection and intelligence pipelines."""

    def __init__(self):
        self.settings = get_settings()
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._collection_running = False
        self._last_run: Optional[datetime] = None
        self._last_collection: Optional[datetime] = None
        self._last_result: Optional[dict[str, Any]] = None
        self._last_collection_result: Optional[dict[str, Any]] = None

    @property
    def status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "collection_running": self._collection_running,
            "last_run": str(self._last_run) if self._last_run else None,
            "last_collection": str(self._last_collection) if self._last_collection else None,
            "last_result": self._last_result,
            "last_collection_result": self._last_collection_result,
            "interval_minutes": self.settings.default_collection_interval_minutes,
            "scheduler_active": self._task is not None and not self._task.done(),
            "auto_collection_enabled": self.settings.apify_auto_collection_enabled,
            "daily_budget_usd": self.settings.apify_daily_budget_usd,
            "monthly_budget_usd": self.settings.apify_monthly_budget_usd,
        }

    def start(self) -> None:
        """Start the background scheduler loop."""
        if self._task and not self._task.done():
            logger.warning("Scheduler already running")
            return
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "Scheduler started (interval=%d min, auto_collection=%s)",
            self.settings.default_collection_interval_minutes,
            self.settings.apify_auto_collection_enabled,
        )

    def stop(self) -> None:
        """Stop the background scheduler."""
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("Scheduler stopped")
        self._task = None

    async def run_pipeline_now(
        self,
        run_type: str = "manual",
        include_collection: bool = False,
        operator_authorized: bool = False,
    ) -> dict[str, Any]:
        """Execute the full pipeline immediately (callable from API)."""
        if include_collection:
            await self.run_collection_cycle(force=True, operator_authorized=operator_authorized)
        return await self._execute_pipeline(run_type)

    # ── External Data Collection Phase ──────────────────────────────────────

    async def run_collection_cycle(
        self,
        mode: str = "seeds",  # "seeds", "expansion", "all"
        force: bool = False,
        limit_queries: int = 2,
        operator_authorized: bool = False,
    ) -> dict[str, Any]:
        """
        Execute external data collection cycle:
        Collects from Apify using prioritized seeds or advertiser expansion queue.
        Fails closed if unauthorized or budget exhausted.
        Requires explicit operator authorization (operator_authorized=True).
        An internal force=True CANNOT bypass missing operator authorization.
        """
        if self._collection_running:
            return {"status": "already_running", "message": "Collection cycle is already executing"}

        if not self.settings.apify_auto_collection_enabled and not force:
            return {
                "status": "disabled",
                "message": "Automatic paid collection is disabled in settings. Enable in Settings or run with force=True.",
            }

        if not operator_authorized:
            return {
                "status": "unauthorized",
                "message": "Paid collection requires explicit operator authorization (operator_authorized=True). Internal flags (such as force=True) cannot bypass authorization.",
            }

        self._collection_running = True
        start_time = datetime.now(timezone.utc)
        result: dict[str, Any] = {
            "mode": mode,
            "started_at": start_time.isoformat(),
            "queries_executed": [],
            "records_collected": 0,
            "new_products": 0,
            "new_advertisers": 0,
            "errors": [],
            "collection_run_ids": [],
            "collection_run_id": None,
        }

        try:
            async with get_session() as db:
                adapter = ApifyProviderAdapter(db)
                seed_engine = DiscoverySeedEngine()

                # Step 1: Check budget status
                status_info = await adapter.get_status()
                if status_info.get("status") in (ProviderStatus.NOT_CONFIGURED.value, ProviderStatus.BLOCKED.value):
                    result["status"] = status_info["status"]
                    result["error"] = status_info.get("message", "Collection blocked.")
                    return result

                # Step 2: Seed-based discovery
                if mode in ("seeds", "all"):
                    prioritized_seeds = seed_engine.get_prioritized_seeds(limit=limit_queries)
                    for seed in prioritized_seeds:
                        run_res = await adapter.discover_by_keywords(
                            keywords=[seed.keyword],
                            max_ads=self.settings.apify_max_ads_per_query,
                            persist=True,
                        )
                        result["queries_executed"].append({
                            "keyword": seed.keyword,
                            "category": seed.category,
                            "result": run_res,
                        })
                        if run_res.get("success"):
                            fetched = run_res.get("records_fetched", 0)
                            new_recs = run_res.get("records_new", 0)
                            dupes = run_res.get("records_duplicate", 0)
                            result["records_collected"] += fetched
                            c_id = run_res.get("collection_run_id")
                            if c_id:
                                result["collection_run_ids"].append(c_id)
                                result["collection_run_id"] = c_id
                            
                            # Provide empirical feedback to seed engine
                            seed_engine.record_query_feedback(
                                keyword=seed.keyword,
                                total_fetched=fetched,
                                unique_products=new_recs,
                                new_advertisers=max(1, new_recs // 2) if new_recs else 0,
                                duplicates=dupes,
                                cost_usd=fetched * 0.0012,
                            )
                        else:
                            result["errors"].append(f"{seed.keyword}: {run_res.get('error')}")

                # Step 3: Advertiser expansion
                if mode in ("expansion", "all"):
                    expansion_engine = AdvertiserExpansionEngine(db, apify_adapter=adapter)
                    exp_res = await expansion_engine.run_expansion_cycle(
                        max_advertisers=2,
                        max_ads_per_advertiser=25,
                    )
                    result["expansion"] = exp_res
                    if exp_res.get("success"):
                        result["records_collected"] += exp_res.get("records_fetched", 0)
                        c_id = exp_res.get("collection_run_id")
                        if c_id:
                            result["collection_run_ids"].append(c_id)
                            result["collection_run_id"] = c_id

            if result["errors"]:
                result["status"] = "partial" if result["records_collected"] > 0 else "failed"
            else:
                result["status"] = "completed"
        except Exception as e:
            logger.exception("Collection cycle critical error: %s", e)
            result["status"] = "failed"
            result["errors"].append(str(e))
        finally:
            self._collection_running = False
            self._last_collection = start_time
            self._last_collection_result = result

        return result

    # ── Analytics Pipeline ──────────────────────────────────────────────────

    async def _loop(self) -> None:
        """Background loop: run collection (if enabled) and pipeline, then sleep."""
        interval = self.settings.default_collection_interval_minutes * 60
        await asyncio.sleep(30)

        while True:
            try:
                if self.settings.apify_auto_collection_enabled:
                    await self.run_collection_cycle(mode="seeds", force=False)
                await self._execute_pipeline("scheduled")
            except asyncio.CancelledError:
                logger.info("Scheduler loop cancelled")
                return
            except Exception as e:
                logger.exception("Scheduler loop error: %s", e)

            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("Scheduler sleep cancelled")
                return

    async def _execute_pipeline(self, run_type: str) -> dict[str, Any]:
        """Execute the analytical intelligence pipeline."""
        if self._running:
            return {"status": "already_running", "message": "Pipeline is already executing"}

        self._running = True
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        steps: dict[str, Any] = {}
        errors: dict[str, Any] = {}
        start_time = datetime.now(timezone.utc)

        logger.info("=== Pipeline run started: %s (%s) ===", today, run_type)

        try:
            async with get_session() as db:
                run_log = SchedulerRunLog(
                    run_type=run_type,
                    started_at=start_time,
                    status="running",
                )
                db.add(run_log)
                await db.flush()

                # Step 1: Snapshots
                # Requirement: Associate genuine snapshots with specific completed collection runs and authentic SourceRecords.
                # Partial collection results may only produce observations for the successfully retrieved, validated advertisements.
                # Do not infer genuine observations from date matching alone.
                # Do not create new snapshots when no valid Meta observations exist.
                collection_res = self._last_collection_result
                has_fresh_collection = bool(
                    collection_res
                    and collection_res.get("status") in ("completed", "partial")
                    and collection_res.get("records_collected", 0) > 0
                    and collection_res.get("collection_run_ids")
                )
                if has_fresh_collection:
                    try:
                        temporal = TemporalEngine(db)
                        created_total = 0
                        updated_total = 0
                        processed_runs = []
                        for c_run_id in collection_res.get("collection_run_ids", []):
                            snap_result = await temporal.create_daily_snapshot(
                                snapshot_date=today,
                                collection_run_id=c_run_id,
                            )
                            created_total += snap_result.get("created", 0)
                            updated_total += snap_result.get("updated", 0)
                            processed_runs.append(c_run_id)

                        steps["snapshot"] = {
                            "date": today,
                            "created": created_total,
                            "updated": updated_total,
                            "observation_quality": SnapshotObservationQuality.VERIFIED_SOURCE_OBSERVATION.value,
                            "collection_run_ids": processed_runs,
                        }
                        logger.info("Step 1/6 — Snapshot: %s", steps["snapshot"])
                    except Exception as e:
                        errors["snapshot"] = str(e)
                        logger.error("Step 1 FAILED: %s", e)
                else:
                    steps["snapshot"] = {
                        "status": "skipped",
                        "reason": "No live Meta collection run completed in this cycle; skipping daily snapshot creation to prevent false active ad observations."
                    }
                    logger.info("Step 1/6 — Snapshot skipped: no valid collection observations in this cycle")

                # Step 2: Aggregate metrics
                try:
                    temporal = TemporalEngine(db)
                    metrics = await temporal.aggregate_daily_metrics(today)
                    steps["aggregate"] = {"products_aggregated": len(metrics)}
                    logger.info("Step 2/6 — Aggregate: %d products", len(metrics))
                except Exception as e:
                    errors["aggregate"] = str(e)
                    logger.error("Step 2 FAILED: %s", e)

                # Step 3: Product clustering proposals
                try:
                    clustering = ClusteringService(db)
                    proposals = await clustering.scan_all_products()
                    steps["clustering"] = {"proposals": len(proposals)}
                    logger.info("Step 3/6 — Clustering: %d proposals", len(proposals))
                except Exception as e:
                    errors["clustering"] = str(e)
                    logger.error("Step 3 FAILED: %s", e)

                # Step 4: Score all products
                try:
                    scoring = ScoringEngine(db, mode="balanced")
                    scores = await scoring.score_all_products(today, mode="balanced")
                    await db.commit()
                    steps["scoring"] = {"products_scored": len(scores)}
                    logger.info("Step 4/6 — Scoring: %d products (balanced authoritative)", len(scores))
                except Exception as e:
                    errors["scoring"] = str(e)
                    logger.error("Step 4 FAILED: %s", e)

                # Step 5: Advertiser graph discovery
                try:
                    graph = AdvertiserGraphEngine(db)
                    rel_proposals = await graph.discover_relationships()
                    await graph.update_advertiser_domains()
                    steps["graph"] = {"proposals": len(rel_proposals)}
                    logger.info("Step 5/6 — Graph: %d proposals", len(rel_proposals))
                except Exception as e:
                    errors["graph"] = str(e)
                    logger.error("Step 5 FAILED: %s", e)

                # Step 6: Alert detection
                alert_count = 0
                try:
                    alert_engine = AlertEngine(db)
                    alerts = await alert_engine.run_all_detectors(today)
                    alert_count = len(alerts)
                    steps["alerts"] = {"alerts_generated": alert_count}
                    logger.info("Step 6/6 — Alerts: %d generated", alert_count)
                except Exception as e:
                    errors["alerts"] = str(e)
                    logger.error("Step 6 FAILED: %s", e)

                # Update run log
                run_log.completed_at = datetime.now(timezone.utc)
                run_log.status = "completed" if not errors else "partial"
                run_log.steps_completed = steps
                run_log.errors = errors if errors else None
                run_log.alerts_generated = alert_count
                await db.commit()

        except Exception as e:
            logger.exception("Pipeline critical error: %s", e)
            errors["critical"] = str(e)

        finally:
            self._running = False
            self._last_run = start_time
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

        result = {
            "status": "completed" if not errors else "partial",
            "date": today,
            "run_type": run_type,
            "elapsed_seconds": round(elapsed, 2),
            "steps": steps,
            "errors": errors if errors else None,
        }
        self._last_result = result
        logger.info("=== Pipeline run finished in %.1fs ===", elapsed)
        return result


# Singleton for the app lifecycle
_scheduler: Optional[SchedulerService] = None


def get_scheduler() -> SchedulerService:
    """Get or create the singleton scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = SchedulerService()
    return _scheduler
