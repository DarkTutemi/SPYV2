"""
US WIN HUNTER — Alerts & Scheduler API Routes

Provides:
- Alert listing, filtering, marking read/dismissed
- Manual pipeline trigger
- Scheduler status
- Pipeline run history
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import Alert, AlertType, AlertSeverity, SchedulerRunLog
from app.services.scheduler import get_scheduler

router = APIRouter()


# ── Alerts ───────────────────────────────────────────────────────────────

@router.get("/")
async def list_alerts(
    unread_only: bool = Query(False),
    alert_type: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List alerts with optional filters."""
    query = select(Alert)

    if unread_only:
        query = query.where(Alert.is_read == False, Alert.is_dismissed == False)
    if alert_type:
        try:
            query = query.where(Alert.alert_type == AlertType(alert_type))
        except ValueError:
            pass
    if entity_type:
        query = query.where(Alert.entity_type == entity_type)
    if severity:
        try:
            query = query.where(Alert.severity == AlertSeverity(severity))
        except ValueError:
            pass

    query = query.order_by(desc(Alert.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    alerts = result.scalars().all()

    # Count totals
    count_result = await db.execute(
        select(func.count(Alert.id)).where(
            Alert.is_read == False, Alert.is_dismissed == False
        )
    )
    unread_count = count_result.scalar() or 0

    return {
        "alerts": [
            {
                "id": a.id,
                "alert_type": a.alert_type.value,
                "severity": a.severity.value,
                "title": a.title,
                "description": a.description,
                "entity_type": a.entity_type,
                "entity_id": a.entity_id,
                "entity_name": a.entity_name,
                "data": a.data,
                "is_read": a.is_read,
                "is_dismissed": a.is_dismissed,
                "created_at": str(a.created_at),
            }
            for a in alerts
        ],
        "unread_count": unread_count,
    }


class MarkAlertRequest(BaseModel):
    alert_ids: list[str]
    action: str  # "read" or "dismiss"


@router.post("/mark")
async def mark_alerts(
    req: MarkAlertRequest,
    db: AsyncSession = Depends(get_db),
):
    """Mark alerts as read or dismissed."""
    result = await db.execute(
        select(Alert).where(Alert.id.in_(req.alert_ids))
    )
    alerts = list(result.scalars().all())

    for alert in alerts:
        if req.action == "read":
            alert.is_read = True
        elif req.action == "dismiss":
            alert.is_dismissed = True

    await db.flush()
    return {"marked": len(alerts), "action": req.action}


@router.get("/summary")
async def alert_summary(db: AsyncSession = Depends(get_db)):
    """Get alert counts by type and severity."""
    result = await db.execute(
        select(
            Alert.alert_type,
            Alert.severity,
            func.count(Alert.id),
        )
        .where(Alert.is_dismissed == False)
        .group_by(Alert.alert_type, Alert.severity)
    )
    rows = result.all()

    summary = {}
    for alert_type, severity, count in rows:
        key = alert_type.value
        if key not in summary:
            summary[key] = {"total": 0}
        summary[key][severity.value] = count
        summary[key]["total"] += count

    unread_result = await db.execute(
        select(func.count(Alert.id)).where(
            Alert.is_read == False, Alert.is_dismissed == False
        )
    )

    return {
        "by_type": summary,
        "unread_total": unread_result.scalar() or 0,
    }


# ── Scheduler ────────────────────────────────────────────────────────────

@router.get("/scheduler/status")
async def scheduler_status():
    """Get scheduler status."""
    scheduler = get_scheduler()
    return scheduler.status


@router.post("/scheduler/run")
async def run_pipeline():
    """Manually trigger the full intelligence pipeline."""
    scheduler = get_scheduler()
    result = await scheduler.run_pipeline_now("manual")
    return result


@router.get("/scheduler/history")
async def run_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get pipeline run history."""
    result = await db.execute(
        select(SchedulerRunLog)
        .order_by(desc(SchedulerRunLog.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    runs = result.scalars().all()
    return [
        {
            "id": r.id,
            "run_type": r.run_type,
            "started_at": str(r.started_at),
            "completed_at": str(r.completed_at) if r.completed_at else None,
            "status": r.status,
            "steps_completed": r.steps_completed,
            "errors": r.errors,
            "alerts_generated": r.alerts_generated,
        }
        for r in runs
    ]

