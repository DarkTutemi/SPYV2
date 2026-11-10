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
async def compute_scores(
    mode: Optional[str] = Query("balanced", description="Scoring mode (balanced authoritative default)"),
    db: AsyncSession = Depends(get_db),
):
    """Recompute deterministic scores for all US products (today's date, UTC). Always defaults to balanced scoring."""
    from fastapi import HTTPException
    from app.engines.scoring import ScoringEngine

    scoring_mode = (mode or "balanced").strip().lower()
    if scoring_mode != "balanced":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid scoring mode '{mode}'. Production opportunity scores strictly require mode='balanced' "
                "(v4_balanced_multimodel). Legacy unverified modes cannot mutate production rankings."
            ),
        )

    engine = ScoringEngine(db, mode=scoring_mode)
    scores = await engine.score_all_products(mode=scoring_mode)
    await db.commit()
    return {
        "scored": len(scores),
        "mode": scoring_mode,
        "weights_version": "v4_balanced_multimodel",
    }

