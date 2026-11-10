"""
US WIN HUNTER — Phase 9 Test Suite: Discovery Quality & Multi-Category Expansion

Comprehensive verification for:
1. Synthetic Data Isolation: Synthetic records (is_synthetic=True, DEMO...) never appear in production API queries.
2. Evidence-Based Qualification States: DISCOVERED, PROMISING, QUALIFIED, REJECTED, SYNTHETIC_FIXTURE.
   - Products without observed prices cannot be QUALIFIED; they remain PROMISING.
3. Natural Bundle Quantity Handling: Pack counts are strictly parsed from observed facts; unobserved remain None/Unknown.
4. Multi-Category Discovery Taxonomy: 6 core US categories with exact resource allocation weights (sum = 1.00).
5. Advanced Discovery Strategies: Strategy A (Pain-First), Strategy B (Bundle-First), Strategy C (Advertiser-First).
6. Discovery Performance Tracking: Duplicate rate, cost per unique product, cost per PROMISING/QUALIFIED candidate.
"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.core.database import Base, engine, async_session_factory
from app.engines.bundle_engine import BundleIntelligenceEngine
from app.engines.scoring import ScoringEngine
from app.engines.seed_engine import (
    PHASE9_CORE_CATEGORIES,
    PainFirstDiscovery,
    BundleFirstDiscovery,
    AdvertiserFirstDiscovery,
    DiscoveryPerformanceTracker,
)
from app.main import app
from app.models.models import (
    Advertisement,
    Advertiser,
    DataSourceType,
    OpportunityScore,
    Product,
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


# ── 1. Synthetic Data Isolation ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_synthetic_records_isolated_from_production_api(db, client):
    """
    Synthetic fixtures and DEMO records must never appear in production ranked opportunity listings.
    """
    # 1 Real Product
    real_prod = Product(
        name="2026 Upgraded Spin Mop Replacement Heads with Scrubbing Pad",
        target_country="US",
        is_physical=True,
        is_synthetic=False,
        opportunity_status="PROMISING",
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    # 2 Synthetic Products
    demo_prod = Product(
        name="DEMO Leakproof Underwear",
        target_country="US",
        is_physical=True,
        is_synthetic=True,
        opportunity_status="SYNTHETIC_FIXTURE",
        source_type=DataSourceType.OTHER,
    )
    fixture_prod = Product(
        name="Handmade Test Fixture Mop",
        target_country="US",
        is_physical=True,
        is_synthetic=True,
        opportunity_status="SYNTHETIC_FIXTURE",
        source_type=DataSourceType.OTHER,
    )
    db.add_all([real_prod, demo_prod, fixture_prod])
    await db.flush()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    s_real = OpportunityScore(
        product_id=real_prod.id,
        score_date=today,
        opportunity_status="PROMISING",
        composite_score=91.0,
        bundle_potential=90.5,
        evidence_confidence=68.75,
        emergence_score=70.0,
    )
    s_demo = OpportunityScore(
        product_id=demo_prod.id,
        score_date=today,
        opportunity_status="SYNTHETIC_FIXTURE",
        composite_score=70.0,
        bundle_potential=90.0,
        evidence_confidence=15.0,
        emergence_score=60.0,
    )
    s_fix = OpportunityScore(
        product_id=fixture_prod.id,
        score_date=today,
        opportunity_status="SYNTHETIC_FIXTURE",
        composite_score=65.0,
        bundle_potential=85.0,
        evidence_confidence=12.0,
        emergence_score=50.0,
    )
    db.add_all([s_real, s_demo, s_fix])
    await db.commit()

    # Query production ranked endpoint (include_synthetic defaults to False)
    resp = await client.get("/api/v1/products/ranked")
    assert resp.status_code == 200
    data = resp.json()

    # Must contain ONLY the authentic product
    assert len(data) == 1
    assert data[0]["product"]["id"] == real_prod.id
    assert data[0]["product"]["is_synthetic"] is False
    assert data[0]["score"]["opportunity_status"] == "PROMISING"

    # Query with include_synthetic=true
    resp_synth = await client.get("/api/v1/products/ranked?include_synthetic=true")
    assert resp_synth.status_code == 200
    data_synth = resp_synth.json()
    assert len(data_synth) == 3


# ── 2. Evidence-Based Qualification: PROMISING vs QUALIFIED ───────────────────

@pytest.mark.asyncio
async def test_missing_price_gated_at_promising(db):
    """
    If observed price is missing, a product CANNOT be marked QUALIFIED.
    It must remain PROMISING until price evidence is obtained.
    """
    prod_no_price = Product(
        name="Microfiber Washable Cloth Refills",
        description="Washable replacement cloth refills for kitchen and bathroom.",
        target_country="US",
        is_physical=True,
        source_type=DataSourceType.META_AD_LIBRARY,
        source_url="https://cleaner.com/refills",
        min_price_usd=None,  # Price is unobserved in ad creative
        max_price_usd=None,
    )
    db.add(prod_no_price)
    await db.flush()

    adv1 = Advertiser(name="Brand One", domain="brandone.com", source_type=DataSourceType.META_AD_LIBRARY)
    adv2 = Advertiser(name="Brand Two", domain="brandtwo.com", source_type=DataSourceType.META_AD_LIBRARY)
    db.add_all([adv1, adv2])
    await db.flush()

    ad1 = Advertisement(
        product_id=prod_no_price.id,
        advertiser_id=adv1.id,
        external_id="ad_noprice_1",
        title="Microfiber Refill",
        body="Washable mop pads for daily cleaning",
        ad_url="https://facebook.com/ads/library/?id=3001",
        landing_page_url="https://brandone.com/refills",
        target_country="US",
        is_active=True,
        first_seen_at=datetime.now(timezone.utc),
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    ad2 = Advertisement(
        product_id=prod_no_price.id,
        advertiser_id=adv2.id,
        external_id="ad_noprice_2",
        title="Microfiber Refill",
        body="Super absorbent washable pads",
        ad_url="https://facebook.com/ads/library/?id=3002",
        landing_page_url="https://brandtwo.com/refills",
        target_country="US",
        is_active=True,
        first_seen_at=datetime.now(timezone.utc),
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    db.add_all([ad1, ad2])
    await db.commit()

    scoring_engine = ScoringEngine(db)
    score = await scoring_engine.score_product(prod_no_price.id)

    # High bundle and functional score, but missing price forces PROMISING
    assert score.bundle_potential >= 80.0
    assert score.functional_benefit_score >= 60.0
    assert score.observed_bundle_price_usd is None
    assert score.observed_single_price_usd is None
    assert score.opportunity_status == "PROMISING"
    assert "lacks verified observed checkout pricing" in score.status_reason


@pytest.mark.asyncio
async def test_observed_price_and_high_confidence_qualifies(db):
    """
    When observed pricing and high evidence confidence (>= 60%) exist, product becomes QUALIFIED.
    """
    prod_with_price = Product(
        name="Washable Microfiber Mop Pads Multi-Room 3-Pack",
        description="Washable reusable microfiber replacement pads for kitchen and bathroom rotation.",
        target_country="US",
        is_physical=True,
        source_type=DataSourceType.META_AD_LIBRARY,
        source_url="https://cleanpads.com/products/3-pack-pads",
        min_price_usd=19.99,  # Verified observed checkout price
        max_price_usd=19.99,
    )
    db.add(prod_with_price)
    await db.flush()

    adv1 = Advertiser(name="CleanPads Official", domain="cleanpads.com", source_type=DataSourceType.META_AD_LIBRARY)
    adv2 = Advertiser(name="HomeClean Hub", domain="homecleanhub.com", source_type=DataSourceType.META_AD_LIBRARY)
    db.add_all([adv1, adv2])
    await db.flush()

    ad1 = Advertisement(
        product_id=prod_with_price.id,
        advertiser_id=adv1.id,
        external_id="ad_qual_1",
        title="Microfiber Replacement Pads 3-Pack",
        body="Get your 3-pack replacement pads for $19.99. Washable rotation.",
        ad_url="https://facebook.com/ads/library/?id=4001",
        landing_page_url="https://cleanpads.com/products/3-pack-pads",
        target_country="US",
        is_active=True,
        first_seen_at=datetime.now(timezone.utc),
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    ad2 = Advertisement(
        product_id=prod_with_price.id,
        advertiser_id=adv2.id,
        external_id="ad_qual_2",
        title="Microfiber Replacement Pads 3-Pack",
        body="Keep one clean pad per room! 3-pack refill available.",
        ad_url="https://facebook.com/ads/library/?id=4002",
        landing_page_url="https://homecleanhub.com/pads",
        target_country="US",
        is_active=True,
        first_seen_at=datetime.now(timezone.utc),
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    db.add_all([ad1, ad2])
    await db.commit()

    scoring_engine = ScoringEngine(db)
    score = await scoring_engine.score_product(prod_with_price.id)

    assert score.opportunity_status in ("QUALIFIED", "QUALIFIED_OPPORTUNITY")
    assert score.evidence_confidence >= 60.0
    assert score.observed_single_price_usd == 19.99
    assert score.natural_bundle_quantity == 3


# ── 3. Unknown vs Observed Pack Count ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_bundle_quantity_remains_none_when_unobserved(db):
    """
    Without verified quantity-demand evidence in text, natural_bundle_quantity must be None (Unknown).
    """
    prod = Product(
        name="Mop Replacement Cloth",
        description="Washable microfiber pads fitting standard mops. Easy to wash and repeat.",
        target_country="US",
        is_physical=True,
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    db.add(prod)
    await db.commit()

    scoring_engine = ScoringEngine(db)
    score = await scoring_engine.score_product(prod.id)

    # Pack count was not specified in title/text, so it must remain None
    assert score.natural_bundle_quantity is None
    assert prod.primary_bundle_qty is None
    assert "Consumable refill with natural room-by-room rotation" in score.natural_quantity_rationale


# ── 4. Multi-Category Discovery Taxonomy ──────────────────────────────────────

def test_phase9_taxonomy_6_categories_and_weights():
    """
    Verify the 6 core US categories and their exact resource allocation weights sum to 1.00.
    """
    expected_weights = {
        "Home & Cleaning": 0.20,
        "Functional Apparel": 0.20,
        "Automotive": 0.15,
        "Pet Supplies": 0.15,
        "Household Essentials": 0.15,
        "Tools & Home Improvement": 0.15,
    }

    assert len(PHASE9_CORE_CATEGORIES) == 6
    total_weight = 0.0

    for cat_name, expected_w in expected_weights.items():
        assert cat_name in PHASE9_CORE_CATEGORIES
        cat_data = PHASE9_CORE_CATEGORIES[cat_name]
        assert cat_data["allocation_weight"] == pytest.approx(expected_w, rel=1e-3)
        total_weight += cat_data["allocation_weight"]

        # Check required fields per spec
        assert "problem_class" in cat_data
        assert "mechanism_of_action" in cat_data
        assert "natural_bundle_rationale" in cat_data
        assert "replenishment_logic" in cat_data
        assert "target_bundle_units" in cat_data
        assert "structured_seed_templates" in cat_data
        assert "exclusion_rules" in cat_data
        assert len(cat_data["structured_seed_templates"]) >= 3
        assert len(cat_data["exclusion_rules"]) >= 3

        # Verify structured seed queries contain Problem, Solution, Outcome, Audience, Context, Rationale
        for tmpl in cat_data["structured_seed_templates"]:
            assert "problem" in tmpl
            assert "solution" in tmpl
            assert "outcome" in tmpl
            assert "audience" in tmpl
            assert "usage_context" in tmpl
            assert "bundle_rationale" in tmpl
            assert "query" in tmpl

    assert total_weight == pytest.approx(1.00, rel=1e-3)


# ── 5. Advanced Discovery Strategies ──────────────────────────────────────────

def test_discovery_strategies():
    """Verify implementation of Strategy A, Strategy B, and Strategy C."""
    # Strategy A: Pain-First Discovery
    pain_strategy = PainFirstDiscovery(
        consumer_problem="Plantar fasciitis and severe heel pain",
        solution_class="graduated compression sleeve",
        target_category="Functional Apparel",
        keyword_variations=[
            "plantar fasciitis copper compression arch support sleeve pair 3 pack",
            "heel spur arch support compression brace 3 pack",
        ],
        bundle_rationale="3-pair rotation: one active, one backup, one in wash",
        target_bundle_units=[3, 5],
    )
    queries = pain_strategy.generate_ad_library_queries()
    assert len(queries) == 2
    assert "plantar fasciitis" in queries[0]

    # Strategy B: Bundle-First Discovery
    bundle_strategy = BundleFirstDiscovery(
        product_type="microfiber car drying towels",
        utility_mechanism="location_coverage",
        pack_scenarios=[3, 5, 10],
        target_aov_range="$30–$90",
        target_category="Automotive",
        search_queries=["twisted loop microfiber car drying towels 1200 gsm 3 pack"],
    )
    scenarios = bundle_strategy.validate_aov_feasibility(estimated_unit_cost=12.0)
    assert "3-pack" in scenarios
    assert scenarios["3-pack"]["fits_target_range"] is True  # 12 * 3 * 0.85 = 30.60
    assert "5-pack" in scenarios
    assert scenarios["5-pack"]["fits_target_range"] is True  # 12 * 5 * 0.85 = 51.00

    # Strategy C: Advertiser-First Discovery
    adv_strategy = AdvertiserFirstDiscovery(
        seed_advertiser_id="page_gridsparkl_1001",
        seed_advertiser_name="Gridsparkl",
        verified_category="Home & Cleaning",
        target_page_urls=["https://facebook.com/gridsparkl"],
        exploration_depth_bound=1,
        max_ads_per_advertiser=20,
    )
    assert adv_strategy.seed_advertiser_name == "Gridsparkl"
    assert adv_strategy.max_ads_per_advertiser == 20
    assert adv_strategy.exploration_depth_bound == 1


# ── 6. Discovery Performance Tracking ─────────────────────────────────────────

def test_discovery_performance_tracker():
    """Verify metrics calculation for queries, ads, clusters, candidates, and costs."""
    tracker = DiscoveryPerformanceTracker(
        queries_executed=6,
        total_ads_returned=60,
        unique_product_clusters=6,
        new_advertisers_discovered=8,
        promising_opportunities=4,
        qualified_opportunities=2,
        actual_cost_usd=0.015,  # $0.005 per 20 ads * 3 batches
    )

    report = tracker.to_dict()
    assert report["queries_executed"] == 6
    assert report["total_ads_returned"] == 60
    assert report["unique_product_clusters"] == 6
    assert report["new_advertisers_discovered"] == 8
    assert report["promising_opportunities"] == 4
    assert report["qualified_opportunities"] == 2
    assert report["actual_cost_usd"] == 0.015
    assert report["duplicate_rate"] == 0.90  # (60 - 6) / 60
    assert report["cost_per_unique_product_usd"] == pytest.approx(0.0025, rel=1e-3)
    assert report["cost_per_promising_usd"] == pytest.approx(0.00375, rel=1e-3)
    assert report["cost_per_qualified_usd"] == pytest.approx(0.0075, rel=1e-3)

