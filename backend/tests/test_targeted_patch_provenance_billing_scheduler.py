"""
US WIN HUNTER — Targeted Patch Regression Test Suite:
Proven Ad Status Extraction, Apify Billing Without Double-Counting, and Scheduler Collection Status Consistency.
"""

import os
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.adapters.apify import ApifyProviderAdapter, ProviderStatus
from app.engines.temporal import TemporalEngine, extract_ad_status
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
    Product,
    ProductDailyMetric,
    SnapshotObservationQuality,
    SourceRecord,
    ApifySpendReservation,
    ApifyReservationStatus,
    ApifyBudgetLock,
    _uuid,
    _utcnow,
)
from app.services.scheduler import SchedulerService


@pytest.fixture
async def patch_test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_url = f"sqlite+aiosqlite:///{path}"
    engine = create_async_engine(db_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as session:
        yield session

    await engine.dispose()
    try:
        os.remove(path)
    except OSError:
        pass


# ── FIX 1 TESTS: EXTRACT ACTUAL AD STATUS FROM SOURCE ───────────────────────────

def test_extract_ad_status_normalization_contract():
    """Verify status extraction across all supported Actor output fields and normalization contracts."""
    # 1. isActive boolean and string
    assert extract_ad_status({"isActive": True}) == (True, "ACTIVE")
    assert extract_ad_status({"isActive": False}) == (False, "INACTIVE")
    assert extract_ad_status({"isActive": "active"}) == (True, "ACTIVE")
    assert extract_ad_status({"isActive": "inactive"}) == (False, "INACTIVE")
    assert extract_ad_status({"isActive": "stopped"}) == (False, "INACTIVE")

    # 2. is_active boolean and string
    assert extract_ad_status({"is_active": True}) == (True, "ACTIVE")
    assert extract_ad_status({"is_active": False}) == (False, "INACTIVE")

    # 3. activeStatus
    assert extract_ad_status({"activeStatus": "active"}) == (True, "ACTIVE")
    assert extract_ad_status({"activeStatus": "inactive"}) == (False, "INACTIVE")
    # "all" is a query filter, not an active indicator!
    assert extract_ad_status({"activeStatus": "all"}) == (None, "UNKNOWN")

    # 4. status
    assert extract_ad_status({"status": "ACTIVE"}) == (True, "ACTIVE")
    assert extract_ad_status({"status": "RUNNING"}) == (True, "ACTIVE")
    assert extract_ad_status({"status": "INACTIVE"}) == (False, "INACTIVE")
    assert extract_ad_status({"status": "PAUSED"}) == (False, "INACTIVE")
    assert extract_ad_status({"status": "ARCHIVED"}) == (False, "INACTIVE")

    # 5. Missing / ambiguous
    assert extract_ad_status({}) == (None, "UNKNOWN")
    assert extract_ad_status(None) == (None, "UNKNOWN")
    assert extract_ad_status({"other_field": 123}) == (None, "UNKNOWN")


@pytest.mark.asyncio
async def test_active_status_all_regression_active_inactive_unknown(patch_test_db: AsyncSession):
    """
    Mandated Regression Test:
    Use activeStatus="all" with an active ad, an inactive ad, and an unknown-status ad.
    - Active ad -> confirmed snapshot (is_active=True, VERIFIED_SOURCE_OBSERVATION)
    - Inactive ad -> confirmed snapshot (is_active=False, VERIFIED_SOURCE_OBSERVATION)
    - Unknown-status ad -> NO confirmed active/inactive snapshot created!
    """
    db = patch_test_db
    today = "2026-11-11"

    # Setup DataSource, Job, Advertiser
    source = DataSource(name="Apify", source_type=DataSourceType.APIFY, is_active=True)
    db.add(source)
    await db.flush()
    job = CollectionJob(data_source_id=source.id, name="test_job", job_type="apify_live")
    db.add(job)
    adv = Advertiser(id="adv_test", name="TestBrand", normalized_name="testbrand", source_type=DataSourceType.META_AD_LIBRARY, country="US")
    db.add(adv)
    await db.flush()

    # Setup CollectionRun
    c_run = CollectionRun(
        id="run_active_status_all_test",
        job_id=job.id,
        status=CollectionJobStatus.COMPLETED,
        completed_at=datetime(2026, 11, 11, 10, 0, 0, tzinfo=timezone.utc),
    )
    db.add(c_run)

    # Setup 3 Ads
    ad_active = Advertisement(
        id="ad_001",
        external_id="ext_active_101",
        source_type=DataSourceType.META_AD_LIBRARY,
        advertiser_id=adv.id,
        is_active=True,
    )
    ad_inactive = Advertisement(
        id="ad_002",
        external_id="ext_inactive_102",
        source_type=DataSourceType.META_AD_LIBRARY,
        advertiser_id=adv.id,
        is_active=False,
    )
    ad_unknown = Advertisement(
        id="ad_003",
        external_id="ext_unknown_103",
        source_type=DataSourceType.META_AD_LIBRARY,
        advertiser_id=adv.id,
        is_active=True,  # Old DB state must not be trusted
    )
    db.add_all([ad_active, ad_inactive, ad_unknown])

    # Setup SourceRecords from a run with activeStatus="all"
    # 1. Active ad: explicitly isActive=True
    sr_active = SourceRecord(
        id="sr_001",
        collection_run_id=c_run.id,
        source_type=DataSourceType.META_AD_LIBRARY,
        external_id="ext_active_101",
        raw_data={"id": "ext_active_101", "activeStatus": "all", "isActive": True, "snapshotDate": "2026-11-11T09:00:00Z"},
        created_at=datetime(2026, 11, 11, 9, 0, 0, tzinfo=timezone.utc),
    )
    # 2. Inactive ad: explicitly isActive=False
    sr_inactive = SourceRecord(
        id="sr_002",
        collection_run_id=c_run.id,
        source_type=DataSourceType.META_AD_LIBRARY,
        external_id="ext_inactive_102",
        raw_data={"id": "ext_inactive_102", "activeStatus": "all", "isActive": False, "snapshotDate": "2026-11-11T09:15:00Z"},
        created_at=datetime(2026, 11, 11, 9, 15, 0, tzinfo=timezone.utc),
    )
    # 3. Unknown status ad: returned under activeStatus="all" but missing explicit status confirmation
    sr_unknown = SourceRecord(
        id="sr_003",
        collection_run_id=c_run.id,
        source_type=DataSourceType.META_AD_LIBRARY,
        external_id="ext_unknown_103",
        raw_data={"id": "ext_unknown_103", "activeStatus": "all"},
        created_at=datetime(2026, 11, 11, 9, 30, 0, tzinfo=timezone.utc),
    )
    db.add_all([sr_active, sr_inactive, sr_unknown])
    await db.commit()

    # Execute snapshot creation scoped to collection run
    temporal = TemporalEngine(db)
    res = await temporal.create_daily_snapshot(
        snapshot_date=today,
        collection_run_id=c_run.id,
    )

    # Exactly 2 snapshots created (active and inactive), 0 for unknown
    assert res["created"] == 2

    # Query snapshots
    snaps = (await db.execute(select(AdvertisementSnapshot))).scalars().all()
    assert len(snaps) == 2

    snap_map = {s.advertisement_id: s for s in snaps}

    # Active ad verified
    snap_a = snap_map["ad_001"]
    assert snap_a.is_active is True
    assert snap_a.observation_quality == SnapshotObservationQuality.VERIFIED_SOURCE_OBSERVATION.value
    assert snap_a.raw_snapshot["status"] == "ACTIVE"
    assert snap_a.raw_snapshot["observed_at"] == "2026-11-11T09:00:00Z"

    # Inactive ad verified
    snap_i = snap_map["ad_002"]
    assert snap_i.is_active is False
    assert snap_i.observation_quality == SnapshotObservationQuality.VERIFIED_SOURCE_OBSERVATION.value
    assert snap_i.raw_snapshot["status"] == "INACTIVE"
    assert snap_i.raw_snapshot["observed_at"] == "2026-11-11T09:15:00Z"

    # Unknown ad: No snapshot created (not confirmed active or inactive)
    assert "ad_003" not in snap_map


@pytest.mark.asyncio
async def test_no_manufactured_observation_timestamp(patch_test_db: AsyncSession):
    """Verify that observation timestamps are authentic and not manufactured."""
    db = patch_test_db
    today = "2026-11-11"

    source = DataSource(name="Apify", source_type=DataSourceType.APIFY, is_active=True)
    db.add(source)
    await db.flush()
    job = CollectionJob(data_source_id=source.id, name="ts_job", job_type="apify_live")
    db.add(job)
    await db.flush()

    c_run = CollectionRun(
        id="run_ts_test",
        job_id=job.id,
        status=CollectionJobStatus.COMPLETED,
        completed_at=datetime(2026, 11, 11, 12, 0, 0, tzinfo=timezone.utc),
    )
    db.add(c_run)

    adv = Advertiser(id="adv_ts", name="TSBrand", normalized_name="tsbrand", source_type=DataSourceType.META_AD_LIBRARY, country="US")
    db.add(adv)
    await db.flush()

    ad = Advertisement(id="ad_ts", external_id="ext_ts", source_type=DataSourceType.META_AD_LIBRARY, advertiser_id=adv.id)
    db.add(ad)

    # Source record with no timestamp fields at all
    sr = SourceRecord(
        id="sr_ts",
        collection_run_id=c_run.id,
        source_type=DataSourceType.META_AD_LIBRARY,
        external_id="ext_ts",
        raw_data={"id": "ext_ts", "isActive": True},
        created_at=None,
    )
    db.add(sr)
    await db.commit()

    temporal = TemporalEngine(db)
    await temporal.create_daily_snapshot(snapshot_date=today, collection_run_id=c_run.id)

    snap = (await db.execute(select(AdvertisementSnapshot).where(AdvertisementSnapshot.advertisement_id == ad.id))).scalar_one()
    # Does NOT manufacture an observation timestamp
    assert "observed_at" not in snap.raw_snapshot


# ── FIX 2 TESTS: APIFY BILLING WITHOUT DOUBLE-COUNTING ─────────────────────────

def test_apify_billing_no_double_counting_pay_per_event():
    """
    Mandated Test: Realistic Pay-Per-Event payloads where usageTotalUsd and eventUsage
    both contain the same underlying charge.
    Apify documents usageTotalUsd as the total run cost.
    Must NOT add event costs already included in usageTotalUsd!
    """
    run_data_ppe_same_charge = {
        "status": "SUCCEEDED",
        "usageTotalUsd": 0.0240,
        "eventUsageTotalUsd": 0.0240,
        "chargedEventCounts": {"ads": 20},
        "pricingInfo": {
            "pricingModel": "PAY_PER_EVENT",
            "unitName": "ad",
            "pricePerUnitUsd": 0.0012,
        },
    }
    billing = ApifyProviderAdapter.extract_billing_details(run_data_ppe_same_charge, records_fetched=20)
    assert billing["cost_status"] == "VERIFIED_CHARGED"
    assert billing["is_verified"] is True
    # CRITICAL: Must be 0.0240, NOT 0.0480 (no double counting!)
    assert billing["actual_cost_usd"] == 0.0240
    assert billing["usage_total_usd"] == 0.0240
    assert billing["event_usage_usd"] == 0.0240


def test_apify_billing_compute_plus_event_authoritative():
    """
    Verify authoritative usageTotalUsd when compute usage and event usage are combined.
    usageTotalUsd is 0.0342 (0.0102 compute + 0.0240 event).
    Result must be 0.0342, NOT 0.0582.
    """
    run_data_combined = {
        "status": "SUCCEEDED",
        "usageTotalUsd": 0.0342,
        "usageUsd": 0.0102,
        "eventUsageTotalUsd": 0.0240,
        "chargedEventCounts": {"ads": 20},
        "pricingInfo": {
            "pricingModel": "PAY_PER_EVENT",
        },
    }
    billing = ApifyProviderAdapter.extract_billing_details(run_data_combined, records_fetched=20)
    assert billing["cost_status"] == "VERIFIED_CHARGED"
    assert billing["actual_cost_usd"] == 0.0342
    assert billing["is_verified"] is True


def test_apify_billing_estimated_not_verified():
    """Estimated billing must not be treated as verified billing."""
    run_data_zero = {
        "status": "SUCCEEDED",
        "usageTotalUsd": 0.0,
        "eventUsageTotalUsd": 0.0,
    }
    billing = ApifyProviderAdapter.extract_billing_details(run_data_zero, records_fetched=10)
    assert billing["cost_status"] == "ESTIMATED"
    assert billing["actual_cost_usd"] == 0.012
    assert billing["is_verified"] is False  # NOT verified!


def test_apify_billing_missing_holds_reservation_cap():
    """Missing billing preserves reservation cap and is not verified."""
    run_data_missing = {
        "status": "SUCCEEDED",
        "usageTotalUsd": None,
        "eventUsageTotalUsd": None,
        "chargedTotalUsd": None,
    }
    billing = ApifyProviderAdapter.extract_billing_details(run_data_missing, records_fetched=10, reservation_cap=0.50)
    assert billing["cost_status"] == "HELD_RESERVATION_CAP"
    assert billing["actual_cost_usd"] == 0.50
    assert billing["is_verified"] is False


def test_apify_billing_explicit_zero_free_tier():
    """Explicit free tier produces 0.0 verified cost."""
    run_data_free = {
        "status": "SUCCEEDED",
        "pricingInfo": {"pricingModel": "FREE"},
    }
    billing = ApifyProviderAdapter.extract_billing_details(run_data_free, records_fetched=10)
    assert billing["cost_status"] == "VERIFIED_FREE_TIER"
    assert billing["actual_cost_usd"] == 0.0
    assert billing["is_verified"] is True


# ── FIX 3 TESTS: SCHEDULER COLLECTION STATUS CONSISTENCY ───────────────────────

@pytest.mark.asyncio
async def test_scheduler_status_completed_creates_snapshots(patch_test_db: AsyncSession):
    """
    Verify scheduler handles collection cycle returning status='completed' (or 'partial')
    rather than checking status == 'success', creating genuine snapshots for completed collection runs.
    """
    db = patch_test_db
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Setup CollectionRun and Ad
    source = DataSource(name="Apify", source_type=DataSourceType.APIFY, is_active=True)
    db.add(source)
    await db.flush()
    job = CollectionJob(data_source_id=source.id, name="sched_job", job_type="apify_live")
    db.add(job)
    await db.flush()

    c_run = CollectionRun(
        id="run_sched_test_01",
        job_id=job.id,
        status=CollectionJobStatus.COMPLETED,
        completed_at=datetime.now(timezone.utc),
    )
    db.add(c_run)

    adv = Advertiser(id="adv_sched_01", name="SchedBrand", normalized_name="schedbrand", source_type=DataSourceType.META_AD_LIBRARY, country="US")
    db.add(adv)
    await db.flush()

    ad = Advertisement(id="ad_sched_01", external_id="ext_sched_01", source_type=DataSourceType.META_AD_LIBRARY, advertiser_id=adv.id)
    db.add(ad)

    sr = SourceRecord(
        id="sr_sched_01",
        collection_run_id=c_run.id,
        source_type=DataSourceType.META_AD_LIBRARY,
        external_id="ext_sched_01",
        raw_data={"id": "ext_sched_01", "isActive": True},
        created_at=datetime.now(timezone.utc),
    )
    db.add(sr)
    await db.commit()

    service = SchedulerService()

    # Simulate completed collection cycle
    service._last_collection = datetime.now(timezone.utc)
    service._last_collection_result = {
        "status": "completed",
        "records_collected": 1,
        "collection_run_ids": [c_run.id],
        "collection_run_id": c_run.id,
        "errors": [],
    }

    # Patch get_session to use our test db
    with patch("app.services.scheduler.get_session") as mock_get_session:
        class SessionContext:
            async def __aenter__(self):
                return db
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        mock_get_session.return_value = SessionContext()

        pipeline_result = await service._execute_pipeline("test_run")
        assert pipeline_result["status"] == "completed"
        # Snapshot step must NOT be skipped!
        snap_step = pipeline_result["steps"]["snapshot"]
        assert snap_step.get("created") == 1
        assert snap_step.get("observation_quality") == SnapshotObservationQuality.VERIFIED_SOURCE_OBSERVATION.value


@pytest.mark.asyncio
async def test_scheduler_zero_records_skips_snapshot(patch_test_db: AsyncSession):
    """When collection collected 0 valid records, snapshot step must be skipped."""
    db = patch_test_db
    service = SchedulerService()

    service._last_collection = datetime.now(timezone.utc)
    service._last_collection_result = {
        "status": "completed",
        "records_collected": 0,
        "collection_run_ids": [],
        "errors": [],
    }

    with patch("app.services.scheduler.get_session") as mock_get_session:
        class SessionContext:
            async def __aenter__(self):
                return db
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        mock_get_session.return_value = SessionContext()

        pipeline_result = await service._execute_pipeline("test_run")
        snap_step = pipeline_result["steps"]["snapshot"]
        assert snap_step["status"] == "skipped"


@pytest.mark.asyncio
async def test_scheduler_partial_collection_handling(patch_test_db: AsyncSession):
    """Partial collection with valid records creates snapshots only for completed runs."""
    db = patch_test_db
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    source = DataSource(name="Apify", source_type=DataSourceType.APIFY, is_active=True)
    db.add(source)
    await db.flush()
    job = CollectionJob(data_source_id=source.id, name="sched_pjob", job_type="apify_live")
    db.add(job)
    await db.flush()

    c_run = CollectionRun(
        id="run_sched_partial_01",
        job_id=job.id,
        status=CollectionJobStatus.COMPLETED,
        completed_at=datetime.now(timezone.utc),
    )
    db.add(c_run)

    adv = Advertiser(id="adv_sched_p1", name="SchedPBrand", normalized_name="schedpbrand", source_type=DataSourceType.META_AD_LIBRARY, country="US")
    db.add(adv)
    await db.flush()

    ad = Advertisement(id="ad_sched_p1", external_id="ext_sched_p1", source_type=DataSourceType.META_AD_LIBRARY, advertiser_id=adv.id)
    db.add(ad)

    sr = SourceRecord(
        id="sr_sched_p1",
        collection_run_id=c_run.id,
        source_type=DataSourceType.META_AD_LIBRARY,
        external_id="ext_sched_p1",
        raw_data={"id": "ext_sched_p1", "isActive": True},
        created_at=datetime.now(timezone.utc),
    )
    db.add(sr)
    await db.commit()

    service = SchedulerService()
    service._last_collection = datetime.now(timezone.utc)
    service._last_collection_result = {
        "status": "partial",
        "records_collected": 1,
        "collection_run_ids": [c_run.id],
        "errors": ["query2 timed out"],
    }

    with patch("app.services.scheduler.get_session") as mock_get_session:
        class SessionContext:
            async def __aenter__(self):
                return db
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        mock_get_session.return_value = SessionContext()

        pipeline_result = await service._execute_pipeline("test_run")
        snap_step = pipeline_result["steps"]["snapshot"]
        assert snap_step.get("created") == 1
        assert snap_step.get("collection_run_ids") == [c_run.id]
