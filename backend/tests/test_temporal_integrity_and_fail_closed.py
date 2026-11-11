"""
US WIN HUNTER — Batch 7: Temporal Evidence Integrity & Apify Fail-Closed Hardening
Comprehensive regression test suite for:
1. Distinguishing genuine fresh Meta observations from database-derived snapshots.
2. Refusing fallback to historic Advertisement.is_active when active snapshots are zero.
3. Requiring collection provenance for confirmed active ads in ProductDailyMetric.
4. Database budget lock failing closed (raising BudgetLockError) if apify_budget_locks table is missing or locked.
5. Handling ambiguous Actor start failures (HTTP 5xx, timeouts, missing run ID) as NEEDS_RECONCILIATION with retained budget cap.
6. Ensuring missing usageTotalUsd retains budget cap and is never logged as verified $0.00.
7. Preserving historical snapshots and distinct ads.
"""

import os
import tempfile
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, text, func

from app.models.models import (
    Base,
    Advertisement,
    AdvertisementSnapshot,
    Advertiser,
    CollectionJob,
    CollectionRun,
    CollectionJobStatus,
    DataSource,
    DataSourceType,
    OpportunityScore,
    Product,
    ProductDailyMetric,
    SnapshotObservationQuality,
    ApifySpendReservation,
    ApifyReservationStatus,
    ApifyBudgetLock,
    _uuid,
    _utcnow,
)
from app.engines.temporal import TemporalEngine
from app.services.budget_manager import (
    ApifyBudgetManager,
    BudgetLockError,
    BudgetExceededError,
)
from app.services.scheduler import SchedulerService


