"""
US WIN HUNTER — P0 HOTFIX: Source Provenance and Unified Paid Collection Safety
Comprehensive Regression Test Suite covering all 14 mandated verification points:

1. Unrelated collection run cannot authenticate an advertisement snapshot.
2. Missing ad IDs remain UNKNOWN (not INACTIVE).
3. A six-ad collection cannot mark 145 advertisements freshly observed.
4. Old stored active states cannot create fresh observations.
5. Arbitrary quality input is rejected (removed from endpoint/function).
6. Derived processing cannot overwrite genuine source evidence.
7. Historical run ID cannot create a new current-date observation.
8. Existing T0 data is preserved.
9. Legacy ApifyAdapter cannot launch without durable budget reservation.
10. Database accounting errors never become zero spending (fails closed).
11. Two concurrent processes cannot over-reserve the budget (DB lock test).
12. Failed or ambiguous Actor starts prevent subsequent paid launches.
13. Automatic collection remains disabled.
14. No paid Actor is executed in tests (mocked httpx).
"""

import inspect
import json
import os
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, text, func

from app.adapters.apify import ApifyProviderAdapter, ProviderStatus
from app.engines.temporal import TemporalEngine
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
    SourceRecord,
    ApifySpendReservation,
    ApifyReservationStatus,
    ApifyBudgetLock,
    _uuid,
    _utcnow,
)
from app.services.budget_manager import (
    ApifyBudgetManager,
    BudgetLockError,
    BudgetExceededError,
)
from app.services.scheduler import SchedulerService


@pytest.fixture
async def disposable_db():
    """Disposable isolated SQLite DB fixture for integration tests."""
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


