"""
US WIN HUNTER — Analyst Review & Decision Support API

Implements operator decision workflow:
- Promising: Queue for creative testing or store listing
- Rejected: Not a winning product (with recorded reason)
- Needs More Data: Flag for closer tracking
- Testing: Currently running ads or live on store
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import AnalystReview, Product

router = APIRouter()


class ReviewCreateRequest(BaseModel):
    product_id: str
    reviewer: str = "operator"
    verdict: str  # promising, rejected, needs_more_data, testing
    notes: Optional[str] = None
    bundle_assessment: Optional[str] = None
    target_aov: Optional[float] = None
    target_bundle_qty: Optional[int] = None
    action_items: Optional[dict[str, Any]] = None


@router.post("/", status_code=201)
async def submit_analyst_review(
    payload: ReviewCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Record an operator's research decision on a product."""
    product = await db.get(Product, payload.product_id)
    if not product:
        raise HTTPException(404, f"Product not found: {payload.product_id}")

    valid_verdicts = {"promising", "rejected", "needs_more_data", "testing"}
    verdict_clean = payload.verdict.lower().strip()
    if verdict_clean not in valid_verdicts:
        raise HTTPException(
            400,
            f"Invalid verdict '{payload.verdict}'. Must be one of: {', '.join(sorted(valid_verdicts))}",
        )

    review = AnalystReview(
        product_id=payload.product_id,
        reviewer=payload.reviewer,
        verdict=verdict_clean,
        notes=payload.notes,
        bundle_assessment=payload.bundle_assessment,
        target_aov=payload.target_aov,
        target_bundle_qty=payload.target_bundle_qty,
        action_items=payload.action_items,
    )
    db.add(review)
    await db.flush()
    await db.refresh(review)

    return {
        "id": review.id,
        "product_id": review.product_id,
        "product_name": product.name,
        "verdict": review.verdict,
        "notes": review.notes,
        "target_aov": review.target_aov,
        "target_bundle_qty": review.target_bundle_qty,
        "created_at": str(review.created_at),
    }


@router.get("/")
async def list_reviews(
    verdict: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List operator decisions with optional verdict filter."""
    query = (
        select(AnalystReview, Product.name.label("product_name"), Product.image_url.label("product_image"))
        .join(Product, AnalystReview.product_id == Product.id)
    )
    if verdict:
        query = query.where(AnalystReview.verdict == verdict.lower().strip())

    query = query.order_by(desc(AnalystReview.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "id": r[0].id,
            "product_id": r[0].product_id,
            "product_name": r[1],
            "product_image": r[2],
            "reviewer": r[0].reviewer,
            "verdict": r[0].verdict,
            "notes": r[0].notes,
            "bundle_assessment": r[0].bundle_assessment,
            "target_aov": r[0].target_aov,
            "target_bundle_qty": r[0].target_bundle_qty,
            "action_items": r[0].action_items,
            "created_at": str(r[0].created_at),
        }
        for r in rows
    ]


@router.get("/product/{product_id}")
async def get_product_reviews(
    product_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get review history for a specific product."""
    result = await db.execute(
        select(AnalystReview)
        .where(AnalystReview.product_id == product_id)
        .order_by(desc(AnalystReview.created_at))
    )
    reviews = result.scalars().all()

    return [
        {
            "id": r.id,
            "reviewer": r.reviewer,
            "verdict": r.verdict,
            "notes": r.notes,
            "bundle_assessment": r.bundle_assessment,
            "target_aov": r.target_aov,
            "target_bundle_qty": r.target_bundle_qty,
            "action_items": r.action_items,
            "created_at": str(r.created_at),
        }
        for r in reviews
    ]

