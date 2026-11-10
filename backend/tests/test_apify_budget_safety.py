"""
US WIN HUNTER — Apify Budget Safety & Durable Lifecycle Regression Suite
Covers all 10 mandated scenarios for Fix A:
1. Two sequential successful Actors (RESERVE -> START -> SAVE -> POLL -> TERMINAL -> RECONCILE -> NEXT).
2. First Actor fails before launch (clean release with $0.00 spend).
3. First Actor is still RUNNING after polling timeout (NEEDS_RECONCILIATION, reservation held, blocks Actor 2).
4. Provider API returns HTTP 500 during recovery (NEEDS_RECONCILIATION, reservation held, blocks new runs).
5. Provider returns an unknown status (NEEDS_RECONCILIATION, reservation held).
6. Crash occurs after remote launch attempt but before ID persistence (NEEDS_RECONCILIATION, held budget).
7. Missing billing data (never assumed $0.00, holds reservation amount).
8. Concurrent budget reservations (atomic serialization test ensuring budget ceiling is never exceeded).
9. Real zero-charge terminal result with explicit billing confirmation ($0.00 accepted).
10. No duplicate paid run after restart (prevent duplicate run ID, safe reconciliation).
"""

import asyncio
import os
import tempfile
from datetime import datetime, timezone
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

