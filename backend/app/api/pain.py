"""Pain Discovery API."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import PainCluster, PainEvidence
from app.schemas.schemas import PainClusterRead, PainEvidenceRead

router = APIRouter()


@router.get("/clusters", response_model=list[PainClusterRead])
async def list_pain_clusters(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(PainCluster)
    if category:
        query = query.where(PainCluster.category == category)
    query = query.order_by(PainCluster.frequency_score.desc().nullslast())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    return [PainClusterRead.model_validate(c) for c in result.scalars().all()]


@router.get("/clusters/{cluster_id}", response_model=PainClusterRead)
async def get_pain_cluster(cluster_id: str, db: AsyncSession = Depends(get_db)):
    cluster = await db.get(PainCluster, cluster_id)
    if not cluster:
        raise HTTPException(404, "Pain cluster not found")
    return PainClusterRead.model_validate(cluster)


@router.get("/clusters/{cluster_id}/evidence", response_model=list[PainEvidenceRead])
async def get_pain_evidence(
    cluster_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PainEvidence)
        .where(PainEvidence.cluster_id == cluster_id)
        .order_by(PainEvidence.original_date.desc().nullslast())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return [PainEvidenceRead.model_validate(e) for e in result.scalars().all()]