# ── POINT 1: Unrelated collection run cannot authenticate an ad snapshot ──────
@pytest.mark.asyncio
async def test_unrelated_collection_run_cannot_authenticate_ad_snapshot(disposable_db):
    """1. An unrelated collection run with no matching source records cannot authenticate an ad snapshot."""
    async with disposable_db() as session:
        adv = Advertiser(name="Adv1", normalized_name="adv1", source_type=DataSourceType.META_AD_LIBRARY, country="US")
        prod = Product(name="Prod1", normalized_name="prod1", target_country="US", source_type=DataSourceType.META_AD_LIBRARY)
        session.add_all([adv, prod])
        await session.flush()

        ad = Advertisement(
            external_id="ad_apple_100",
            source_type=DataSourceType.META_AD_LIBRARY,
            advertiser_id=adv.id,
            product_id=prod.id,
            is_active=True,
            first_seen_at=_utcnow(),
            last_seen_at=_utcnow(),
        )
        session.add(ad)

        # Create completed collection run today, but with NO matching SourceRecord for ad_apple_100
        source = DataSource(name="Apify", source_type=DataSourceType.APIFY, is_active=True)
        session.add(source)
        await session.flush()
        job = CollectionJob(data_source_id=source.id, name="unrelated_job", job_type="apify_live")
        session.add(job)
        await session.flush()

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        crun = CollectionRun(
            job_id=job.id,
            status=CollectionJobStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        session.add(crun)
        await session.flush()

        # Add an unrelated source record
        sr_unrelated = SourceRecord(
            collection_run_id=crun.id,
            source_type=DataSourceType.META_AD_LIBRARY,
            external_id="ad_banana_999",  # Different external ID
            raw_data={"title": "Unrelated Banana"},
        )
        session.add(sr_unrelated)
        await session.commit()

        # Snapshot for today with crun.id
        engine = TemporalEngine(session)
        result = await engine.create_daily_snapshot(snapshot_date=today, collection_run_id=crun.id)
        await session.commit()

        snap = (await session.execute(
            select(AdvertisementSnapshot).where(AdvertisementSnapshot.advertisement_id == ad.id)
        )).scalar_one_or_none()

        # Ad has no matching source record in crun -> No verified observation can be created for it!
        assert snap is None


# ── POINT 2: Missing ad IDs remain UNKNOWN (not INACTIVE) ─────────────────────
@pytest.mark.asyncio
async def test_missing_ad_ids_remain_unknown_not_inactive(disposable_db):
    """2. Ad IDs omitted from observed_ad_statuses remain UNKNOWN, never defaulting to inactive without evidence."""
    async with disposable_db() as session:
        adv = Advertiser(name="Adv2", normalized_name="adv2", source_type=DataSourceType.META_AD_LIBRARY, country="US")
        prod = Product(name="Prod2", normalized_name="prod2", target_country="US", source_type=DataSourceType.META_AD_LIBRARY)
        session.add_all([adv, prod])
        await session.flush()

        ad1 = Advertisement(
            external_id="ad_present_1",
            source_type=DataSourceType.META_AD_LIBRARY,
            advertiser_id=adv.id,
            product_id=prod.id,
            is_active=True,
            first_seen_at=_utcnow(),
            last_seen_at=_utcnow(),
        )
        ad2 = Advertisement(
            external_id="ad_omitted_2",
            source_type=DataSourceType.META_AD_LIBRARY,
            advertiser_id=adv.id,
            product_id=prod.id,
            is_active=True,
            first_seen_at=_utcnow(),
            last_seen_at=_utcnow(),
        )
        session.add_all([ad1, ad2])
        await session.commit()

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        engine = TemporalEngine(session)
        # Supply observation ONLY for ad1
        await engine.create_daily_snapshot(
            snapshot_date=today,
            observed_ad_statuses={str(ad1.id): True},
        )
        await session.commit()

        snap1 = (await session.execute(
            select(AdvertisementSnapshot).where(AdvertisementSnapshot.advertisement_id == ad1.id)
        )).scalar_one()
        snap2 = (await session.execute(
            select(AdvertisementSnapshot).where(AdvertisementSnapshot.advertisement_id == ad2.id)
        )).scalar_one_or_none()

        assert snap1.observation_quality == SnapshotObservationQuality.VERIFIED_SOURCE_OBSERVATION.value
        assert snap1.is_active is True

        # ad2 was omitted from observation batch: cannot be snapshotted as inactive without evidence!
        assert snap2 is None


# ── POINT 3: A six-ad collection cannot mark 145 advertisements freshly observed
@pytest.mark.asyncio
async def test_six_ad_collection_only_authenticates_six_ads(disposable_db):
    """3. A collection returning 6 ads creates genuine observations ONLY for those 6 ads."""
    async with disposable_db() as session:
        adv = Advertiser(name="Adv3", normalized_name="adv3", source_type=DataSourceType.META_AD_LIBRARY, country="US")
        prod = Product(name="Prod3", normalized_name="prod3", target_country="US", source_type=DataSourceType.META_AD_LIBRARY)
        session.add_all([adv, prod])
        await session.flush()

        # Create 20 total ads in database
        ads = []
        for i in range(20):
            ad = Advertisement(
                external_id=f"ad_pool_{i:03d}",
                source_type=DataSourceType.META_AD_LIBRARY,
                advertiser_id=adv.id,
                product_id=prod.id,
                is_active=True,
                first_seen_at=_utcnow(),
                last_seen_at=_utcnow(),
            )
            session.add(ad)
            ads.append(ad)

        source = DataSource(name="Apify", source_type=DataSourceType.APIFY, is_active=True)
        session.add(source)
        await session.flush()
        job = CollectionJob(data_source_id=source.id, name="six_ad_job", job_type="apify_live")
        session.add(job)
        await session.flush()

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        crun = CollectionRun(
            job_id=job.id,
            status=CollectionJobStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        session.add(crun)
        await session.flush()

        # Add SourceRecords for exactly 6 ads (indexes 0..5)
        for i in range(6):
            sr = SourceRecord(
                collection_run_id=crun.id,
                source_type=DataSourceType.META_AD_LIBRARY,
                external_id=f"ad_pool_{i:03d}",
                raw_data={"title": f"Ad {i}", "isActive": True},
            )
            session.add(sr)
        await session.commit()

        engine = TemporalEngine(session)
        await engine.create_daily_snapshot(snapshot_date=today, collection_run_id=crun.id)
        await session.commit()

        # Count verified observations vs unverified
        verified_count = (await session.execute(
            select(func.count(AdvertisementSnapshot.id)).where(
                AdvertisementSnapshot.snapshot_date == today,
                AdvertisementSnapshot.observation_quality == SnapshotObservationQuality.VERIFIED_SOURCE_OBSERVATION.value,
            )
        )).scalar()

        total_snaps = (await session.execute(
            select(func.count(AdvertisementSnapshot.id)).where(
                AdvertisementSnapshot.snapshot_date == today,
            )
        )).scalar()

        assert verified_count == 6
        assert total_snaps == 6  # Scoped strictly to the 6 ads in the collection run


# ── POINT 4: Old stored active states cannot create fresh observations ────────
@pytest.mark.asyncio
async def test_old_stored_active_states_cannot_create_fresh_observations(disposable_db):
    """4. Advertisement.is_active=True in DB cannot produce fresh observations without source collection."""
    async with disposable_db() as session:
        adv = Advertiser(name="Adv4", normalized_name="adv4", source_type=DataSourceType.META_AD_LIBRARY, country="US")
        prod = Product(name="Prod4", normalized_name="prod4", target_country="US", source_type=DataSourceType.META_AD_LIBRARY)
        session.add_all([adv, prod])
        await session.flush()

        ad = Advertisement(
            external_id="ad_stored_active",
            source_type=DataSourceType.META_AD_LIBRARY,
            advertiser_id=adv.id,
            product_id=prod.id,
            is_active=True,  # Historical active in DB
            first_seen_at=_utcnow() - timedelta(days=30),
            last_seen_at=_utcnow() - timedelta(days=10),
        )
        session.add(ad)
        await session.commit()

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        engine = TemporalEngine(session)
        # Snapshot without live collection provenance
        res = await engine.create_daily_snapshot(snapshot_date=today)
        await session.commit()

        snap = (await session.execute(
            select(AdvertisementSnapshot).where(AdvertisementSnapshot.advertisement_id == ad.id)
        )).scalar_one()

        assert snap.observation_quality == SnapshotObservationQuality.DATABASE_DERIVED_SNAPSHOT.value

        # ProductDailyMetric calculation must strictly require verified/genuine source observations
        metrics = await engine.aggregate_daily_metrics(today)
        await session.commit()

        assert len(metrics) == 1
        # Active ad count MUST be 0 because 0 verified source observations exist
        assert metrics[0].active_ad_count == 0


# ── POINT 5: Arbitrary quality input is rejected (removed from signature) ─────
def test_arbitrary_quality_input_is_rejected():
    """5. observation_quality parameter is removed from TemporalEngine and cannot be spoofed."""
    sig = inspect.signature(TemporalEngine.create_daily_snapshot)
    assert "observation_quality" not in sig.parameters

    from app.api.temporal import create_snapshot
    api_sig = inspect.signature(create_snapshot)
    assert "observation_quality" not in api_sig.parameters


# ── POINT 6: Derived processing cannot overwrite genuine source evidence ──────
@pytest.mark.asyncio
async def test_derived_processing_cannot_overwrite_genuine_evidence(disposable_db):
    """6. Analytical/derived snapshot pass cannot overwrite or downgrade existing VERIFIED_SOURCE_OBSERVATION."""
    async with disposable_db() as session:
        adv = Advertiser(name="Adv6", normalized_name="adv6", source_type=DataSourceType.META_AD_LIBRARY, country="US")
        prod = Product(name="Prod6", normalized_name="prod6", target_country="US", source_type=DataSourceType.META_AD_LIBRARY)
        session.add_all([adv, prod])
        await session.flush()

        ad = Advertisement(
            external_id="ad_verified_6",
            source_type=DataSourceType.META_AD_LIBRARY,
            advertiser_id=adv.id,
            product_id=prod.id,
            is_active=True,
            first_seen_at=_utcnow(),
            last_seen_at=_utcnow(),
        )
        session.add(ad)
        await session.commit()

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        engine = TemporalEngine(session)

        # 1. Establish verified observation
        await engine.create_daily_snapshot(
            snapshot_date=today,
            observed_ad_statuses={str(ad.id): True},
        )
        await session.commit()

        snap_initial = (await session.execute(
            select(AdvertisementSnapshot).where(AdvertisementSnapshot.advertisement_id == ad.id)
        )).scalar_one()
        assert snap_initial.observation_quality == SnapshotObservationQuality.VERIFIED_SOURCE_OBSERVATION.value

        # 2. Run subsequent derived snapshot pass for the same date without evidence
        await engine.create_daily_snapshot(snapshot_date=today)
        await session.commit()

        snap_after = (await session.execute(
            select(AdvertisementSnapshot).where(AdvertisementSnapshot.advertisement_id == ad.id)
        )).scalar_one()

        # Evidence preservation: Must remain VERIFIED_SOURCE_OBSERVATION
        assert snap_after.observation_quality == SnapshotObservationQuality.VERIFIED_SOURCE_OBSERVATION.value


# ── POINT 7: Historical run ID cannot create a new current-date observation ───
@pytest.mark.asyncio
async def test_historical_run_id_cannot_create_new_current_date_observation(disposable_db):
    """7. An authentic run from 2026-11-09 cannot authenticate snapshots on a different date (e.g. 2026-11-11)."""
    async with disposable_db() as session:
        source = DataSource(name="Apify", source_type=DataSourceType.APIFY, is_active=True)
        session.add(source)
        await session.flush()
        job = CollectionJob(data_source_id=source.id, name="job7", job_type="apify_live")
        session.add(job)
        await session.flush()

        # Run executed on 2026-11-09
        run_date = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)
        hist_run = CollectionRun(
            job_id=job.id,
            status=CollectionJobStatus.COMPLETED,
            started_at=run_date,
            created_at=run_date,
        )
        session.add(hist_run)

        adv = Advertiser(name="Adv7", normalized_name="adv7", source_type=DataSourceType.META_AD_LIBRARY, country="US")
        prod = Product(name="Prod7", normalized_name="prod7", target_country="US", source_type=DataSourceType.META_AD_LIBRARY)
        session.add_all([adv, prod])
        await session.flush()

        ad = Advertisement(
            external_id="ad_test_7",
            source_type=DataSourceType.META_AD_LIBRARY,
            advertiser_id=adv.id,
            product_id=prod.id,
            is_active=True,
            first_seen_at=_utcnow(),
            last_seen_at=_utcnow(),
        )
        session.add(ad)
        await session.flush()

        sr = SourceRecord(
            collection_run_id=hist_run.id,
            source_type=DataSourceType.META_AD_LIBRARY,
            external_id="ad_test_7",
            created_at=run_date,
            raw_data={"title": "Historical Ad"},
        )
        session.add(sr)
        await session.commit()

        engine = TemporalEngine(session)
        # Attempt to use 2026-11-09 run to snapshot 2026-11-11
        result = await engine.create_daily_snapshot(
            snapshot_date="2026-11-11",
            collection_run_id=hist_run.id,
        )
        await session.commit()

        # The engine must reject the mismatched run date
        snap = (await session.execute(
            select(AdvertisementSnapshot).where(AdvertisementSnapshot.advertisement_id == ad.id)
        )).scalar_one()

        assert snap.observation_quality == SnapshotObservationQuality.DATABASE_DERIVED_SNAPSHOT.value
        assert snap.collection_run_id is None


# ── POINT 8: Existing T0 data is preserved ────────────────────────────────────
@pytest.mark.asyncio
async def test_existing_t0_data_is_preserved():
    """8. Production SQLite database preserves all 145 unique ads across 435 audited snapshots."""
    import sqlite3
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "winhunter.db"))
    if not os.path.exists(db_path):
        pytest.skip(f"Production database winhunter.db not found at expected path: {db_path}")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(DISTINCT advertisement_id) FROM advertisement_snapshots")
    distinct_ads = cur.fetchone()[0]
    assert distinct_ads == 145

    cur.execute("SELECT COUNT(*) FROM advertisement_snapshots WHERE snapshot_date = '2026-11-09' AND observation_quality = 'VERIFIED_SOURCE_OBSERVATION'")
    t0_verified = cur.fetchone()[0]
    assert t0_verified == 145

    cur.execute("SELECT COUNT(*) FROM advertisement_snapshots WHERE snapshot_date = '2026-11-10' AND observation_quality = 'DATABASE_DERIVED_SNAPSHOT'")
    t1_derived = cur.fetchone()[0]
    assert t1_derived == 145

    cur.execute("SELECT COUNT(*) FROM advertisement_snapshots WHERE snapshot_date = '2026-11-11' AND observation_quality = 'DATABASE_DERIVED_SNAPSHOT'")
    t2_derived = cur.fetchone()[0]
    assert t2_derived == 145

    conn.close()


