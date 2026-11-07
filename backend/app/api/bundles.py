"""Bundles API."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import BundleOffer
from app.schemas.schemas import BundleOfferCreate, BundleOfferRead

router = APIRouter()


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

