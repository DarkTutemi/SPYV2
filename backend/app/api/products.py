"""Products API — includes product intelligence report."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import (
    Advertisement, Advertiser, BundleOffer, OpportunityScore,
    Product, ProductCluster, ProductClusterMember, ProductDailyMetric,
)
from app.schemas.schemas import (
    BundleOfferRead, OpportunityScoreRead, ProductCreate,
    ProductDetail, ProductIntelligenceReport, ProductRead,
)

router = APIRouter()


@router.get("/", response_model=list[ProductRead])
async def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: Optional[str] = None,
    category: Optional[str] = None,
    country: str = "US",
    status: Optional[str] = None,
    bundle_qty: Optional[int] = None,
    is_physical: Optional[bool] = None,
    include_synthetic: bool = Query(False, description="Include synthetic test fixtures"),
    sort_by: str = "first_seen_at",
    db: AsyncSession = Depends(get_db),
):
    query = select(Product).where(Product.target_country == country)
    if not include_synthetic:
        query = query.where(
            Product.is_synthetic == False,
            ~Product.name.startswith("DEMO "),
        )
    if search:
        query = query.where(Product.name.ilike(f"%{search}%"))
    if category:
        query = query.where(Product.category == category)
    if status and status.upper() != "ALL":
        s_upper = status.upper()
        if s_upper in ("QUALIFIED", "QUALIFIED_OPPORTUNITY"):
            query = query.where(Product.opportunity_status.in_(["QUALIFIED", "QUALIFIED_OPPORTUNITY"]))
        elif s_upper == "QUALIFIED_AND_PROMISING":
            query = query.where(Product.opportunity_status.in_(["QUALIFIED", "QUALIFIED_OPPORTUNITY", "PROMISING"]))
        else:
            query = query.where(Product.opportunity_status == s_upper)
    if bundle_qty:
        query = query.where(Product.primary_bundle_qty == bundle_qty)
    if is_physical is not None:
        query = query.where(Product.is_physical == is_physical)

    if sort_by == "name":
        query = query.order_by(Product.name)
    else:
        query = query.order_by(Product.first_seen_at.desc())

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    return [ProductRead.model_validate(p) for p in result.scalars().all()]


@router.get("/ranked", response_model=list[dict])
async def ranked_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    min_emergence: float = 0,
    min_bundle: float = 0,
    min_confidence: float = 0,
    status: Optional[str] = None,
    bundle_qty: Optional[int] = None,
    is_physical: Optional[bool] = None,
    include_synthetic: bool = Query(False, description="Include synthetic test fixtures"),
    db: AsyncSession = Depends(get_db),
):
    """Products ranked by latest composite opportunity score with qualification filters."""
    # Subquery to pick only the latest score per product
    latest_score_sq = (
        select(
            OpportunityScore.product_id,
            func.max(OpportunityScore.score_date).label("max_date"),
        )
        .group_by(OpportunityScore.product_id)
        .subquery()
    )

    query = (
        select(OpportunityScore, Product)
        .join(
            latest_score_sq,
            (OpportunityScore.product_id == latest_score_sq.c.product_id)
            & (OpportunityScore.score_date == latest_score_sq.c.max_date),
        )
        .join(Product, OpportunityScore.product_id == Product.id)
        .where(Product.target_country == "US")
    )
    if not include_synthetic:
        query = query.where(
            Product.is_synthetic == False,
            ~Product.name.startswith("DEMO "),
            OpportunityScore.opportunity_status != "SYNTHETIC_FIXTURE",
        )
    if min_emergence > 0:
        query = query.where(OpportunityScore.emergence_score >= min_emergence)
    if min_bundle > 0:
        query = query.where(OpportunityScore.bundle_potential >= min_bundle)
    if min_confidence > 0:
        query = query.where(OpportunityScore.evidence_confidence >= min_confidence)
    if status and status.upper() != "ALL":
        s_upper = status.upper()
        if s_upper in ("QUALIFIED", "QUALIFIED_OPPORTUNITY"):
            query = query.where(OpportunityScore.opportunity_status.in_(["QUALIFIED", "QUALIFIED_OPPORTUNITY"]))
        elif s_upper == "QUALIFIED_AND_PROMISING":
            query = query.where(OpportunityScore.opportunity_status.in_(["QUALIFIED", "QUALIFIED_OPPORTUNITY", "PROMISING"]))
        else:
            query = query.where(OpportunityScore.opportunity_status == s_upper)
    if bundle_qty:
        query = query.where(OpportunityScore.natural_bundle_quantity == bundle_qty)
    if is_physical is not None:
        query = query.where(Product.is_physical == is_physical)

    query = query.order_by(OpportunityScore.composite_score.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "product": ProductRead.model_validate(row.Product).model_dump(),
            "score": OpportunityScoreRead.model_validate(row.OpportunityScore).model_dump(),
        }
        for row in rows
    ]


@router.get("/{product_id}", response_model=ProductRead)
async def get_product(product_id: str, db: AsyncSession = Depends(get_db)):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    return ProductRead.model_validate(product)


@router.get("/{product_id}/report", response_model=ProductIntelligenceReport)
async def product_report(product_id: str, db: AsyncSession = Depends(get_db)):
    """Full Product Intelligence Report (Section 8 of spec)."""
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")

    # Ad counts
    total_ads = (await db.execute(
        select(func.count(Advertisement.id)).where(Advertisement.product_id == product_id)
    )).scalar() or 0

    active_ads = (await db.execute(
        select(func.count(Advertisement.id)).where(
            Advertisement.product_id == product_id,
            Advertisement.is_active == True,
        )
    )).scalar() or 0

    # Advertiser count
    adv_count = (await db.execute(
        select(func.count(func.distinct(Advertisement.advertiser_id))).where(
            Advertisement.product_id == product_id
        )
    )).scalar() or 0

    # New ads in windows
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)

    async def count_new_ads(days: int) -> int:
        cutoff = now - timedelta(days=days)
        return (await db.execute(
            select(func.count(Advertisement.id)).where(
                Advertisement.product_id == product_id,
                Advertisement.first_seen_at >= cutoff,
            )
        )).scalar() or 0

    new_7d = await count_new_ads(7)
    new_14d = await count_new_ads(14)
    new_30d = await count_new_ads(30)

    # Bundle offers
    bundle_result = await db.execute(
        select(BundleOffer).where(BundleOffer.product_id == product_id)
    )
    bundles = [BundleOfferRead.model_validate(b) for b in bundle_result.scalars().all()]

    # Latest score
    score_result = await db.execute(
        select(OpportunityScore)
        .where(OpportunityScore.product_id == product_id)
        .order_by(OpportunityScore.score_date.desc())
        .limit(1)
    )
    score = score_result.scalar_one_or_none()

    # Competitor domains
    domains_result = await db.execute(
        select(func.distinct(Advertiser.domain))
        .join(Advertisement, Advertisement.advertiser_id == Advertiser.id)
        .where(Advertisement.product_id == product_id, Advertiser.domain.isnot(None))
    )
    competitor_domains = [d[0] for d in domains_result.all() if d[0]]

    # Daily metrics for momentum chart
    metrics_result = await db.execute(
        select(ProductDailyMetric)
        .where(ProductDailyMetric.product_id == product_id)
        .order_by(ProductDailyMetric.metric_date)
        .limit(90)
    )
    momentum_data = [
        {
            "date": m.metric_date,
            "ads": m.active_ad_count,
            "advertisers": m.unique_advertiser_count,
            "creatives": m.unique_creative_count,
        }
        for m in metrics_result.scalars().all()
    ]

    # Identify data gaps
    data_gaps = []
    if not product.image_url:
        data_gaps.append("No product image available")
    if not product.description:
        data_gaps.append("No product description")
    if not product.functional_use_case:
        data_gaps.append("Functional use case not identified")
    if not product.customer_pain:
        data_gaps.append("Customer pain point not identified")
    if adv_count == 0:
        data_gaps.append("No advertisers linked to this product")
    if total_ads == 0:
        data_gaps.append("No advertisements linked to this product")
    if not bundles:
        data_gaps.append("No bundle offers observed")
    if not score:
        data_gaps.append("Opportunity score not yet computed")
    if not momentum_data:
        data_gaps.append("No historical daily metrics available")

    return ProductIntelligenceReport(
        product=ProductRead.model_validate(product),
        customer_pain=product.customer_pain,
        us_market_verified=product.us_relevance_confidence.value in ("high", "medium"),
        first_observed=product.first_seen_at,
        observed_advertiser_count=adv_count,
        observed_active_ad_count=active_ads,
        new_ads_7d=new_7d,
        new_ads_14d=new_14d,
        new_ads_30d=new_30d,
        ad_persistence_days=(
            now - (product.first_seen_at if product.first_seen_at.tzinfo
                   else product.first_seen_at.replace(tzinfo=timezone.utc))
        ).days if product.first_seen_at else None,
        momentum_data=momentum_data,
        competitor_domains=competitor_domains,
        bundle_offers=bundles,
        bundle_types=list({b.bundle_mechanism.value for b in bundles if b.bundle_mechanism}),
        emergence_score=score.emergence_score if score else None,
        evidence_confidence=score.evidence_confidence if score else None,
        bundle_potential=score.bundle_potential if score else None,
        discovery_signal_score=score.discovery_signal_score if score else None,
        functional_benefit_score=score.functional_benefit_score if score else None,
        observed_momentum=score.observed_momentum if score else None,
        opportunity_status=score.opportunity_status if score else "NEW_DISCOVERY",
        status_reason=score.status_reason if score else None,
        natural_bundle_quantity=score.natural_bundle_quantity if score else None,
        score_components={
            "emergence": score.emergence_components,
            "confidence": score.confidence_components,
            "bundle": score.bundle_components,
        } if score else None,
        data_gaps=data_gaps,
    )


@router.post("/", response_model=ProductRead, status_code=201)
async def create_product(payload: ProductCreate, db: AsyncSession = Depends(get_db)):
    product = Product(**payload.model_dump())
    product.normalized_name = payload.name.lower().strip()
    db.add(product)
    await db.flush()
    await db.refresh(product)
    return ProductRead.model_validate(product)

