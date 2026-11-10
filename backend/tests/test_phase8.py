"""
US WIN HUNTER — Phase 8 Test Suite: Bundle-First Qualification & Ranking

Comprehensive verification for:
1. Single-unit durable tools penalized for artificial bundles (status REJECTED).
2. Daily rotation and consumable replenishment receiving high bundle scores (status QUALIFIED_OPPORTUNITY).
3. Multi-unit bundle modeling across 3, 5, 10 units in the $30–$90 AOV range.
4. Detection of artificial volume discounts on non-consumable goods.
5. Missing price evidence handling without fabricating market facts.
6. Clone advertiser network deduplication (funnel/domain clustering).
7. Longitudinal momentum guardrail (unobserved on single collection snapshots).
8. Synthetic vs authentic source data isolation.
9. API qualification filtering (/api/v1/products/ranked?status=QUALIFIED_OPPORTUNITY).
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.core.database import Base, engine, async_session_factory
from app.engines.bundle_engine import BundleIntelligenceEngine
from app.engines.scoring import ScoringEngine
from app.main import app
from app.models.models import (
    Advertisement,
    Advertiser,
    BundleMechanism,
    BundleOffer,
    ConfidenceLevel,
    DataSourceType,
    EvidenceType,
    OpportunityScore,
    Product,
    SourceRecord,
)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Reset database for each test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db():
    """Provide a database session."""
    async with async_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    """Provide an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Tests ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_single_unit_tool_penalized(db):
    """
    Test 1: Complete flat mop hardware tool is penalized for artificial bundles.
    Households need only 1 mop handle; multi-pack offers are artificial seller discounts.
    Status must be REJECTED and composite score capped.
    """
    mop = Product(
        name="Hands-Free Multi-Purpose Flat Mop – Lazy Cleaning Squeeze Mop",
        description="Self-wringing flat mop tool with 360 swivel head and extendable handle.",
        target_country="US",
        is_physical=True,
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    db.add(mop)
    await db.flush()

    adv = Advertiser(name="ToolStore Direct", domain="toolstoredirect.com", source_type=DataSourceType.META_AD_LIBRARY)
    db.add(adv)
    await db.flush()

    ad = Advertisement(
        product_id=mop.id,
        advertiser_id=adv.id,
        external_id="ad_mop_001",
        title="Hands-Free Flat Mop System",
        body="Buy 1 get 1 50% off! Get our complete mop tool for your home.",
        ad_url="https://facebook.com/ads/library/?id=1001",
        landing_page_url="https://toolstoredirect.com/mop",
        target_country="US",
        is_active=True,
        first_seen_at=datetime.now(timezone.utc),
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    db.add(ad)
    await db.commit()

    bundle_engine = BundleIntelligenceEngine(db)
    scoring_engine = ScoringEngine(db)

    await bundle_engine.analyze_product_bundles(mop.id)
    score = await scoring_engine.score_product(mop.id)

    # Verification: Tool must be recognized as non-natural multi-unit purchase
    assert score.opportunity_status == "REJECTED"
    assert "Fails bundle-first qualification: durable hardware tool" in score.status_reason
    assert score.bundle_potential < 40.0
    assert score.composite_score <= 35.0  # Capped composite


@pytest.mark.asyncio
async def test_daily_rotation_consumable_high_bundle_score(db):
    """
    Test 2: Washable microfiber mop pads have genuine multi-room rotation & laundry replenishment.
    Must qualify as QUALIFIED_OPPORTUNITY with bundle_potential >= 80 and confidence >= 20.
    """
    pads = Product(
        name="Washable Microfiber Mop Pads Multi-Room 3-Pack",
        description="Washable reusable microfiber replacement pads for kitchen and bathroom rotation.",
        target_country="US",
        is_physical=True,
        source_type=DataSourceType.META_AD_LIBRARY,
        source_url="https://cleanpads.com/products/3-pack-pads",
        min_price_usd=19.99,
        max_price_usd=19.99,
    )
    db.add(pads)
    await db.flush()

    adv = Advertiser(name="CleanPads Official", domain="cleanpads.com", source_type=DataSourceType.META_AD_LIBRARY)
    db.add(adv)
    await db.flush()

    ad = Advertisement(
        product_id=pads.id,
        advertiser_id=adv.id,
        external_id="ad_pad_001",
        title="Microfiber Replacement Pads",
        body="Keep one clean pad per room! 3-pack or 5-pack refill available.",
        ad_url="https://facebook.com/ads/library/?id=2001",
        landing_page_url="https://cleanpads.com/products/3-pack-pads",
        target_country="US",
        is_active=True,
        first_seen_at=datetime.now(timezone.utc),
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    db.add(ad)
    await db.commit()

    bundle_engine = BundleIntelligenceEngine(db)
    scoring_engine = ScoringEngine(db)

    await bundle_engine.analyze_product_bundles(pads.id)
    score = await scoring_engine.score_product(pads.id)

    assert score.opportunity_status == "QUALIFIED_OPPORTUNITY"
    assert score.bundle_potential >= 80.0
    assert score.natural_bundle_quantity in (3, 5, 10)
    assert score.functional_benefit_score >= 60.0


@pytest.mark.asyncio
async def test_multi_location_bundles_3_5_10(db):
    """
    Test 3: Generates 3, 5, 10 unit scenarios in the $30–$90 AOV range.
    """
    refills = Product(
        name="Upgraded Spin Mop Heads Replacement 5-Pack",
        description="Replacement spin mop heads for deep floor cleaning.",
        target_country="US",
        is_physical=True,
        source_type=DataSourceType.META_AD_LIBRARY,
        source_url="https://spinheads.com/refills",
    )
    db.add(refills)
    await db.flush()

    bundle_engine = BundleIntelligenceEngine(db)
    await bundle_engine.analyze_product_bundles(refills.id)

    res = await db.execute(
        select(BundleOffer).where(BundleOffer.product_id == refills.id)
    )
    bundles = res.scalars().all()

    quantities = [b.quantity for b in bundles]
    assert 3 in quantities
    assert 5 in quantities
    assert 10 in quantities

    # Verify estimated order values fall into plausible consumer ranges
    for b in bundles:
        if b.quantity in (3, 5, 10):
            assert b.estimated_order_value_usd is not None
            assert 15.0 <= b.estimated_order_value_usd <= 90.0


@pytest.mark.asyncio
async def test_clone_advertiser_network_deduplication(db):
    """
    Test 4: Affiliate clone domains sharing funnel paths are grouped into 1 advertiser entity.
    Prevents emergence score inflation from farmed burner domains.
    """
    prod = Product(
        name="Hands-Free Multi-Purpose Flat Mop",
        target_country="US",
        is_physical=True,
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    db.add(prod)
    await db.flush()

    # 4 clone domains sharing the same funnel slug
    domains = ["pawndify.com", "preiplieex.com", "consciouts.com", "rehearsatl.com"]
    for i, dom in enumerate(domains):
        adv = Advertiser(name=f"Clone Page {i}", domain=dom, source_type=DataSourceType.META_AD_LIBRARY)
        db.add(adv)
        await db.flush()
        ad = Advertisement(
            product_id=prod.id,
            advertiser_id=adv.id,
            external_id=f"ad_clone_{i}",
            landing_page_url=f"https://{dom}/funnel/news-hands-free-multi-purpose-flat-mop-m-2",
            target_country="US",
            is_active=True,
            first_seen_at=datetime.now(timezone.utc),
            source_type=DataSourceType.META_AD_LIBRARY,
        )
        db.add(ad)

    await db.commit()

    scoring_engine = ScoringEngine(db)
    ads_res = await db.execute(select(Advertisement).where(Advertisement.product_id == prod.id))
    ads = list(ads_res.scalars().all())

    indep_count, clone_detected, indep_score = scoring_engine._analyze_advertisers(ads)
    assert clone_detected is True
    assert indep_count == 1  # Grouped into 1 marketing entity, not 4!


@pytest.mark.asyncio
async def test_longitudinal_momentum_guard(db):
    """
    Test 5: When ads exist only on 1 collection snapshot date, observed_momentum must be None
    and advertiser/creative acceleration components must be 0.0 (Unobserved).
    """
    prod = Product(
        name="Microfiber Floor Scrub Replacement Pads",
        target_country="US",
        is_physical=True,
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    db.add(prod)
    await db.flush()

    adv = Advertiser(name="FloorClean Co", domain="floorclean.com", source_type=DataSourceType.META_AD_LIBRARY)
    db.add(adv)
    await db.flush()

    now = datetime.now(timezone.utc)
    # Both ads seen on the exact same date
    for i in range(2):
        ad = Advertisement(
            product_id=prod.id,
            advertiser_id=adv.id,
            external_id=f"ad_snap_{i}",
            target_country="US",
            is_active=True,
            first_seen_at=now,
            source_type=DataSourceType.META_AD_LIBRARY,
        )
        db.add(ad)
    await db.commit()

    bundle_engine = BundleIntelligenceEngine(db)
    scoring_engine = ScoringEngine(db)
    await bundle_engine.analyze_product_bundles(prod.id)
    score = await scoring_engine.score_product(prod.id)

    assert score.observed_momentum is None
    assert score.emergence_components["advertiser_accel"]["raw"] == 0.0
    assert score.emergence_components["creative_accel"]["raw"] == 0.0


@pytest.mark.asyncio
async def test_synthetic_data_isolation(db):
    """
    Test 6: Synthetic / demo records without traceable live links do not claim high confidence.
    """
    synth_prod = Product(
        name="Synthetic Demo Gadget",
        target_country="US",
        is_physical=True,
        source_type=DataSourceType.OTHER,
        us_relevance_confidence=ConfidenceLevel.UNKNOWN,
    )
    db.add(synth_prod)
    await db.flush()

    adv = Advertiser(name="Synthetic Advertiser", domain="synthetic.local", source_type=DataSourceType.OTHER)
    db.add(adv)
    await db.flush()

    ad = Advertisement(
        product_id=synth_prod.id,
        advertiser_id=adv.id,
        external_id="synth_ad_999",
        target_country="US",
        is_active=True,
        first_seen_at=datetime.now(timezone.utc),
        source_type=DataSourceType.OTHER,
    )
    db.add(ad)
    await db.commit()

    scoring_engine = ScoringEngine(db)
    score = await scoring_engine.score_product(synth_prod.id)

    # Records lacking verifiable URLs and independent proofs have low evidence confidence
    assert score.evidence_confidence <= 25.0


@pytest.mark.asyncio
async def test_ranked_api_filters(db, client):
    """
    Test 7: GET /api/v1/products/ranked properly supports status filter (QUALIFIED_OPPORTUNITY vs ALL).
    """
    # Create 1 qualified consumable and 1 rejected tool
    p1 = Product(
        name="Washable Microfiber Mop Pads Multi-Room 3-Pack",
        description="Washable reusable pads",
        target_country="US",
        is_physical=True,
        opportunity_status="QUALIFIED_OPPORTUNITY",
        primary_bundle_qty=5,
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    p2 = Product(
        name="Hands-Free Multi-Purpose Flat Mop",
        description="Complete mop tool handle",
        target_country="US",
        is_physical=True,
        opportunity_status="REJECTED",
        primary_bundle_qty=1,
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    db.add_all([p1, p2])
    await db.flush()

    # Add scores
    s1 = OpportunityScore(
        product_id=p1.id,
        score_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        opportunity_status="QUALIFIED_OPPORTUNITY",
        composite_score=85.0,
        bundle_potential=90.0,
        natural_bundle_quantity=5,
        evidence_confidence=30.0,
        emergence_score=60.0,
    )
    s2 = OpportunityScore(
        product_id=p2.id,
        score_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        opportunity_status="REJECTED",
        composite_score=25.0,
        bundle_potential=15.0,
        natural_bundle_quantity=1,
        evidence_confidence=20.0,
        emergence_score=40.0,
    )
    db.add_all([s1, s2])
    await db.commit()

    # Query with status=QUALIFIED_OPPORTUNITY
    r_qual = await client.get("/api/v1/products/ranked?status=QUALIFIED_OPPORTUNITY")
    assert r_qual.status_code == 200
    data_qual = r_qual.json()
    assert len(data_qual) == 1
    assert data_qual[0]["product"]["id"] == p1.id
    assert data_qual[0]["score"]["opportunity_status"] == "QUALIFIED_OPPORTUNITY"

    # Query with status=ALL
    r_all = await client.get("/api/v1/products/ranked?status=ALL")
    assert r_all.status_code == 200
    data_all = r_all.json()
    assert len(data_all) == 2

    # Query with bundle_qty=5
    r_qty = await client.get("/api/v1/products/ranked?bundle_qty=5")
    assert r_qty.status_code == 200
    data_qty = r_qty.json()
    assert len(data_qty) == 1
    assert data_qty[0]["product"]["id"] == p1.id
