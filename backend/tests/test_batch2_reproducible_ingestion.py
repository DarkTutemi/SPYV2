"""
Regression tests proving Batch 2 multi-category OEM/DTC ingestion is reproducible,
idempotent, artifact-verified, and scores cleanly without fabricating demand or COGS.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models.models import Base  # noqa: E402
from ingest_batch2_dtc_evidence import ingest_batch2_evidence  # noqa: E402


@pytest.mark.asyncio
async def test_batch2_ingestion_reproducible_and_idempotent(tmp_path: Path):
    """
    Verify on an isolated temporary SQLite database:
    1. First run ingests all 5 Batch 2 products from manifest + disk HTML artifacts (0 -> 5).
    2. All 5 offers pass strict DB provenance verification with OEM_LIST_PRICE and In Stock.
    3. All 5 products score as PARTIALLY_VALIDATED with confidence <= 49.0 (zero ads -> UNKNOWN demand).
    4. Second run is completely idempotent: counts stay 5/5/5/5 and products_reused == 5.
    """
    db_file = tmp_path / "batch2_repro_test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_maker() as session:
            res1 = await ingest_batch2_evidence(session, score_date="2026-11-12")

        assert res1["counts_before"]["products"] == 0
        assert res1["counts_after"]["products"] == 5
        assert res1["counts_after"]["source_records"] == 5
        assert res1["counts_after"]["product_offers"] == 5
        assert res1["counts_after"]["opportunity_scores"] == 5
        assert res1["dedup_stats"]["products_created"] == 5
        assert res1["dedup_stats"]["offers_created"] == 5

        skus = {r["sku"] for r in res1["records"]}
        assert skus == {"GENIUS5", "KPHJ320", "DLC-2ABC", "GS23L", "841230028873"}

        for rec in res1["records"]:
            assert rec["verification_outcome"] == "VERIFIED"
            assert rec["price_evidence_type"] == "OEM_LIST_PRICE"
            assert rec["currency"] == "USD"
            assert rec["declared_availability"] == "In Stock"
            assert rec["opportunity_status"] == "PARTIALLY_VALIDATED"
            assert rec["opportunity_score_id"]
            assert rec["observed_single_price_usd"] == rec["price_usd"]
            assert 40.0 <= rec["evidence_confidence"] <= 49.0

        async with session_maker() as session:
            res2 = await ingest_batch2_evidence(session, score_date="2026-11-12")

        assert res2["counts_before"]["products"] == 5
        assert res2["counts_after"]["products"] == 5
        assert res2["counts_after"]["source_records"] == 5
        assert res2["counts_after"]["product_offers"] == 5
        assert res2["dedup_stats"]["products_created"] == 0
        assert res2["dedup_stats"]["products_reused"] == 5
        assert res2["dedup_stats"]["offers_created"] == 0
        assert res2["dedup_stats"]["offers_updated"] == 5
    finally:
        await engine.dispose()

