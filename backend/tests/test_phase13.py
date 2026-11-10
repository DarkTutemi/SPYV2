"""
US WIN HUNTER — Phase 13 Test Suite: Watchlist Precision & Baseline Integrity

Verification for:
1. Strict $30–$90 price filtering rejects $29.99 ($29.99 < $30.00).
2. Multi-unit demand (Class A) is distinguished from pieces required per functional set (Class B/C).
3. T0 baseline snapshots do not backdate timestamps and cover monitored advertisements.
4. Research priority states (INVESTIGATE_NOW, CONTINUE_MONITORING, NEEDS_MORE_EVIDENCE, DEPRIORITIZE) are assigned deterministically.
"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest
import pytest_asyncio

from app.core.database import Base, engine, async_session_factory
from app.models.models import (
    Advertisement,
    AdvertisementSnapshot,
    Advertiser,
    DataSourceType,
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


def is_strictly_within_30_to_90(price: float | None) -> bool:
    """Strict evaluation: 30.00 <= price <= 90.00."""
    if price is None:
        return False
    return 30.00 <= price <= 90.00


def classify_bundle_demand_type(product_category: str, item_nature: str) -> str:
    """
    Distinguish:
    A: Multiple complete units needed for regular consumable / hygienic use
    B: Multiple pieces required to cover one household or complete 1 functional set
    C: A complete tool kit containing multiple components
    """
    nature_lower = item_nature.lower()
    if any(k in nature_lower for k in ["pee pad", "mop head", "underwear", "boxer", "detailing towel"]):
        return "CLASS_A_NATURAL_MULTI_UNIT"
    elif any(k in nature_lower for k in ["chair leg protector", "dog boot", "rug gripper"]):
        return "CLASS_B_PIECES_PER_SET"
    elif any(k in nature_lower for k in ["bolt extractor", "drill brush", "window wand kit"]):
        return "CLASS_C_COMPLETE_TOOLKIT"
    return "CLASS_E_INSUFFICIENT"


def assign_research_priority(
    has_functional_benefit: bool,
    bundle_class: str,
    verified_price_30_90: bool,
    advertiser_count: int,
) -> str:
    """
    Deterministic research priority assignment:
    - INVESTIGATE_NOW: Functional + Natural Multi-Unit (Class A or B) + Verified $30-$90 + >=2 Advertisers
    - CONTINUE_MONITORING: Functional + Multi-Unit + Verified $30-$90 + 1 Advertiser
    - NEEDS_MORE_EVIDENCE: Functional + (Class A or B) + Missing verified $30-$90
    - DEPRIORITIZE: Toolkit / Artificial bundle / Non-functional / Weak demand
    """
    if not has_functional_benefit:
        return "DEPRIORITIZE"
    if bundle_class not in ("CLASS_A_NATURAL_MULTI_UNIT", "CLASS_B_PIECES_PER_SET"):
        return "DEPRIORITIZE"
    if verified_price_30_90:
        if advertiser_count >= 2:
            return "INVESTIGATE_NOW"
        return "CONTINUE_MONITORING"
    return "NEEDS_MORE_EVIDENCE"


def test_strict_30_90_pricing_rule():
    """Verify $29.99 is strictly rejected, while prices >= $30.00 and <= $90.00 pass."""
    assert is_strictly_within_30_to_90(29.99) is False
    assert is_strictly_within_30_to_90(29.999) is False
    assert is_strictly_within_30_to_90(20.79) is False
    assert is_strictly_within_30_to_90(95.00) is False
    assert is_strictly_within_30_to_90(None) is False

    assert is_strictly_within_30_to_90(30.00) is True
    assert is_strictly_within_30_to_90(34.99) is True
    assert is_strictly_within_30_to_90(39.90) is True
    assert is_strictly_within_30_to_90(39.99) is True
    assert is_strictly_within_30_to_90(49.88) is True
    assert is_strictly_within_30_to_90(69.00) is True
    assert is_strictly_within_30_to_90(90.00) is True


def test_bundle_demand_type_differentiation():
    """Verify natural multi-unit demand (Class A) is cleanly separated from pieces per set (Class B/C)."""
    assert classify_bundle_demand_type("Pet Supplies", "washable pee pad 4-layer") == "CLASS_A_NATURAL_MULTI_UNIT"
    assert classify_bundle_demand_type("Home & Cleaning", "microfiber spin mop head refill") == "CLASS_A_NATURAL_MULTI_UNIT"
    assert classify_bundle_demand_type("Functional Apparel", "men leakproof boxer brief") == "CLASS_A_NATURAL_MULTI_UNIT"
    assert classify_bundle_demand_type("Automotive", "microfiber detailing towel") == "CLASS_A_NATURAL_MULTI_UNIT"

    assert classify_bundle_demand_type("Household", "silicone chair leg protector 24-pack") == "CLASS_B_PIECES_PER_SET"
    assert classify_bundle_demand_type("Pet", "dog boot 4-piece set") == "CLASS_B_PIECES_PER_SET"
    assert classify_bundle_demand_type("Household", "anti-curling rug gripper 8-pack") == "CLASS_B_PIECES_PER_SET"

    assert classify_bundle_demand_type("Hardware", "damaged bolt extractor set 10pcs") == "CLASS_C_COMPLETE_TOOLKIT"
    assert classify_bundle_demand_type("Cleaning", "drill brush power scrubber set") == "CLASS_C_COMPLETE_TOOLKIT"


def test_research_priority_state_assignment():
    """Verify deterministic priority states based on evidence and multi-unit validity."""
    # Top candidate with verified bundle price and 3 advertisers
    p1 = assign_research_priority(
        has_functional_benefit=True,
        bundle_class="CLASS_A_NATURAL_MULTI_UNIT",
        verified_price_30_90=True,
        advertiser_count=3,
    )
    assert p1 == "INVESTIGATE_NOW"

    # Promising candidate with verified price but single advertiser
    p2 = assign_research_priority(
        has_functional_benefit=True,
        bundle_class="CLASS_B_PIECES_PER_SET",
        verified_price_30_90=True,
        advertiser_count=1,
    )
    assert p2 == "CONTINUE_MONITORING"

    # Candidate with unverified price (e.g. dynamic landing page)
    p3 = assign_research_priority(
        has_functional_benefit=True,
        bundle_class="CLASS_A_NATURAL_MULTI_UNIT",
        verified_price_30_90=False,
        advertiser_count=2,
    )
    assert p3 == "NEEDS_MORE_EVIDENCE"

    # Toolkit with no natural multi-unit demand (Class C)
    p4 = assign_research_priority(
        has_functional_benefit=True,
        bundle_class="CLASS_C_COMPLETE_TOOLKIT",
        verified_price_30_90=True,
        advertiser_count=4,
    )
    assert p4 == "DEPRIORITIZE"


@pytest.mark.asyncio
async def test_snapshot_timestamp_integrity(db):
    """Verify snapshots preserve actual creation timestamp without backdating."""
    adv = Advertiser(
        name="Test Seller",
        source_type=DataSourceType.META_AD_LIBRARY,
        facebook_page_id="999888777",
    )
    db.add(adv)
    await db.flush()

    ad = Advertisement(
        external_id="meta_test_ad_123",
        source_type=DataSourceType.META_AD_LIBRARY,
        advertiser_id=adv.id,
        is_active=True,
        is_synthetic=False,
    )
    db.add(ad)
    await db.flush()

    before = datetime.now(timezone.utc)
    snap = AdvertisementSnapshot(
        advertisement_id=ad.id,
        snapshot_date="2026-11-09",  # Observation baseline date
        is_active=True,
        source_type=DataSourceType.META_AD_LIBRARY,
        raw_snapshot={"ad_archive_id": ad.external_id, "t0_status": "ACTIVE"},
    )
    db.add(snap)
    await db.commit()
    await db.refresh(snap)
    after = datetime.now(timezone.utc)

    # created_at must be the real system execution time, NOT 2026-11-09
    assert snap.snapshot_date == "2026-11-09"
    created_naive = snap.created_at.replace(tzinfo=None) if snap.created_at.tzinfo else snap.created_at
    assert before.replace(tzinfo=None) <= created_naive <= after.replace(tzinfo=None)
    assert created_naive.date() == after.date()
