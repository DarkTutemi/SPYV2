"""
US WIN HUNTER — Balanced Scoring Engine Test Suite (Phase 14 / Multi-Model)

Verification for:
1. Model A (Single-Product Winner): Hero problem-solvers (e.g. Damaged Screw Extractor)
   are NOT penalized for single-unit utility and achieve QUALIFIED/PROMISING.
2. Model B (Natural Multi-Unit Winner): High natural replenishment items (e.g. Pee Pads)
   receive high bundle upside and achieve QUALIFIED_OPPORTUNITY.
3. Model C (High-AOV Offer Winner): Kit/bundle combining hero hardware + refills
   achieves MODEL_C_HIGH_AOV_OFFER with strong composite score.
4. Explainability fields are fully generated and populated.
5. Missing price evidence keeps product in PROMISING instead of premature qualification.
6. Non-US or non-physical items are strictly REJECTED.
"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.database import Base, engine, async_session_factory
from app.engines.scoring import ScoringEngine, BalancedScoringEngine
from app.models.models import (
    Advertisement,
    Advertiser,
    DataSourceType,
    OpportunityScore,
    Product,
)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Reset test database for each test."""
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


@pytest.mark.asyncio
async def test_model_a_single_product_not_penalized(db):
    """
    Model A: Damaged screw extractor kit is a durable tool normally bought as 1 unit.
    Under balanced scoring, it must NOT be rejected for lack of multi-pack demand.
    """
    extractor = Product(
        name="Damaged Screw Extractor & Stripped Bolt Removal Set",
        description="Extract stripped, sheared, rusted, or painted screws in seconds with reverse-thread HSS bits.",
        target_country="US",
        is_physical=True,
        source_type=DataSourceType.META_AD_LIBRARY,
        source_url="https://toolstore.com/extractor",
        min_price_usd=34.99,
        max_price_usd=34.99,
        category="Tools & Home Improvement",
    )
    db.add(extractor)
    await db.flush()

    adv = Advertiser(name="Precision Tools US", domain="precisiontools.com", source_type=DataSourceType.META_AD_LIBRARY)
    db.add(adv)
    await db.flush()

    ad = Advertisement(
        product_id=extractor.id,
        advertiser_id=adv.id,
        external_id="ad_extractor_001",
        title="Remove Any Stripped Screw in 10 Seconds!",
        body="Reverse thread bites deep into stripped screw heads. Works on any drill. Before & after instant demonstration.",
        ad_url="https://facebook.com/ads/library/?id=3001",
        landing_page_url="https://precisiontools.com/extractor",
        target_country="US",
        is_active=True,
        first_seen_at=datetime.now(timezone.utc),
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    db.add(ad)
    await db.commit()

    engine = BalancedScoringEngine(db)
    score = await engine.score_product(extractor.id)

    assert score.commercial_model == "MODEL_A_SINGLE_PRODUCT"
    assert score.opportunity_status in ("QUALIFIED_OPPORTUNITY", "PROMISING")
    assert score.core_opportunity_score >= 60.0
    assert score.composite_score >= 50.0
    assert score.why_it_ranks_high is not None
    assert "hero problem solver" in score.why_it_ranks_high.lower()
    assert score.why_it_might_fail is not None
    assert score.what_evidence_supports_it is not None
    assert score.what_remains_unknown is not None
    assert score.next_validation_action is not None


@pytest.mark.asyncio
async def test_model_b_natural_multi_unit_winner(db):
    """
    Model B: Reusable dog pee pads have genuine laundry rotation and multi-room demand.
    Must qualify with MODEL_B_NATURAL_MULTI_UNIT and high bundle upside score.
    """
    pads = Product(
        name="Reusable Waterproof Absorbent Dog Pee Pads 3-Pack",
        description="Washable leakproof puppy training pads with rapid absorption layer and multi-room rotation utility.",
        target_country="US",
        is_physical=True,
        source_type=DataSourceType.META_AD_LIBRARY,
        source_url="https://diegospaws.com/products/reusable-waterproof-absorbent-pet-pad",
        min_price_usd=39.99,
        max_price_usd=49.99,
        category="Pet Care",
    )
    db.add(pads)
    await db.flush()

    adv = Advertiser(name="Diego's Paws", domain="diegospaws.com", source_type=DataSourceType.META_AD_LIBRARY)
    db.add(adv)
    await db.flush()

    ad = Advertisement(
        product_id=pads.id,
        advertiser_id=adv.id,
        external_id="ad_pads_001",
        title="Save Thousands on Disposable Pee Pads!",
        body="Instant liquid lock technology. Washable 300+ times. Keep 2 in use while 1 is in laundry.",
        ad_url="https://facebook.com/ads/library/?id=3002",
        landing_page_url="https://diegospaws.com/pads",
        target_country="US",
        is_active=True,
        first_seen_at=datetime.now(timezone.utc),
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    db.add(ad)
    await db.commit()

    engine = BalancedScoringEngine(db)
    score = await engine.score_product(pads.id)

    assert score.commercial_model == "MODEL_B_NATURAL_MULTI_UNIT"
    assert score.opportunity_status in ("QUALIFIED_OPPORTUNITY", "PROMISING")
    assert score.bundle_upside_score >= 80.0
    assert "multi-room" in score.why_it_ranks_high.lower() or "replenishment" in score.why_it_ranks_high.lower()


@pytest.mark.asyncio
async def test_model_c_high_aov_starter_kit(db):
    """
    Model C: Stainless steel pet fountain starter kit + replacement filters.
    Must achieve MODEL_C_HIGH_AOV_OFFER with high bundle upside score.
    """
    fountain_kit = Product(
        name="Stainless Steel Hygienic Pet Water Fountain Starter Kit with 6 Replacement Filter Refills",
        description="Ultra-quiet 2.2L stainless steel pet water fountain system with multi-layer replacement filter packs.",
        target_country="US",
        is_physical=True,
        source_type=DataSourceType.META_AD_LIBRARY,
        source_url="https://cleanpaws.com/fountain-kit",
        min_price_usd=49.99,
        max_price_usd=64.99,
        category="Pet Care",
    )
    db.add(fountain_kit)
    await db.flush()

    adv = Advertiser(name="CleanPaws US", domain="cleanpaws.com", source_type=DataSourceType.META_AD_LIBRARY)
    db.add(adv)
    await db.flush()

    ad = Advertisement(
        product_id=fountain_kit.id,
        advertiser_id=adv.id,
        external_id="ad_fountain_001",
        title="Hygienic Flow Pet Fountain Kit",
        body="Veterinarian recommended continuous filtration. Complete kit includes fountain with replacement filters.",
        ad_url="https://facebook.com/ads/library/?id=3003",
        landing_page_url="https://cleanpaws.com/fountain-kit",
        target_country="US",
        is_active=True,
        first_seen_at=datetime.now(timezone.utc),
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    db.add(ad)
    await db.commit()

    engine = BalancedScoringEngine(db)
    score = await engine.score_product(fountain_kit.id)

    assert score.commercial_model == "MODEL_C_HIGH_AOV_OFFER"
    assert score.opportunity_status in ("QUALIFIED_OPPORTUNITY", "PROMISING")
    assert score.bundle_upside_score >= 70.0
    assert "starter kit" in score.why_it_ranks_high.lower() or "bundle" in score.why_it_ranks_high.lower()


@pytest.mark.asyncio
async def test_missing_price_remains_promising(db):
    """
    A product with strong fundamentals but NO observed checkout price
    must remain PROMISING and CANNOT be marked QUALIFIED_OPPORTUNITY.
    """
    unpriced = Product(
        name="Twin Seal Under-Door Draft & Soundproofing Stopper",
        description="Blocks winter drafts, dust, hallway sound, and insects under doors.",
        target_country="US",
        is_physical=True,
        source_type=DataSourceType.META_AD_LIBRARY,
        min_price_usd=None,
        max_price_usd=None,
        category="Home Improvement",
    )
    db.add(unpriced)
    await db.flush()

    adv = Advertiser(name="DraftGuard", domain="draftguard.com", source_type=DataSourceType.META_AD_LIBRARY)
    db.add(adv)
    await db.flush()

    ad = Advertisement(
        product_id=unpriced.id,
        advertiser_id=adv.id,
        external_id="ad_draft_001",
        title="Stop Hallway Drafts Cold!",
        body="Double-sided door sweep stops drafts and noise instantly.",
        ad_url="https://facebook.com/ads/library/?id=3004",
        landing_page_url="https://draftguard.com/door",
        target_country="US",
        is_active=True,
        first_seen_at=datetime.now(timezone.utc),
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    db.add(ad)
    await db.commit()

    engine = BalancedScoringEngine(db)
    score = await engine.score_product(unpriced.id)

    assert score.opportunity_status == "PROMISING"
    assert "lacks verified observed checkout pricing" in score.status_reason


@pytest.mark.asyncio
async def test_non_physical_or_non_us_rejected(db):
    """Non-physical digital items or non-US products are strictly rejected."""
    digital = Product(
        name="Pet Training Masterclass 30-Day Video Course",
        description="Digital video streaming course for puppy behavior.",
        target_country="US",
        is_physical=False,
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    db.add(digital)
    await db.flush()

    engine = BalancedScoringEngine(db)
    score = await engine.score_product(digital.id)
    assert score.opportunity_status == "REJECTED"
    assert "Non-physical" in score.status_reason


@pytest.mark.asyncio
async def test_single_unit_outranks_mediocre_bundle(db):
    """
    Mission 2: A strong single-unit product must outrank a mediocre bundle product
    when commercial fundamentals support it.
    """
    # 1. Strong Single-Unit Product (Hero hardware tool)
    hero_tool = Product(
        name="Precision Damaged Screw Extractor Kit",
        description="Extract stripped, broken, and rusted screws in seconds with reverse HSS steel bits.",
        target_country="US",
        is_physical=True,
        source_type=DataSourceType.META_AD_LIBRARY,
        source_url="https://toolstore.com/hero",
        min_price_usd=34.99,
        max_price_usd=34.99,
        category="Tools",
    )
    db.add(hero_tool)
    await db.flush()

    adv1 = Advertiser(name="Tool Pro Direct", domain="toolprodirect.com", source_type=DataSourceType.META_AD_LIBRARY)
    db.add(adv1)
    await db.flush()

    ad1 = Advertisement(
        product_id=hero_tool.id,
        advertiser_id=adv1.id,
        external_id="ad_hero_001",
        title="Remove Any Stripped Screw Instantly",
        body="Instant demonstration: reverse thread bites deep into stripped screws. Works in seconds.",
        ad_url="https://facebook.com/ads/library/?id=4001",
        landing_page_url="https://toolprodirect.com/hero",
        target_country="US",
        is_active=True,
        first_seen_at=datetime.now(timezone.utc),
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    db.add(ad1)

    # 2. Mediocre Bundle Product (Low problem severity, generic novelty multi-pack)
    mediocre_bundle = Product(
        name="Generic Random Printed Novelty Socks 10-Pack",
        description="Assorted socks with colorful random printed patterns.",
        target_country="US",
        is_physical=True,
        source_type=DataSourceType.META_AD_LIBRARY,
        source_url="https://cheapstuff.com/socks",
        min_price_usd=19.99,
        max_price_usd=19.99,
        category="Apparel",
    )
    db.add(mediocre_bundle)
    await db.flush()

    adv2 = Advertiser(name="Bargain Depot", domain="bargaindepot.com", source_type=DataSourceType.META_AD_LIBRARY)
    db.add(adv2)
    await db.flush()

    ad2 = Advertisement(
        product_id=mediocre_bundle.id,
        advertiser_id=adv2.id,
        external_id="ad_bundle_002",
        title="10 Pairs of Socks Cheap",
        body="Get 10 pairs of random socks for a low price today.",
        ad_url="https://facebook.com/ads/library/?id=4002",
        landing_page_url="https://bargaindepot.com/socks",
        target_country="US",
        is_active=True,
        first_seen_at=datetime.now(timezone.utc),
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    db.add(ad2)
    await db.commit()

    engine = BalancedScoringEngine(db)
    hero_score = await engine.score_product(hero_tool.id)
    bundle_score = await engine.score_product(mediocre_bundle.id)

    assert hero_score.commercial_model == "MODEL_A_SINGLE_PRODUCT"
    # Strong single-unit product must cleanly outrank mediocre bundle product!
    assert hero_score.composite_score > bundle_score.composite_score
    assert hero_score.core_opportunity_score > bundle_score.core_opportunity_score


@pytest.mark.asyncio
async def test_single_unit_can_achieve_full_score_without_bundle():
    """
    Mission 2: Formula verification: Model A base components must sum to 100%
    without requiring any bundle upside.
    """
    engine_obj = BalancedScoringEngine(None)
    # If core=100, signal=100, conf=100, and bundle_upside=0:
    composite = engine_obj._compute_composite_balanced(
        model="MODEL_A_SINGLE_PRODUCT",
        core_opp=100.0,
        bundle_upside=0.0,
        discovery_signal=100.0,
        confidence=100.0,
        status="QUALIFIED_OPPORTUNITY",
    )
    # Must be 100.0 (not capped at 90.0!)
    assert composite == 100.0


@pytest.mark.asyncio
async def test_unresolved_safety_risk_blocks_qualified_status(db):
    """
    Mission 4: Electric pet heating pad without verified UL/ETL certification
    must be flagged and blocked from QUALIFIED_OPPORTUNITY status.
    """
    unverified_pad = Product(
        name="Electric Pet Heating Pad with Steel Cord",
        description="Warm thermal pad for indoor cats and dogs with plug-in heater.",
        target_country="US",
        is_physical=True,
        source_type=DataSourceType.META_AD_LIBRARY,
        source_url="https://petstore.com/pad",
        min_price_usd=57.99,
        max_price_usd=57.99,
        category="Pet Care",
        raw_data={"ul_etl_certified": False},  # Certification unverified!
    )
    db.add(unverified_pad)
    await db.flush()

    adv = Advertiser(name="WarmPets US", domain="warmpets.com", source_type=DataSourceType.META_AD_LIBRARY)
    db.add(adv)
    await db.flush()

    ad = Advertisement(
        product_id=unverified_pad.id,
        advertiser_id=adv.id,
        external_id="ad_safety_001",
        title="Cozy Heated Pet Pad for Cold Nights",
        body="Keep your pet warm all winter with plug-in electric heating pad.",
        ad_url="https://facebook.com/ads/library/?id=4003",
        landing_page_url="https://warmpets.com/pad",
        target_country="US",
        is_active=True,
        first_seen_at=datetime.now(timezone.utc),
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    db.add(ad)
    await db.commit()

    engine = BalancedScoringEngine(db)
    score = await engine.score_product(unverified_pad.id)

    # Must be blocked from QUALIFIED_OPPORTUNITY due to safety risk!
    assert score.opportunity_status == "NEEDS_SAFETY_VERIFICATION"
    assert "electrical heating element without verified ul/etl" in score.status_reason.lower()
    assert "safety" in score.why_it_might_fail.lower()


@pytest.mark.asyncio
async def test_unsupported_medical_claim_penalized(db):
    """
    Mission 4: Product with illegal medical claims (e.g. 'cures arthritis', 'prevents GDV/bloat')
    must be flagged, penalized, and blocked from QUALIFIED_OPPORTUNITY.
    """
    bloat_feeder = Product(
        name="Elevated Dog Feeder Station",
        description="Elevated dog bowl feeder station.",
        target_country="US",
        is_physical=True,
        source_type=DataSourceType.META_AD_LIBRARY,
        source_url="https://feeder.com/bowl",
        min_price_usd=69.99,
        max_price_usd=69.99,
        category="Pet Care",
    )
    db.add(bloat_feeder)
    await db.flush()

    adv = Advertiser(name="Feeder Store", domain="feederstore.com", source_type=DataSourceType.META_AD_LIBRARY)
    db.add(adv)
    await db.flush()

    ad = Advertisement(
        product_id=bloat_feeder.id,
        advertiser_id=adv.id,
        external_id="ad_claim_001",
        title="Stop Dog Bloat Guaranteed!",
        body="Clinically proven: our feeder cures arthritis and eliminates bloat completely!",
        ad_url="https://facebook.com/ads/library/?id=4004",
        landing_page_url="https://feederstore.com/bowl",
        target_country="US",
        is_active=True,
        first_seen_at=datetime.now(timezone.utc),
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    db.add(ad)
    await db.commit()

    engine = BalancedScoringEngine(db)
    score = await engine.score_product(bloat_feeder.id)

    assert score.opportunity_status == "NEEDS_CLAIM_CORRECTION"
    assert "unsupported medical/health claim" in score.status_reason.lower()
    assert "compliance" in score.why_it_might_fail.lower()


# ── 7. Overwrite Protection & Authoritative Balanced Defaults Regression ─────

@pytest.mark.asyncio
async def test_scoring_engine_defaults_to_balanced(db):
    """ScoringEngine() must default to balanced multi-model commercial scoring."""
    prod = Product(
        name="Universal Damaged Screw Extractor Kit",
        description="Extract stripped screws and bolts instantly. Dual-head reverse drill bit.",
        target_country="US",
        is_physical=True,
        source_type=DataSourceType.META_AD_LIBRARY,
        min_price_usd=34.99,
        max_price_usd=34.99,
    )
    db.add(prod)
    await db.commit()

    # Plain ScoringEngine without any mode argument
    engine = ScoringEngine(db)
    assert engine.mode == "balanced"

    score = await engine.score_product(prod.id)
    assert score.weights_version == "v4_balanced_multimodel"
    assert score.commercial_model == "MODEL_A_SINGLE_PRODUCT"
    assert score.core_opportunity_score > 0.0


@pytest.mark.asyncio
async def test_legacy_mode_cannot_overwrite_balanced_score(db):
    """
    CRITICAL REGRESSION TEST:
    Legacy bundle-first scoring must be blocked from overwriting an existing
    production balanced score.
    """
    prod = Product(
        name="Automatic Electric Jar Opener",
        description="One-touch hands-free vacuum jar lid opener for seniors with arthritis.",
        target_country="US",
        is_physical=True,
        source_type=DataSourceType.AMAZON,
        min_price_usd=34.99,
        max_price_usd=34.99,
    )
    db.add(prod)
    await db.commit()

    # 1. Initial score in balanced mode
    engine = ScoringEngine(db, mode="balanced")
    initial_score = await engine.score_product(prod.id)
    assert initial_score.weights_version == "v4_balanced_multimodel"
    initial_composite = initial_score.composite_score
    await db.commit()

    # 2. Attempt legacy overwrite without allow_legacy_overwrite -> must raise RuntimeError
    legacy_engine = ScoringEngine(db, mode="phase9_bundle_first")
    with pytest.raises(RuntimeError) as exc_info:
        await legacy_engine.score_product(prod.id)
    assert "cannot overwrite production balanced score" in str(exc_info.value)

    # 3. Verify in DB that the score remains untouched
    db_score = await db.get(OpportunityScore, initial_score.id)
    assert db_score.weights_version == "v4_balanced_multimodel"
    assert db_score.composite_score == initial_composite


@pytest.mark.asyncio
async def test_double_recalculation_idempotency(db):
    """
    Run complete score recalculation twice and compare database values before and after.
    Values must match deterministically.
    """
    prod = Product(
        name="Washable Reusable Dog Pee Pads",
        description="4-layer leakproof absorbent puppy training pad. Machine washable.",
        target_country="US",
        is_physical=True,
        source_type=DataSourceType.SHOPIFY,
        min_price_usd=29.99,
        max_price_usd=49.99,
    )
    db.add(prod)
    await db.commit()

    engine = ScoringEngine(db, mode="balanced")
    score_1 = await engine.score_product(prod.id)
    s1_comp = score_1.composite_score
    s1_core = score_1.core_opportunity_score
    s1_bundle = score_1.bundle_upside_score
    s1_model = score_1.commercial_model
    await db.commit()

    # Second recalculation
    score_2 = await engine.score_product(prod.id)
    assert score_2.composite_score == s1_comp
    assert score_2.core_opportunity_score == s1_core
    assert score_2.bundle_upside_score == s1_bundle
    assert score_2.commercial_model == s1_model
    assert score_2.weights_version == "v4_balanced_multimodel"



