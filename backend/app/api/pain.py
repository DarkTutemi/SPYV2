"""Pain Discovery API."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.trends import GoogleTrendsAdapter
from app.core.database import get_db
from app.models.models import PainCluster, PainEvidence
from app.schemas.schemas import PainClusterRead, PainEvidenceRead
from app.services.pain_service import PainDiscoveryService

router = APIRouter()


class PainImportRequest(BaseModel):
    cluster_name: str
    core_problem: str
    category: Optional[str] = None
    evidence_items: list[dict[str, Any]]
    product_hypotheses: Optional[list[str]] = None
    search_keywords: Optional[list[str]] = None


@router.post("/import", status_code=201)
async def import_pain_cluster(
    payload: PainImportRequest,
    db: AsyncSession = Depends(get_db),
):
    """Import and cluster consumer pain evidence items."""
    service = PainDiscoveryService(db)
    cluster = await service.import_evidence_and_cluster(
        cluster_name=payload.cluster_name,
        core_problem=payload.core_problem,
        category=payload.category,
        evidence_items=payload.evidence_items,
        product_hypotheses=payload.product_hypotheses,
        search_keywords=payload.search_keywords,
    )
    return {"id": cluster.id, "name": cluster.name, "evidence_count": len(payload.evidence_items)}


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


@router.get("/clusters/{cluster_id}")
async def get_pain_cluster_detail(cluster_id: str, db: AsyncSession = Depends(get_db)):
    """Get full cluster with categorized evidence items."""
    service = PainDiscoveryService(db)
    detail = await service.get_cluster_detail(cluster_id)
    if not detail:
        raise HTTPException(404, "Pain cluster not found")
    return detail


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


@router.get("/trends/{keyword}")
async def get_trends(
    keyword: str,
    limit_days: int = Query(30, ge=7, le=90),
    db: AsyncSession = Depends(get_db),
):
    """Get Google Trends search interest trajectory for a product keyword in the US."""
    adapter = GoogleTrendsAdapter(db)
    await adapter.observe_keyword_interest(keyword)
    trajectory = await adapter.get_keyword_trajectory(keyword, limit_days)
    return {
        "keyword": keyword,
        "geo": "US",
        "data_points": len(trajectory),
        "trajectory": trajectory,
        "note": "Relative search interest score (0-100). Not an indicator of purchase demand or revenue.",
    }
