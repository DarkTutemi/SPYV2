"""
US WIN HUNTER — Phase 10 Test Suite: Controlled Discovery Experiment Preflight & Attribution

Verification for:
1. Preflight safety check validates configuration, token, spend limits, and zero auto-collection.
2. 14 Experiment tasks are strictly defined with exact categories, strategies, and bounded limits (10 ads/task).
3. Advertiser-first seeds use genuine stored Facebook Page IDs (Swiftlifty & Gridsparkl).
4. Billing formula reconciles provider pricing ($0.005 start + $0.000575/ad) within the $0.50 budget cap.
5. Exact source attribution structure preserves query, strategy, category, and run ID.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.database import Base, engine, async_session_factory
from app.models.models import Advertiser, DataSourceType
from app.services.phase10_experiment import (
    EXPERIMENT_TASKS,
    Phase10ExperimentService,
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


def test_experiment_tasks_structure():
    """Verify all 14 tasks adhere to user prompt specification across the 6 core categories."""
    assert len(EXPERIMENT_TASKS) == 14

    pain_tasks = [t for t in EXPERIMENT_TASKS if t["strategy"] == "PAIN_FIRST"]
    bundle_tasks = [t for t in EXPERIMENT_TASKS if t["strategy"] == "BUNDLE_FIRST"]
    adv_tasks = [t for t in EXPERIMENT_TASKS if t["strategy"] == "ADVERTISER_FIRST"]

    assert len(pain_tasks) == 6
    assert len(bundle_tasks) == 6
    assert len(adv_tasks) == 2

    # Check queries match prompt exactly
    pain_queries = [t["query_or_seed"] for t in pain_tasks]
    assert pain_queries == [
        "pet hair stuck couch",
        "underwear leak protection",
        "car seat gap filler",
        "muddy dog paws",
        "cold air under door",
        "stripped screw removal",
    ]

    bundle_queries = [t["query_or_seed"] for t in bundle_tasks]
    assert bundle_queries == [
        "washable cleaning pads",
        "period underwear multipack",
        "microfiber car detailing towels",
        "reusable dog pee pads",
        "silicone chair leg protectors",
        "drill brush attachment set",
    ]

    adv_page_ids = [t["query_or_seed"] for t in adv_tasks]
    assert "1427580890438766" in adv_page_ids
    assert "1238627265989998" in adv_page_ids

    # Max ads per task must be strictly 10
    assert all(t["max_ads"] == 10 for t in EXPERIMENT_TASKS)


@pytest.mark.asyncio
async def test_preflight_checks_with_stored_advertisers(db):
    """Verify preflight check validates stored advertiser seeds and safety budget limits."""
    # Seed the two authentic advertisers into database
    adv1 = Advertiser(
        name="Swiftlifty",
        facebook_page_id="1427580890438766",
        domain="swiftlifty.com",
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    adv2 = Advertiser(
        name="Gridsparkl/er",
        facebook_page_id="1238627265989998",
        domain="gridsparkl.com",
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    db.add_all([adv1, adv2])
    await db.commit()

    service = Phase10ExperimentService(db)
    report = await service.run_preflight_checks()

    assert report.total_tasks_count == 14
    assert report.max_ads_per_task == 10
    assert report.max_total_ads == 140
    assert report.stored_advertiser_seeds_verified is True
    assert set(report.verified_page_ids) == {"1427580890438766", "1238627265989998"}
    assert report.estimated_cost_usd == pytest.approx(0.1505, rel=1e-3)
    assert report.max_authorized_budget_usd == 0.50
    assert report.safety_buffer_ratio >= 3.0
    assert report.auto_collection_disabled is True


def test_billing_formula_reconciliation():
    """Verify official Apify pay-per-event pricing formula."""
    # Run mgrbhLt82lm2ybAZn had 1 start event + 20 ad-scraped events
    start_fee = 0.0050
    per_ad_fee = 0.000575
    run_cost = start_fee + (20 * per_ad_fee)
    assert run_cost == pytest.approx(0.0165, rel=1e-4)

    # 14 task experiment: 14 start events + 140 ad-scraped events
    total_est = (14 * start_fee) + (140 * per_ad_fee)
    assert total_est == pytest.approx(0.1505, rel=1e-4)
    assert total_est < 0.50  # Strictly within $0.50 ceiling

