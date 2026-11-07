"""
US WIN HUNTER — Phase 3 Test Suite

Tests:
- Alert engine detectors (advertiser entry, creative spike, contraction, coverage gap)
- Alert dedup and persistence
- Scheduler run pipeline (end-to-end without real timers)
- Historical metrics endpoint logic
- Window comparison with coverage warnings
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import Base, engine, async_session_factory
from app.models.models import (
    Advertisement,
    Advertiser,
    Alert,
    AlertSeverity,
    AlertType,
    CollectionJobStatus,
    CollectionRun,
    DataSource,
    DataSourceType,
    OpportunityScore,
    Product,
    ProductDailyMetric,
)
from app.engines.alerts import AlertEngine
from app.engines.temporal import TemporalEngine
from app.services.scheduler import SchedulerService, get_scheduler


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db():
    async with async_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_alert_new_advertiser_entry(db):
    """Test detection of new independent advertisers promoting a product."""
    product = Product(
        name="Test Multi-Use Sponge",
        target_country="US",
        source_type=DataSourceType.MANUAL_IMPORT,
    )
    db.add(product)
    await db.flush()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

    # Prior week: 1 advertiser
    db.add(ProductDailyMetric(
        product_id=product.id,
        metric_date=week_ago,
        active_ad_count=2,
        unique_advertiser_count=1,
        new_advertiser_count=0,
    ))

    # Today: 3 advertisers (2 new)
    db.add(ProductDailyMetric(
        product_id=product.id,
        metric_date=today,
        active_ad_count=6,
        unique_advertiser_count=3,
        new_advertiser_count=2,
    ))
    await db.flush()

    engine = AlertEngine(db)
    alerts = await engine.run_all_detectors(today)

    entry_alerts = [a for a in alerts if a.alert_type == AlertType.NEW_ADVERTISER_ENTRY]
    assert len(entry_alerts) >= 1
    assert entry_alerts[0].entity_id == product.id
    assert entry_alerts[0].severity == AlertSeverity.WARNING


@pytest.mark.asyncio
async def test_alert_creative_spike(db):
    """Test detection of creative spikes."""
    product = Product(
        name="Test Kitchen Gadget",
        target_country="US",
        source_type=DataSourceType.MANUAL_IMPORT,
    )
    db.add(product)
    await db.flush()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Last 6 days: 1 new ad/day
    for i in range(1, 7):
        d = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
        db.add(ProductDailyMetric(
            product_id=product.id,
            metric_date=d,
            active_ad_count=3,
            new_ad_count=1,
            unique_advertiser_count=1,
        ))

    # Today: 5 new ads (5x average of 1.0)
    db.add(ProductDailyMetric(
        product_id=product.id,
        metric_date=today,
        active_ad_count=8,
        new_ad_count=5,
        unique_advertiser_count=1,
    ))
    await db.flush()

    engine = AlertEngine(db)
    alerts = await engine.run_all_detectors(today)

    spike_alerts = [a for a in alerts if a.alert_type == AlertType.CREATIVE_SPIKE]
    assert len(spike_alerts) >= 1
    assert spike_alerts[0].entity_id == product.id
    assert spike_alerts[0].data["new_ads_today"] == 5


@pytest.mark.asyncio
async def test_alert_sudden_contraction(db):
    """Test detection of sudden ad contraction with coverage warning."""
    product = Product(
        name="Test Yoga Mat",
        target_country="US",
        source_type=DataSourceType.MANUAL_IMPORT,
    )
    db.add(product)
    await db.flush()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

    # Prior week: 10 active ads
    db.add(ProductDailyMetric(
        product_id=product.id,
        metric_date=week_ago,
        active_ad_count=10,
        unique_advertiser_count=2,
    ))

    # Today: 2 active ads (80% drop)
    db.add(ProductDailyMetric(
        product_id=product.id,
        metric_date=today,
        active_ad_count=2,
        unique_advertiser_count=1,
        coverage_completeness=0.2,  # Low coverage!
    ))
    await db.flush()

    engine = AlertEngine(db)
    alerts = await engine.run_all_detectors(today)

    contraction_alerts = [a for a in alerts if a.alert_type == AlertType.SUDDEN_CONTRACTION]
    assert len(contraction_alerts) >= 1
    assert "Low data coverage" in contraction_alerts[0].description


@pytest.mark.asyncio
async def test_alert_coverage_gap(db):
    """Test detection of coverage gaps."""
    product = Product(
        name="Test Coverage Product",
        target_country="US",
        source_type=DataSourceType.MANUAL_IMPORT,
    )
    db.add(product)
    await db.flush()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    db.add(ProductDailyMetric(
        product_id=product.id,
        metric_date=today,
        active_ad_count=1,
        coverage_completeness=0.1,  # 10% coverage
    ))
    await db.flush()

    engine = AlertEngine(db)
    alerts = await engine.run_all_detectors(today)

    gap_alerts = [a for a in alerts if a.alert_type == AlertType.COVERAGE_GAP]
    assert len(gap_alerts) >= 1
    assert gap_alerts[0].entity_id == product.id


@pytest.mark.asyncio
async def test_alert_high_emergence_low_confidence(db):
    """Test alert when product has high emergence but low confidence."""
    product = Product(
        name="Test Risky Product",
        target_country="US",
        source_type=DataSourceType.MANUAL_IMPORT,
    )
    db.add(product)
    await db.flush()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    db.add(OpportunityScore(
        product_id=product.id,
        score_date=today,
        emergence_score=85.0,
        evidence_confidence=15.0,
        bundle_potential=40.0,
        composite_score=42.0,
        requires_verification=True,
        verification_reason="High emergence but low evidence confidence",
    ))
    await db.flush()

    engine = AlertEngine(db)
    alerts = await engine.run_all_detectors(today)

    flag_alerts = [a for a in alerts if a.alert_type == AlertType.HIGH_EMERGENCE_LOW_CONFIDENCE]
    assert len(flag_alerts) >= 1
    assert flag_alerts[0].entity_id == product.id


@pytest.mark.asyncio
async def test_alert_deduplication(db):
    """Test that running detectors twice on the same day does not create duplicate alerts."""
    product = Product(
        name="Test Dedup Product",
        target_country="US",
        source_type=DataSourceType.MANUAL_IMPORT,
    )
    db.add(product)
    await db.flush()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    db.add(ProductDailyMetric(
        product_id=product.id,
        metric_date=today,
        active_ad_count=1,
        coverage_completeness=0.1,
    ))
    await db.flush()

    engine = AlertEngine(db)
    first_run = await engine.run_all_detectors(today)
    second_run = await engine.run_all_detectors(today)

    assert len(first_run) >= 1
    assert len(second_run) == 0  # No duplicates created


@pytest.mark.asyncio
async def test_scheduler_pipeline_execution():
    """Test full pipeline run using SchedulerService."""
    scheduler = SchedulerService()
    result = await scheduler.run_pipeline_now("test_run")
    assert result["status"] in ("completed", "partial")
    assert result["run_type"] == "test_run"
    assert "snapshot" in result["steps"]
    assert "aggregate" in result["steps"]
    assert "scoring" in result["steps"]
    assert "graph" in result["steps"]
    assert "alerts" in result["steps"]


@pytest.mark.asyncio
async def test_alerts_api(client, db):
    """Test alert API list, mark read/dismissed, and summary."""
    # Seed an alert
    alert = Alert(
        alert_type=AlertType.NEW_ADVERTISER_ENTRY,
        severity=AlertSeverity.WARNING,
        title="Test Alert",
        description="Test alert description",
        entity_type="product",
        entity_id="prod-123",
        entity_name="Test Prod",
    )
    db.add(alert)
    await db.commit()

    # List alerts
    res = await client.get("/api/v1/alerts/")
    assert res.status_code == 200
    data = res.json()
    assert len(data["alerts"]) >= 1
    alert_id = data["alerts"][0]["id"]

    # Summary
    summary_res = await client.get("/api/v1/alerts/summary")
    assert summary_res.status_code == 200
    summary = summary_res.json()
    assert summary["unread_total"] >= 1

    # Mark as read
    mark_res = await client.post(
        "/api/v1/alerts/mark",
        json={"alert_ids": [alert_id], "action": "read"},
    )
    assert mark_res.status_code == 200
    assert mark_res.json()["marked"] == 1

    # Verify unread filtered list
    res_unread = await client.get("/api/v1/alerts/?unread_only=true")
    assert res_unread.status_code == 200
    assert all(a["id"] != alert_id for a in res_unread.json()["alerts"])


@pytest.mark.asyncio
async def test_historical_metrics_api(client, db):
    """Test product historical metrics and analytics overview endpoints."""
    product = Product(
        name="Test Analytics Product",
        target_country="US",
        source_type=DataSourceType.MANUAL_IMPORT,
    )
    db.add(product)
    await db.flush()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    db.add(ProductDailyMetric(
        product_id=product.id,
        metric_date=yesterday,
        active_ad_count=4,
        new_ad_count=2,
        unique_advertiser_count=1,
        coverage_completeness=0.8,
    ))
    db.add(ProductDailyMetric(
        product_id=product.id,
        metric_date=today,
        active_ad_count=6,
        new_ad_count=3,
        unique_advertiser_count=2,
        coverage_completeness=0.9,
    ))
    await db.commit()

    # Test product metrics
    res = await client.get(f"/api/v1/temporal/metrics/{product.id}?window=7")
    assert res.status_code == 200
    body = res.json()
    assert body["product_id"] == product.id
    assert len(body["metrics"]) == 2
    assert body["metrics"][-1]["active_ads"] == 6

    # Test analytics overview
    overview_res = await client.get("/api/v1/temporal/analytics/overview?window=7")
    assert overview_res.status_code == 200
    overview_body = overview_res.json()
    assert len(overview_body["daily_overview"]) >= 1