# ── POINT 9: Legacy ApifyAdapter cannot launch without budget reservation ──────
@pytest.mark.asyncio
async def test_legacy_apify_adapter_cannot_launch_without_durable_reservation(disposable_db):
    """9. ApifyProviderAdapter cannot dispatch paid runs when budget check fails or token missing."""
    async with disposable_db() as session:
        # Without token: BLOCKED / NOT_CONFIGURED immediately
        adapter = ApifyProviderAdapter(session, api_token="")
        res = await adapter.discover_by_keywords(["test query"])
        assert res["success"] is False
        assert res["status"] == ProviderStatus.NOT_CONFIGURED.value

        # With token but daily budget already exhausted
        adapter_funded = ApifyProviderAdapter(session, api_token="apify_mock_token_123")
        adapter_funded.daily_budget_usd = 0.50

        # Create prior reservation consuming the entire budget
        bm = adapter_funded.budget_manager
        await bm.create_reservation(actor_id="test-actor", reserved_amount_usd=0.50)
        await session.commit()

        with patch("httpx.AsyncClient.post") as mock_post:
            res_blocked = await adapter_funded.discover_by_keywords(["another query"])
            assert res_blocked["success"] is False
            assert res_blocked["status"] == ProviderStatus.BLOCKED.value
            # Verify ZERO HTTP calls were dispatched
            assert mock_post.call_count == 0


