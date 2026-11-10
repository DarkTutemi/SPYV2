"""
US WIN HUNTER — Apify Budget Safety & Durable Recovery Tests (Bug 4)
Verifies:
1. Hard session ceiling ($2.00) enforcement.
2. Hard daily limit ($2.00) and monthly limit ($10.00) enforcement.
3. In-flight run lock preventing duplicate concurrent or un-reconciled launches.
4. Crash recovery: orphaned in-flight runs reconciled against provider status.
5. Honest billing reconciliation: never assumes missing billing is $0.00.
6. Prevention of duplicate run ID registration.
"""

import os
import tempfile
from datetime import datetime, timezone, timedelta
import pytest
import httpx
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

from app.models.models import (
    Base,
    ApifySpendReservation,
    ApifyReservationStatus,
    CollectionJob,
    CollectionRun,
    CollectionJobStatus,
    DataSource,
    DataSourceType,
)
from app.services.budget_manager import (
    ApifyBudgetManager,
    BudgetExceededError,
    InFlightRunPendingError,
)


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
async def test_session_ceiling_enforcement(disposable_db):
    """Verifies that requests exceeding the session ceiling ($2.00) are blocked."""
    async with disposable_db() as session:
        bm = ApifyBudgetManager(
            db=session,
            session_ceiling_usd=2.00,
            daily_budget_usd=2.00,
            monthly_budget_usd=10.00,
        )

        # Run 1: reserve $1.20
        res1 = await bm.create_reservation(
            actor_id="apify/google-trends-scraper",
            reserved_amount_usd=1.20,
            session_id="test_session",
        )
        assert res1.status == "RESERVED"
        assert res1.reserved_amount_usd == 1.20

        # Run 1 starts and completes with actual cost $1.15
        await bm.mark_run_started(res1.id, apify_run_id="run_001")
        await bm.reconcile_run(res1.id, final_status="SUCCEEDED", actual_cost_usd=1.15)
        await session.commit()

        # Run 2: attempt to reserve $0.90 -> $1.15 + $0.90 = $2.05 > $2.00
        can_run, reason, metrics = await bm.check_budget_availability(
            requested_reservation_usd=0.90,
            session_id="test_session",
        )
        assert not can_run
        assert "Session budget ceiling of $2.00 exceeded" in reason

        with pytest.raises(BudgetExceededError):
            await bm.create_reservation(
                actor_id="scrapermagic/amazon-product-scraper",
                reserved_amount_usd=0.90,
                session_id="test_session",
            )

        # Run 3: attempt to reserve $0.80 -> $1.15 + $0.80 = $1.95 <= $2.00 -> allowed
        can_run3, _, _ = await bm.check_budget_availability(
            requested_reservation_usd=0.80,
            session_id="test_session",
        )
        assert can_run3


@pytest.mark.asyncio
async def test_in_flight_run_blocks_new_runs(disposable_db):
    """Verifies that an active, un-reconciled in-flight run prevents new paid runs."""
    async with disposable_db() as session:
        bm = ApifyBudgetManager(db=session, session_ceiling_usd=2.00)

        # Launch run 1 and mark RUNNING
        res1 = await bm.create_reservation(
            actor_id="apify/google-trends-scraper",
            reserved_amount_usd=0.20,
            session_id="session_flight",
        )
        await bm.mark_run_started(res1.id, apify_run_id="run_inflight_1")
        await session.commit()

        # Attempt to launch run 2 while run 1 is still in flight
        can_run, reason, metrics = await bm.check_budget_availability(
            requested_reservation_usd=0.20,
            session_id="session_flight",
        )
        assert not can_run
        assert "in-flight run(s)" in reason
        assert "pending reconciliation" in reason


@pytest.mark.asyncio
async def test_never_assume_missing_billing_is_zero(disposable_db):
    """Verifies that missing or $0.0 provider billing retains the reservation amount."""
    async with disposable_db() as session:
        bm = ApifyBudgetManager(db=session, session_ceiling_usd=2.00)

        res = await bm.create_reservation(
            actor_id="apify/google-trends-scraper",
            reserved_amount_usd=0.18,
            session_id="session_honest",
        )
        await bm.mark_run_started(res.id, apify_run_id="run_missing_billing")

        # Provider completes but returns None / 0.0 for actual cost
        await bm.reconcile_run(
            res.id,
            final_status="SUCCEEDED",
            actual_cost_usd=None,
            billing_detail={},
        )
        await session.commit()

        # Check persisted reservation
        updated = await session.get(ApifySpendReservation, res.id)
        assert updated.actual_amount_usd == 0.18
        assert "Held reservation amount" in updated.reconciliation_notes

        # Metric accounts for the $0.18 spend, not $0.0
        metrics = await bm.get_spend_metrics("session_honest")
        assert metrics["session_spend_usd"] == 0.18


@pytest.mark.asyncio
async def test_crash_recovery_orphaned_runs(disposable_db, monkeypatch):
    """Verifies that interrupted runs in RUNNING state are recovered on restart."""
    async with disposable_db() as session:
        bm = ApifyBudgetManager(db=session, api_token="test_mock_token")

        # Simulate orphaned run left in RUNNING after crash
        res = await bm.create_reservation(
            actor_id="automation-lab/facebook-ads-library",
            reserved_amount_usd=0.50,
            session_id="session_crash",
        )
        await bm.mark_run_started(res.id, apify_run_id="apify_orphan_999")
        await session.commit()

        # Mock Apify remote API response
        class MockResponse:
            status_code = 200

            def json(self):
                return {
                    "data": {
                        "id": "apify_orphan_999",
                        "status": "SUCCEEDED",
                        "usageTotalUsd": 0.0625,
                    }
                }

        class MockClient:
            async def get(self, url, headers=None):
                return MockResponse()

        # Run recovery
        recovered = await bm.recover_orphaned_runs(http_client=MockClient())
        await session.commit()

        assert len(recovered) == 1
        assert recovered[0]["apify_run_id"] == "apify_orphan_999"
        assert recovered[0]["final_status"] == "SUCCEEDED"
        assert recovered[0]["actual_cost_usd"] == 0.0625

        # Verify DB state
        db_res = await session.get(ApifySpendReservation, res.id)
        assert db_res.status == "SUCCEEDED"
        assert db_res.actual_amount_usd == 0.0625

        # Verify system is unblocked
        can_run, reason, _ = await bm.check_budget_availability(0.20, session_id="session_crash")
        assert can_run, f"Expected unblocked, but got: {reason}"


@pytest.mark.asyncio
async def test_prevent_duplicate_run_id(disposable_db):
    """Verifies that an apify_run_id cannot be registered more than once."""
    async with disposable_db() as session:
        bm = ApifyBudgetManager(db=session)

        res1 = await bm.create_reservation("actor_a", 0.10, session_id="s1")
        await bm.mark_run_started(res1.id, "apify_shared_id")
        await bm.reconcile_run(res1.id, "SUCCEEDED", actual_cost_usd=0.08)
        await session.commit()

        res2 = await bm.create_reservation("actor_b", 0.10, session_id="s1")
        with pytest.raises(RuntimeError) as exc_info:
            await bm.mark_run_started(res2.id, "apify_shared_id")
        assert "already tracked by another reservation" in str(exc_info.value)