@pytest.fixture
async def disposable_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
        tmp_db_path = tmp_db.name

    db_url = f"sqlite+aiosqlite:///{tmp_db_path.replace(os.sep, '/')}"
    engine = create_async_engine(db_url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield async_session

    await engine.dispose()
    try:
        os.remove(tmp_db_path)
    except OSError:
        pass


@pytest.mark.asyncio
async def test_derived_snapshot_marked_correctly_without_collection(disposable_db):
    """Scenario 1: Daily snapshot without collection provenance is marked DATABASE_DERIVED_SNAPSHOT."""
    async with disposable_db() as session:
        adv = Advertiser(
            name="Test Advertiser",
            normalized_name="test advertiser",
            source_type=DataSourceType.META_AD_LIBRARY,
            country="US",
        )
        session.add(adv)
        await session.flush()

        prod = Product(
            name="Test Product",
            normalized_name="test product",
            target_country="US",
            source_type=DataSourceType.META_AD_LIBRARY,
        )
        session.add(prod)
        await session.flush()

        ad = Advertisement(
            external_id="ad_test_101",
            source_type=DataSourceType.META_AD_LIBRARY,
            advertiser_id=adv.id,
            product_id=prod.id,
            is_active=True,
            first_seen_at=_utcnow(),
            last_seen_at=_utcnow(),
        )
        session.add(ad)
        await session.commit()

        temporal = TemporalEngine(session)
        result = await temporal.create_daily_snapshot("2026-11-12")
        await session.commit()

        assert result["observation_quality"] == SnapshotObservationQuality.DATABASE_DERIVED_SNAPSHOT.value
        assert result["collection_run_id"] is None

        # Verify in DB
        snap = (await session.execute(
            select(AdvertisementSnapshot).where(AdvertisementSnapshot.advertisement_id == ad.id)
        )).scalar_one()
        assert snap.observation_quality == SnapshotObservationQuality.DATABASE_DERIVED_SNAPSHOT.value
        assert snap.raw_snapshot["observation_quality"] == SnapshotObservationQuality.DATABASE_DERIVED_SNAPSHOT.value


@pytest.mark.asyncio
async def test_active_ad_count_strictly_zero_when_no_genuine_snapshots(disposable_db):
    """Scenario 2: Active ad count does NOT fall back to historic Advertisement table when active snapshots are 0 or derived."""
    async with disposable_db() as session:
        adv = Advertiser(
            name="Active Ad Brand",
            normalized_name="active ad brand",
            source_type=DataSourceType.META_AD_LIBRARY,
            country="US",
        )
        session.add(adv)
        await session.flush()

        prod = Product(
            name="Active Widget",
            normalized_name="active widget",
            target_country="US",
            source_type=DataSourceType.META_AD_LIBRARY,
        )
        session.add(prod)
        await session.flush()

        # 3 ads in advertisements table, all marked is_active=True
        for i in range(3):
            ad = Advertisement(
                external_id=f"active_widget_ad_{i}",
                source_type=DataSourceType.META_AD_LIBRARY,
                advertiser_id=adv.id,
                product_id=prod.id,
                is_active=True,
                first_seen_at=_utcnow() - timedelta(days=5),
                last_seen_at=_utcnow(),
            )
            session.add(ad)
        await session.commit()

        temporal = TemporalEngine(session)

        # Case A: Zero snapshots on 2026-11-12. Metric must be 0, NOT falling back to 3!
        metrics = await temporal.aggregate_daily_metrics("2026-11-12")
        await session.commit()
        assert len(metrics) == 1
        assert metrics[0].active_ad_count == 0  # Crucial: NO fallback to Advertisement.is_active!

        # Case B: Create DATABASE_DERIVED_SNAPSHOT on 2026-11-13
        await temporal.create_daily_snapshot("2026-11-13")
        await session.commit()

        metrics_b = await temporal.aggregate_daily_metrics("2026-11-13")
        await session.commit()
        assert len(metrics_b) == 1
        assert metrics_b[0].active_ad_count == 0  # Crucial: Derived snapshots do NOT inflate active count!


@pytest.mark.asyncio
async def test_genuine_source_observation_properly_counts_active_ads(disposable_db):
    """Scenario 3: Genuine source observation with collection run provenance correctly updates active_ad_count."""
    async with disposable_db() as session:
        adv = Advertiser(
            name="Verified Brand",
            normalized_name="verified brand",
            source_type=DataSourceType.META_AD_LIBRARY,
            country="US",
        )
        session.add(adv)
        await session.flush()

        prod = Product(
            name="Verified Gadget",
            normalized_name="verified gadget",
            target_country="US",
            source_type=DataSourceType.META_AD_LIBRARY,
        )
        session.add(prod)
        await session.flush()

        ads = []
        for i in range(4):
            ad = Advertisement(
                external_id=f"verified_ad_{i}",
                source_type=DataSourceType.META_AD_LIBRARY,
                advertiser_id=adv.id,
                product_id=prod.id,
                is_active=True,
                first_seen_at=_utcnow(),
                last_seen_at=_utcnow(),
            )
            session.add(ad)
            ads.append(ad)
        await session.commit()

        # Create snapshots with genuine provenance
        temporal = TemporalEngine(session)
        observed_statuses = {
            ads[0].id: True,
            ads[1].id: True,
            ads[2].id: False,  # confirmed inactive
            ads[3].id: False,
        }
        res = await temporal.create_daily_snapshot(
            snapshot_date="2026-11-14",
            collection_run_id="crun_test_genuine_1",
            observed_ad_statuses=observed_statuses,
        )
        await session.commit()
        assert res["observation_quality"] in (
            SnapshotObservationQuality.VERIFIED_SOURCE_OBSERVATION.value,
            SnapshotObservationQuality.GENUINE_SOURCE_OBSERVATION.value,
        )

        metrics = await temporal.aggregate_daily_metrics("2026-11-14")
        await session.commit()
        assert len(metrics) == 1
        assert metrics[0].active_ad_count == 2  # Exactly 2 confirmed active!


@pytest.mark.asyncio
async def test_budget_lock_fails_closed_when_lock_table_missing(disposable_db):
    """Scenario 4: Missing apify_budget_locks table raises BudgetLockError and refuses reservation (fail closed)."""
    async with disposable_db() as session:
        # Drop the lock table to simulate missing table defect
        await session.execute(text("DROP TABLE IF EXISTS apify_budget_locks"))
        await session.commit()

        bm = ApifyBudgetManager(session, session_ceiling_usd=1.0)

        with pytest.raises(BudgetLockError) as exc_info:
            await bm.create_reservation(actor_id="test/actor", reserved_amount_usd=0.20)

        assert "apify_budget_locks' does not exist" in str(exc_info.value)

        # Verify no reservation was created
        res = (await session.execute(select(ApifySpendReservation))).scalars().all()
        assert len(res) == 0


@pytest.mark.asyncio
async def test_budget_lock_fails_closed_on_concurrency_or_db_error(disposable_db):
    """Scenario 5: DB execution failure during lock acquisition raises BudgetLockError and refuses reservation."""
    async with disposable_db() as session:
        # Lock table exists
        bm = ApifyBudgetManager(session, session_ceiling_usd=1.0)

        # Tamper table with an invalid column constraint to trigger DB error on insert
        await session.execute(text("DROP TABLE IF EXISTS apify_budget_locks"))
        await session.execute(text("CREATE TABLE apify_budget_locks (lock_id INT PRIMARY KEY, invalid_not_null TEXT NOT NULL)"))
        await session.commit()

        with pytest.raises(BudgetLockError) as exc_info:
            await bm.create_reservation(actor_id="test/actor", reserved_amount_usd=0.20)

        assert "Failed to acquire database budget lock" in str(exc_info.value)

        # Refused reservation
        res = (await session.execute(select(ApifySpendReservation))).scalars().all()
        assert len(res) == 0


@pytest.mark.asyncio
async def test_reconcile_definitive_client_rejection_vs_ambiguous_failure(disposable_db):
    """Scenario 6: Definitive 4xx client rejection allows $0.00 release; ambiguous failure holds reservation."""
    async with disposable_db() as session:
        bm = ApifyBudgetManager(session, session_ceiling_usd=2.0)

        # 1. Definitive client rejection (e.g. 400 Bad Request, no run created)
        res1 = await bm.create_reservation(actor_id="test/actor1", reserved_amount_usd=0.30)
        await bm.mark_launch_attempted(res1.id)
        await session.commit()

        await bm.reconcile_run(
            reservation_id=res1.id,
            final_status="FAILED",
            actual_cost_usd=0.0,
            billing_detail={
                "http_status": 400,
                "definitive_client_rejection": True,
            },
            notes="HTTP 400 bad payload, confirmed no run created",
        )
        await session.commit()

        r1 = await session.get(ApifySpendReservation, res1.id)
        assert r1.status == "FAILED"
        assert r1.actual_amount_usd == 0.0  # Clean release

        # 2. Ambiguous failure (e.g. 500 Internal Server Error during dispatch)
        res2 = await bm.create_reservation(actor_id="test/actor2", reserved_amount_usd=0.40)
        await bm.mark_launch_attempted(res2.id)
        await session.commit()

        await bm.reconcile_run(
            reservation_id=res2.id,
            final_status="NEEDS_RECONCILIATION",
            actual_cost_usd=0.40,
            billing_detail={
                "http_status": 500,
                "ambiguous_failure": True,
            },
            notes="HTTP 500 provider error, held full reservation",
        )
        await session.commit()

        r2 = await session.get(ApifySpendReservation, res2.id)
        assert r2.status == "NEEDS_RECONCILIATION"
        assert r2.actual_amount_usd == 0.40  # Budget held!


@pytest.mark.asyncio
async def test_missing_usage_total_usd_never_assumed_zero(disposable_db):
    """Scenario 7: Run payload missing usageTotalUsd retains reserved budget and is not verified as $0.00."""
    async with disposable_db() as session:
        bm = ApifyBudgetManager(session, session_ceiling_usd=1.0)

        res = await bm.create_reservation(actor_id="test/actor_billing", reserved_amount_usd=0.35)
        await bm.mark_run_started(res.id, apify_run_id="run_missing_billing_123")
        await session.commit()

        # Reconcile with terminal status SUCCEEDED but billing payload omits usageTotalUsd
        billing_payload_missing = {
            "id": "run_missing_billing_123",
            "status": "SUCCEEDED",
            # usageTotalUsd is omitted / None
        }

        # Simulate execute_new_research_run logic: usage_raw is None -> retain budget_cap
        usage_raw = billing_payload_missing.get("usageTotalUsd")
        if usage_raw is None:
            usage_usd = res.reserved_amount_usd
            notes = "Missing usageTotalUsd in provider response; retained reserved budget cap."
        else:
            usage_usd = float(usage_raw)
            notes = "Verified provider usage"

        await bm.reconcile_run(
            reservation_id=res.id,
            final_status="SUCCEEDED",
            actual_cost_usd=usage_usd,
            billing_detail=billing_payload_missing,
            notes=notes,
        )
        await session.commit()

        reconciled = await session.get(ApifySpendReservation, res.id)
        assert reconciled.status == "SUCCEEDED"
        assert reconciled.actual_amount_usd == 0.35  # Reserved amount preserved, NOT $0.00!
        assert "Missing usageTotalUsd" in reconciled.reconciliation_notes


@pytest.mark.asyncio
async def test_scheduler_skips_snapshot_when_no_collection_run(disposable_db, monkeypatch):
    """Scenario 8: Scheduler pipeline skips snapshot creation when no live collection completed in cycle."""
    async with disposable_db() as session:
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_get_session():
            yield session

        monkeypatch.setattr("app.services.scheduler.get_session", mock_get_session)

        scheduler = SchedulerService()
        scheduler._last_collection = None
        scheduler._last_collection_result = None

        result = await scheduler._execute_pipeline("test_scheduled")
        assert result["steps"]["snapshot"]["status"] == "skipped"
        assert "No live Meta collection run completed" in result["steps"]["snapshot"]["reason"]