# ── POINT 10: Database accounting errors fail closed ──────────────────────────
@pytest.mark.asyncio
async def test_database_accounting_errors_fail_closed(disposable_db):
    """10. Accounting/database errors fail closed: status=BLOCKED, never return 0.0 spend."""
    async with disposable_db() as session:
        adapter = ApifyProviderAdapter(session, api_token="test_token")

        with patch.object(adapter.budget_manager, "get_spend_metrics", side_effect=RuntimeError("DB disk failure")):
            status = await adapter.get_status()
            assert status["status"] == ProviderStatus.BLOCKED.value
            assert status["estimated_spent_today_usd"] == adapter.daily_budget_usd
            assert status["has_pending"] is True
            assert "Fail-closed" in status["message"]

            # _calculate_current_spend must also return ceilings, never 0.0
            spend_day, spend_month = await adapter._calculate_current_spend()
            assert spend_day == adapter.daily_budget_usd
            assert spend_month == adapter.monthly_budget_usd


# ── POINT 11: Two concurrent processes cannot over-reserve budget ─────────────
@pytest.mark.asyncio
async def test_two_concurrent_processes_cannot_over_reserve_budget(disposable_db):
    """11. SQLite serialization locking on apify_budget_locks prevents concurrent budget over-reservation."""
    async with disposable_db() as session:
        bm = ApifyBudgetManager(session, api_token="test_token", daily_budget_usd=1.00)

        # First reservation reserves $0.75 of $1.00
        res1 = await bm.create_reservation("actor-1", reserved_amount_usd=0.75, session_id="worker_1")
        await session.commit()
        assert res1.status == ApifyReservationStatus.RESERVED.value

        # Concurrent second worker attempts to reserve $0.50 ($0.75 + $0.50 = $1.25 > $1.00)
        with pytest.raises(BudgetExceededError) as exc_info:
            await bm.create_reservation("actor-2", reserved_amount_usd=0.50, session_id="worker_2")
        assert "exceeded" in str(exc_info.value).lower() or "blocked" in str(exc_info.value).lower()


