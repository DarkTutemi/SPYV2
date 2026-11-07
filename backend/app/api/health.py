"""Health & Data Health API."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import (
    Advertisement, Advertiser, CollectionRun, DataSource, Product, ProductCluster,
    CollectionJobStatus,
)
from app.schemas.schemas import DataHealthReport, DataSourceRead, CollectionRunRead

router = APIRouter()


@router.get("/ping")
async def ping():
    return {"status": "ok", "service": "us-win-hunter"}


@router.get("/data", response_model=DataHealthReport)
async def data_health(db: AsyncSession = Depends(get_db)):
    # Sources
    sources_result = await db.execute(select(DataSource))
    sources = sources_result.scalars().all()

    # Counts
    adv_count = (await db.execute(select(func.count(Advertiser.id)))).scalar() or 0
    ad_count = (await db.execute(select(func.count(Advertisement.id)))).scalar() or 0
    prod_count = (await db.execute(select(func.count(Product.id)))).scalar() or 0
    cluster_count = (await db.execute(select(func.count(ProductCluster.id)))).scalar() or 0

    # Recent runs (last 20)
    runs_result = await db.execute(
        select(CollectionRun).order_by(CollectionRun.created_at.desc()).limit(20)
    )
    recent_runs = runs_result.scalars().all()

    # Failed jobs in last 24h
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    failed = (await db.execute(
        select(func.count(CollectionRun.id)).where(
            CollectionRun.status == CollectionJobStatus.FAILED,
            CollectionRun.created_at >= cutoff,
        )
    )).scalar() or 0

    return DataHealthReport(
        sources=[DataSourceRead.model_validate(s) for s in sources],
        recent_runs=[CollectionRunRead.model_validate(r) for r in recent_runs],
        total_advertisers=adv_count,
        total_advertisements=ad_count,
        total_products=prod_count,
        total_clusters=cluster_count,
        stale_sources=[],
        failed_jobs_24h=failed,
        integration_errors=[],
    )

