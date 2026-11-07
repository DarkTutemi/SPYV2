"""Scores API."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import OpportunityScore
from app.schemas.schemas import OpportunityScoreRead

router = APIRouter()


@router.get("/", response_model=list[OpportunityScoreRead])
async def list_scores(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    min_composite: float = 0,
    db: AsyncSession = Depends(get_db),
):
    query = select(OpportunityScore)
    if min_composite > 0:
        query = query.where(OpportunityScore.composite_score >= min_composite)
    query = query.order_by(OpportunityScore.composite_score.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    return [OpportunityScoreRead.model_validate(s) for s in result.scalars().all()]


@router.post("/compute", response_model=dict)
async def compute_scores(db: AsyncSession = Depends(get_db)):
    """Recompute deterministic scores for all US products (today's date, UTC)."""
    from app.engines.scoring import ScoringEngine
    scores = await ScoringEngine(db).score_all_products()
    return {"scored": len(scores)}