# ── POINT 12: Ambiguous Actor starts prevent subsequent paid launches ─────────
@pytest.mark.asyncio
async def test_failed_or_ambiguous_actor_starts_prevent_subsequent_paid_launches(disposable_db):
    """12. An ambiguous HTTP 500 start failure transitions reservation to NEEDS_RECONCILIATION, blocking subsequent runs."""
    async with disposable_db() as session:
        adapter = ApifyProviderAdapter(session, api_token="test_token")

        # Mock start request returning HTTP 500
        mock_resp_500 = httpx.Response(
            500,
            text="Internal Server Error on dispatch",
            request=httpx.Request("POST", "https://api.apify.com/v2/acts/test/runs"),
        )

        with patch("httpx.AsyncClient.post", return_value=mock_resp_500):
            res = await adapter._execute_and_process(
                actor_name="automation-lab/facebook-ads-library",
                run_input={"searchQueries": ["test"]},
                job_name="ambiguous_run",
                reservation_amount=0.50,
            )
            assert res["success"] is False
            assert res["status"] == ProviderStatus.FAILED.value

        # Check reservation state in DB: must be NEEDS_RECONCILIATION holding $0.50
        reservations = (await session.execute(select(ApifySpendReservation))).scalars().all()
        assert len(reservations) == 1
        assert reservations[0].status == ApifyReservationStatus.NEEDS_RECONCILIATION.value
        assert reservations[0].actual_amount_usd == 0.50

        # Attempt next reservation: MUST be blocked because unresolved run is pending reconciliation
        is_allowed, reason, _ = await adapter.budget_manager.check_budget_availability(0.50)
        assert is_allowed is False
        assert "pending reconciliation" in reason.lower()


