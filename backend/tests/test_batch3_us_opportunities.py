"""
Regression tests verifying Batch 3 US dropshipping opportunities ingestion is reproducible,
idempotent, manifest-verified, and keeps demand/COGS unknowns honest.
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
from ingest_batch3_us_opportunities import ingest_batch3_opportunities  # noqa: E402


@pytest.mark.asyncio
async def test_batch3_us_opportunities_reproducible_and_idempotent(tmp_path: Path):
    db_file = tmp_path / "batch3_repro_test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_maker() as session:
            res1 = await ingest_batch3_opportunities(session, score_date="2026-11-12")

        assert res1["counts_after"]["products"] == 3
        assert res1["counts_after"]["source_records"] == 7
        assert res1["counts_after"]["product_offers"] == 3
        assert res1["counts_after"]["opportunity_scores"] == 3
        assert res1["dedup_stats"]["products_created"] == 3

        for rec in res1["records"]:
            assert rec["verification_outcome"] == "VERIFIED"
            assert rec["opportunity_status"] == "PARTIALLY_VALIDATED"
            assert rec["opportunity_score_id"]
            assert rec["evidence_confidence"] <= 49.0

        async with session_maker() as session:
            res2 = await ingest_batch3_opportunities(session, score_date="2026-11-12")

        assert res2["counts_after"]["products"] == 3
        assert res2["counts_after"]["source_records"] == 7
        assert res2["dedup_stats"]["products_created"] == 0
        assert res2["dedup_stats"]["products_reused"] == 3
    finally:
        await engine.dispose()
