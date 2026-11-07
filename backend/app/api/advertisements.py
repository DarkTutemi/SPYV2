"""Advertisements API."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import Advertisement
from app.schemas.schemas import AdvertisementCreate, AdvertisementRead

router = APIRouter()


@router.get("/", response_model=list[AdvertisementRead])
async def list_advertisements(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    advertiser_id: Optional[str] = None,
    product_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    country: str = "US",
    db: AsyncSession = Depends(get_db),
):
    query = select(Advertisement).where(Advertisement.target_country == country)
    if advertiser_id:
        query = query.where(Advertisement.advertiser_id == advertiser_id)
    if product_id:
        query = query.where(Advertisement.product_id == product_id)
    if is_active is not None:
        query = query.where(Advertisement.is_active == is_active)
    query = query.order_by(Advertisement.first_seen_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    return [AdvertisementRead.model_validate(a) for a in result.scalars().all()]


@router.get("/{ad_id}", response_model=AdvertisementRead)
async def get_advertisement(ad_id: str, db: AsyncSession = Depends(get_db)):
    ad = await db.get(Advertisement, ad_id)
    if not ad:
        raise HTTPException(404, "Advertisement not found")
    return AdvertisementRead.model_validate(ad)