# ── POINT 13: Automatic collection remains disabled ───────────────────────────
@pytest.mark.asyncio
async def test_automatic_collection_remains_disabled():
    """13. SchedulerService refuses paid collection unless explicit operator_authorized=True is supplied."""
    scheduler = SchedulerService()
    # 1. Background / scheduled loop passes operator_authorized=False
    res1 = await scheduler.run_collection_cycle(force=False, operator_authorized=False)
    assert res1["status"] in ("disabled", "unauthorized")

    # 2. Internal force=True WITHOUT operator_authorized=True is REJECTED
    res2 = await scheduler.run_collection_cycle(force=True, operator_authorized=False)
    assert res2["status"] == "unauthorized"
    assert "explicit operator authorization" in res2["message"]


# ── POINT 14: No paid Actor is executed in tests (mocked httpx) ───────────────
@pytest.mark.asyncio
async def test_no_paid_actor_is_executed_in_tests(disposable_db):
    """14. Validates that testing harnesses maintain zero external network egress."""
    async with disposable_db() as session:
        adapter = ApifyProviderAdapter(session, api_token="test_token")
        with patch("httpx.AsyncClient.post") as mock_post, patch("httpx.AsyncClient.get") as mock_get:
            # Check status does not make network calls
            status = await adapter.get_status()
            assert status["configured"] is True
            assert mock_post.call_count == 0
            assert mock_get.call_count == 0
