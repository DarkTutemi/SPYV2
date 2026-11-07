"""Advertisers API."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import Advertiser, Advertisement
from app.schemas.schemas import AdvertiserCreate, AdvertiserRead, AdvertiserDetail

router = APIRouter()


@router.get("/", response_model=list[AdvertiserRead])
async def list_advertisers(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: Optional[str] = None,
    country: str = "US",
    db: AsyncSession = Depends(get_db),
):
    query = select(Advertiser).where(Advertiser.country == country)
    if search:
        query = query.where(Advertiser.name.ilike(f"%{search}%"))
    query = query.order_by(Advertiser.last_seen_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    return [AdvertiserRead.model_validate(a) for a in result.scalars().all()]


@router.get("/{advertiser_id}", response_model=AdvertiserDetail)
async def get_advertiser(advertiser_id: str, db: AsyncSession = Depends(get_db)):
    adv = await db.get(Advertiser, advertiser_id)
    if not adv:
        raise HTTPException(404, "Advertiser not found")

    # Count ads
    ad_count = (await db.execute(
        select(func.count(Advertisement.id)).where(Advertisement.advertiser_id == advertiser_id)
    )).scalar() or 0

    active_ad_count = (await db.execute(
        select(func.count(Advertisement.id)).where(
            Advertisement.advertiser_id == advertiser_id,
            Advertisement.is_active == True,
        )
    )).scalar() or 0

    # Count distinct products
    product_count = (await db.execute(
        select(func.count(func.distinct(Advertisement.product_id))).where(
            Advertisement.advertiser_id == advertiser_id,
            Advertisement.product_id.isnot(None),
        )
    )).scalar() or 0

    detail = AdvertiserDetail.model_validate(adv)
    detail.ad_count = ad_count
    detail.active_ad_count = active_ad_count
    detail.product_count = product_count
    return detail


@router.post("/", response_model=AdvertiserRead, status_code=201)
async def create_advertiser(payload: AdvertiserCreate, db: AsyncSession = Depends(get_db)):
    adv = Advertiser(**payload.model_dump())
    db.add(adv)
    await db.flush()
    await db.refresh(adv)
    return AdvertiserRead.model_validate(adv)


@router.get("/{advertiser_id}/ads", response_model=list)
async def get_advertiser_ads(
    advertiser_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    from app.schemas.schemas import AdvertisementRead
    result = await db.execute(
        select(Advertisement)
        .where(Advertisement.advertiser_id == advertiser_id)
        .order_by(Advertisement.first_seen_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return [AdvertisementRead.model_validate(a) for a in result.scalars().all()]

