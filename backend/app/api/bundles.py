"""Bundles API."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.engines.bundle_engine import BundleIntelligenceEngine
from app.models.models import BundleOffer, Product
from app.schemas.schemas import BundleOfferCreate, BundleOfferRead

router = APIRouter()


class BundleAnalyzeRequest(BaseModel):
    page_content: Optional[str] = None
    source_url: Optional[str] = None


@router.get("/", response_model=list[BundleOfferRead])
async def list_bundles(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    product_id: Optional[str] = None,
    min_quantity: int = 1,
    db: AsyncSession = Depends(get_db),
):
    query = select(BundleOffer).where(BundleOffer.quantity >= min_quantity)
    if product_id:
        query = query.where(BundleOffer.product_id == product_id)
    query = query.order_by(BundleOffer.observed_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    return [BundleOfferRead.model_validate(b) for b in result.scalars().all()]


@router.post("/", response_model=BundleOfferRead, status_code=201)
async def create_bundle(payload: BundleOfferCreate, db: AsyncSession = Depends(get_db)):
    bundle = BundleOffer(**payload.model_dump())
    db.add(bundle)
    await db.flush()
    await db.refresh(bundle)
    return BundleOfferRead.model_validate(bundle)


@router.post("/analyze/{product_id}")
async def analyze_product_bundles(
    product_id: str,
    payload: Optional[BundleAnalyzeRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """Run Engine F bundle intelligence on a product."""
    engine = BundleIntelligenceEngine(db)
    page_content = payload.page_content if payload else None
    source_url = payload.source_url if payload else None
    try:
        return await engine.analyze_product_bundles(product_id, page_content, source_url)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/scenarios/{product_id}")
async def get_bundle_scenarios(
    product_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get $30-$90 AOV scenarios for preferred bundle sizes (3, 5, 10 units)."""
    engine = BundleIntelligenceEngine(db)
    try:
        return await engine.analyze_product_bundles(product_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