from app.models.models import (
    Base,
    ApifySpendReservation,
    ApifyReservationStatus,
    ApifyBudgetLock,
)
from app.services.budget_manager import (
    ApifyBudgetManager,
    BudgetExceededError,
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
async def test_scenario_1_sequential_successful_actors(disposable_db):
    """Scenario 1: Two sequential successful Actors completing full lifecycle before next starts."""
    async with disposable_db() as session:
        bm = ApifyBudgetManager(db=session, session_ceiling_usd=2.00)

        # Provider 1: Reserve -> Launch Attempt -> Start -> Poll -> Terminal -> Reconcile -> Commit
        res1 = await bm.create_reservation("apify/google-trends-scraper", 0.15, session_id="s1")
        assert res1.status == ApifyReservationStatus.RESERVED.value
        await bm.mark_launch_attempted(res1.id)
        await bm.mark_run_started(res1.id, "run_trends_001")
        await bm.reconcile_run(res1.id, "SUCCEEDED", actual_cost_usd=0.12, billing_detail={"usageTotalUsd": 0.12})
        await session.commit()

        # Provider 2: Can only run because Provider 1 was cleanly resolved
        res2 = await bm.create_reservation("scrapermagic/amazon-product-scraper", 0.15, session_id="s1")
        assert res2.status == ApifyReservationStatus.RESERVED.value
        await bm.mark_launch_attempted(res2.id)
        await bm.mark_run_started(res2.id, "run_amazon_002")
        await bm.reconcile_run(res2.id, "SUCCEEDED", actual_cost_usd=0.14, billing_detail={"usageTotalUsd": 0.14})
        await session.commit()

        metrics = await bm.get_spend_metrics(session_id="s1")
        assert metrics["session_spend_usd"] == 0.26
        assert len(metrics["pending_in_flight_runs"]) == 0


@pytest.mark.asyncio
async def test_scenario_2_first_actor_fails_before_launch(disposable_db):
    """Scenario 2: First Actor fails pre-dispatch; released cleanly with $0 spend, second Actor succeeds."""
    async with disposable_db() as session:
        bm = ApifyBudgetManager(db=session, session_ceiling_usd=2.00)

        # Actor 1 reserves, but local validation fails before launch attempt
        res1 = await bm.create_reservation("actor_fail_pre", 0.30, session_id="s2")
        await bm.reconcile_run(res1.id, "FAILED", actual_cost_usd=0.0, notes="Pre-launch validation error")
        await session.commit()

        r1_db = await session.get(ApifySpendReservation, res1.id)
        assert r1_db.status == "FAILED"
        assert r1_db.actual_amount_usd == 0.0

        # Actor 2 can immediately proceed and utilize the full budget
        res2 = await bm.create_reservation("actor_success", 0.30, session_id="s2")
        await bm.mark_launch_attempted(res2.id)
        await bm.mark_run_started(res2.id, "run_success_002")
        await bm.reconcile_run(res2.id, "SUCCEEDED", actual_cost_usd=0.25)
        await session.commit()

        metrics = await bm.get_spend_metrics(session_id="s2")
        assert metrics["session_spend_usd"] == 0.25


@pytest.mark.asyncio
async def test_scenario_3_polling_timeout_blocks_subsequent_runs(disposable_db):
    """Scenario 3: First Actor still RUNNING after polling timeout; holds reservation, blocks Actor 2."""
    async with disposable_db() as session:
        bm = ApifyBudgetManager(db=session, session_ceiling_usd=2.00)

        res1 = await bm.create_reservation("actor_slow", 0.40, session_id="s3")
        await bm.mark_launch_attempted(res1.id)
        await bm.mark_run_started(res1.id, "run_slow_001")

        # Polling window expires
        await bm.mark_polling_timeout(res1.id, "run_slow_001", notes="Polling window 180s expired")
        await session.commit()

        r1_db = await session.get(ApifySpendReservation, res1.id)
        assert r1_db.status == ApifyReservationStatus.NEEDS_RECONCILIATION.value
        assert r1_db.reserved_amount_usd == 0.40

        # Actor 2 attempts to run: must be BLOCKED
        can_run, reason, metrics = await bm.check_budget_availability(0.20, session_id="s3")
        assert not can_run
        assert "pending reconciliation" in reason
        assert metrics["session_spend_usd"] == 0.40


@pytest.mark.asyncio
async def test_scenario_4_provider_api_http_500_during_recovery(disposable_db):
    """Scenario 4: Provider returns HTTP 500 during recovery; preserves reservation, blocks new runs."""
    async with disposable_db() as session:
        bm = ApifyBudgetManager(db=session, api_token="test_token", session_ceiling_usd=2.00)

        res = await bm.create_reservation("actor_500", 0.50, session_id="s4")
        await bm.mark_launch_attempted(res.id)
        await bm.mark_run_started(res.id, "run_apify_500")
        await session.commit()

        class Mock500Response:
            status_code = 500
            def json(self): return {"error": "Internal Server Error"}

        class Mock500Client:
            async def get(self, url, headers=None): return Mock500Response()

        recovered = await bm.recover_orphaned_runs(http_client=Mock500Client())
        await session.commit()

        assert len(recovered) == 1
        assert recovered[0]["action"] == "HELD_API_ERROR"
        assert recovered[0]["status"] == ApifyReservationStatus.NEEDS_RECONCILIATION.value
        assert recovered[0]["cost"] == 0.50

        # Verify system remains blocked
        can_run, reason, _ = await bm.check_budget_availability(0.10, session_id="s4")
        assert not can_run
        assert "pending reconciliation" in reason


@pytest.mark.asyncio
async def test_scenario_5_provider_unknown_status(disposable_db):
    """Scenario 5: Provider returns unmapped status; preserves reservation, does not abort."""
    async with disposable_db() as session:
        bm = ApifyBudgetManager(db=session, api_token="test_token", session_ceiling_usd=2.00)

        res = await bm.create_reservation("actor_unknown_st", 0.35, session_id="s5")
        await bm.mark_launch_attempted(res.id)
        await bm.mark_run_started(res.id, "run_custom_status")
        await session.commit()

        class MockCustomStatusResponse:
            status_code = 200
            def json(self):
                return {"data": {"id": "run_custom_status", "status": "CUSTOM_MAINTENANCE_PAUSED"}}

        class MockCustomClient:
            async def get(self, url, headers=None): return MockCustomStatusResponse()

        recovered = await bm.recover_orphaned_runs(http_client=MockCustomClient())
        await session.commit()

        assert len(recovered) == 1
        assert recovered[0]["action"] == "HELD_UNKNOWN_STATUS"
        assert recovered[0]["status"] == ApifyReservationStatus.NEEDS_RECONCILIATION.value
        assert recovered[0]["cost"] == 0.35


@pytest.mark.asyncio
async def test_scenario_6_crash_after_launch_attempt_ambiguity(disposable_db):
    """Scenario 6: Crash post-dispatch without saved run ID; preserves reservation, requires reconciliation."""
    async with disposable_db() as session:
        bm = ApifyBudgetManager(db=session, session_ceiling_usd=2.00)

        # Reservation created and launch attempted, but process dies before mark_run_started saves run ID
        res = await bm.create_reservation("actor_ambiguous", 0.45, session_id="s6")
        await bm.mark_launch_attempted(res.id)
        await session.commit()

        # Restart recovery
        recovered = await bm.recover_orphaned_runs()
        await session.commit()

        assert len(recovered) == 1
        assert recovered[0]["action"] == "HELD_AMBIGUOUS_START"
        assert recovered[0]["status"] == ApifyReservationStatus.NEEDS_RECONCILIATION.value
        assert recovered[0]["reserved_cost"] == 0.45

        # Does NOT allow new paid run
        can_run, reason, metrics = await bm.check_budget_availability(0.10, session_id="s6")
        assert not can_run
        assert "pending reconciliation" in reason
        assert metrics["session_spend_usd"] == 0.45


@pytest.mark.asyncio
async def test_scenario_7_missing_billing_data_holds_reservation(disposable_db):
    """Scenario 7: Succeeded run with missing/None provider billing holds reservation amount."""
    async with disposable_db() as session:
        bm = ApifyBudgetManager(db=session, session_ceiling_usd=2.00)

        res = await bm.create_reservation("actor_missing_bill", 0.28, session_id="s7")
        await bm.mark_launch_attempted(res.id)
        await bm.mark_run_started(res.id, "run_no_billing")

        # Provider completes successfully but usageTotalUsd is missing
        await bm.reconcile_run(
            res.id,
            final_status="SUCCEEDED",
            actual_cost_usd=None,
            billing_detail={},
        )
        await session.commit()

        r_db = await session.get(ApifySpendReservation, res.id)
        assert r_db.actual_amount_usd == 0.28
        assert "Held reservation amount" in r_db.reconciliation_notes

        metrics = await bm.get_spend_metrics(session_id="s7")
        assert metrics["session_spend_usd"] == 0.28


@pytest.mark.asyncio
async def test_scenario_8_concurrent_budget_reservations_serialization(disposable_db):
    """Scenario 8: Concurrent workers attempting reservations against the same budget serialize atomically."""
    # Ceiling is $2.00. Worker A requests $1.20, Worker B requests $1.20.
    # Exactly one must succeed, and the second must be rejected with BudgetExceededError.
    async with disposable_db() as session_a, disposable_db() as session_b:
        bm_a = ApifyBudgetManager(db=session_a, session_ceiling_usd=2.00)
        bm_b = ApifyBudgetManager(db=session_b, session_ceiling_usd=2.00)

        results = []
        errors = []

        async def worker_reserve(bm, sess, name):
            try:
                r = await bm.create_reservation("concurrent_actor", 1.20, session_id="concurrent_session")
                await sess.commit()
                results.append((name, r.id))
            except BudgetExceededError as e:
                errors.append((name, str(e)))

        await asyncio.gather(
            worker_reserve(bm_a, session_a, "Worker_A"),
            worker_reserve(bm_b, session_b, "Worker_B"),
        )

        # One succeeded, one was rejected (by in-flight serialization lock or budget ceiling)
        assert len(results) == 1, f"Expected 1 success, got {len(results)}"
        assert len(errors) == 1, f"Expected 1 BudgetExceededError, got {len(errors)}"
        assert any(
            msg in errors[0][1]
            for msg in ["Session budget ceiling of $2.00 exceeded", "pending reconciliation"]
        )


@pytest.mark.asyncio
async def test_scenario_9_real_zero_charge_explicit_confirmation(disposable_db):
    """Scenario 9: Terminal result with explicit confirmed zero charge accepts $0.00 actual cost."""
    async with disposable_db() as session:
        bm = ApifyBudgetManager(db=session, session_ceiling_usd=2.00)

        res = await bm.create_reservation("actor_free_tier", 0.15, session_id="s9")
        await bm.mark_launch_attempted(res.id)
        await bm.mark_run_started(res.id, "run_free_tier_001")

        # Explicit confirmation that run ran on verified free tier
        await bm.reconcile_run(
            res.id,
            final_status="SUCCEEDED",
            actual_cost_usd=0.0,
            billing_detail={
                "usageTotalUsd": 0.0,
                "explicit_zero_charge_confirmed": True,
                "pricingInfo": {"pricingModel": "FREE"},
            },
        )
        await session.commit()

        r_db = await session.get(ApifySpendReservation, res.id)
        assert r_db.actual_amount_usd == 0.0
        assert "Explicit verified zero-charge confirmed" in r_db.reconciliation_notes

        metrics = await bm.get_spend_metrics(session_id="s9")
        assert metrics["session_spend_usd"] == 0.0


@pytest.mark.asyncio
async def test_scenario_10_no_duplicate_paid_run_after_restart(disposable_db):
    """Scenario 10: Prevention of duplicate run ID registration and safe restart reconciliation."""
    async with disposable_db() as session:
        bm = ApifyBudgetManager(db=session, api_token="test_token", session_ceiling_usd=2.00)

        res1 = await bm.create_reservation("actor_single_inst", 0.20, session_id="s10")
        await bm.mark_launch_attempted(res1.id)
        await bm.mark_run_started(res1.id, "apify_immutable_001")
        # Finalize res1
        await bm.reconcile_run(res1.id, "SUCCEEDED", actual_cost_usd=0.08)
        await session.commit()

        # Attempting to assign same apify_run_id to another reservation raises RuntimeError
        res2 = await bm.create_reservation("actor_other", 0.20, session_id="s10_other")
        with pytest.raises(RuntimeError) as exc_info:
            await bm.mark_run_started(res2.id, "apify_immutable_001")
        assert "already tracked by another reservation" in str(exc_info.value)
        # Clean up failed res2 so session is unblocked for next test step
        await bm.reconcile_run(res2.id, "FAILED", actual_cost_usd=0.0)
        await session.commit()

        # On restart with another unresolved run, recovery finalizes it cleanly
        res3 = await bm.create_reservation("actor_restart", 0.20, session_id="s10_restart")
        await bm.mark_launch_attempted(res3.id)
        await bm.mark_run_started(res3.id, "apify_restart_999")
        await session.commit()

        class MockTerminalResponse:
            status_code = 200
            def json(self):
                return {"data": {"id": "apify_restart_999", "status": "SUCCEEDED", "usageTotalUsd": 0.08}}

        class MockTerminalClient:
            async def get(self, url, headers=None): return MockTerminalResponse()

        recovered = await bm.recover_orphaned_runs(http_client=MockTerminalClient())
        await session.commit()

        assert len(recovered) == 1
        assert recovered[0]["action"] == "FINALIZED_TERMINAL"
        assert recovered[0]["actual_cost_usd"] == 0.08
