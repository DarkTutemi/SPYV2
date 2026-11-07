"""
US WIN HUNTER — Scheduler Service

Background asyncio tasks for the daily intelligence pipeline.
Replaces Celery/Redis (not available) with in-process asyncio scheduling.

Pipeline steps (daily):
1. Create advertisement snapshots
2. Aggregate daily product metrics
3. Recompute all opportunity scores
4. Run advertiser graph discovery
5. Run alert detectors
6. Log the run

The scheduler is started at application startup and runs once per configured
interval (default: 6 hours). Can also be triggered manually via API.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from app.core.config import get_settings
from app.core.database import get_session
from app.engines.temporal import TemporalEngine
from app.engines.scoring import ScoringEngine
from app.engines.advertiser_graph import AdvertiserGraphEngine
from app.engines.alerts import AlertEngine
from app.models.models import SchedulerRunLog

logger = logging.getLogger(__name__)


class SchedulerService:
    """In-process async scheduler for the daily intelligence pipeline."""

    def __init__(self):
        self.settings = get_settings()
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._last_run: Optional[datetime] = None
        self._last_result: Optional[dict] = None

    @property
    def status(self) -> dict:
        return {
            "running": self._running,
            "last_run": str(self._last_run) if self._last_run else None,
            "last_result": self._last_result,
            "interval_minutes": self.settings.default_collection_interval_minutes,
            "scheduler_active": self._task is not None and not self._task.done(),
        }

    def start(self) -> None:
        """Start the background scheduler loop."""
        if self._task and not self._task.done():
            logger.warning("Scheduler already running")
            return
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "Scheduler started (interval=%d min)",
            self.settings.default_collection_interval_minutes,
        )

    def stop(self) -> None:
        """Stop the background scheduler."""
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("Scheduler stopped")
        self._task = None

    async def run_pipeline_now(self, run_type: str = "manual") -> dict:
        """Execute the full pipeline immediately (callable from API)."""
        return await self._execute_pipeline(run_type)

    # ── Internal ─────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        """Background loop: run pipeline then sleep."""
        interval = self.settings.default_collection_interval_minutes * 60

        # Initial delay: 30 seconds after startup to let things settle
        await asyncio.sleep(30)

        while True:
            try:
                await self._execute_pipeline("scheduled")
            except asyncio.CancelledError:
                logger.info("Scheduler loop cancelled")
                return
            except Exception as e:
                logger.exception("Scheduler pipeline error: %s", e)

            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("Scheduler sleep cancelled")
                return

    async def _execute_pipeline(self, run_type: str) -> dict:
        """Execute the full daily intelligence pipeline."""
        if self._running:
            return {"status": "already_running", "message": "Pipeline is already executing"}

        self._running = True
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        steps: dict = {}
        errors: dict = {}
        start_time = datetime.now(timezone.utc)

        logger.info("=== Pipeline run started: %s (%s) ===", today, run_type)

        try:
            async with get_session() as db:
                # Create run log
                run_log = SchedulerRunLog(
                    run_type=run_type,
                    started_at=start_time,
                    status="running",
                )
                db.add(run_log)
                await db.flush()

                # Step 1: Snapshots
                try:
                    temporal = TemporalEngine(db)
                    snap_result = await temporal.create_daily_snapshot(today)
                    steps["snapshot"] = snap_result
                    logger.info("Step 1/5 — Snapshot: %s", snap_result)
                except Exception as e:
                    errors["snapshot"] = str(e)
                    logger.error("Step 1 FAILED: %s", e)

                # Step 2: Aggregate metrics
                try:
                    temporal = TemporalEngine(db)
                    metrics = await temporal.aggregate_daily_metrics(today)
                    steps["aggregate"] = {"products_aggregated": len(metrics)}
                    logger.info("Step 2/5 — Aggregate: %d products", len(metrics))
                except Exception as e:
                    errors["aggregate"] = str(e)
                    logger.error("Step 2 FAILED: %s", e)

                # Step 3: Score all products
                try:
                    scoring = ScoringEngine(db)
                    scores = await scoring.score_all_products(today)
                    steps["scoring"] = {"products_scored": len(scores)}
                    logger.info("Step 3/5 — Scoring: %d products", len(scores))
                except Exception as e:
                    errors["scoring"] = str(e)
                    logger.error("Step 3 FAILED: %s", e)

                # Step 4: Advertiser graph discovery
                try:
                    graph = AdvertiserGraphEngine(db)
                    proposals = await graph.discover_relationships()
                    await graph.update_advertiser_domains()
                    steps["graph"] = {"proposals": len(proposals)}
                    logger.info("Step 4/5 — Graph: %d proposals", len(proposals))
                except Exception as e:
                    errors["graph"] = str(e)
                    logger.error("Step 4 FAILED: %s", e)

                # Step 5: Alert detection
                alert_count = 0
                try:
                    alert_engine = AlertEngine(db)
                    alerts = await alert_engine.run_all_detectors(today)
                    alert_count = len(alerts)
                    steps["alerts"] = {"alerts_generated": alert_count}
                    logger.info("Step 5/5 — Alerts: %d generated", alert_count)
                except Exception as e:
                    errors["alerts"] = str(e)
                    logger.error("Step 5 FAILED: %s", e)

                # Update run log
                run_log.completed_at = datetime.now(timezone.utc)
                run_log.status = "completed" if not errors else "partial"
                run_log.steps_completed = steps
                run_log.errors = errors if errors else None
                run_log.alerts_generated = alert_count

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

