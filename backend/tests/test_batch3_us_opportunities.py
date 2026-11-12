"""
Regression tests verifying Batch 3 commercial validation & competitor pricing semantics:
1. Ingestion is reproducible, idempotent, and passes inspect_artifact_content + DB provenance gate.
2. Competitor retail prices (RuffRover $159.95, Aquasana $99.99, AquaBliss $64.99, Weddell $79.99,
   Fanttik $49.99) and corded category benchmarks (XPOWER A-2 $65.00) NEVER populate
   OpportunityScore.observed_single_price_usd as the generic candidate's own price.
3. Equivalent sourcing 1-unit OEM storefront listings (HonkCare 29347 $51.99) stay isolated from
   corded benchmarks, B2B FOB quotes, landed costs, and customer AOV.
4. Standalone ScoringEngine isolation guard ensures any offer tagged is_competitor_benchmark=True
   never leaks into candidate observed_single_price_usd.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.engines.scoring import ScoringEngine  # noqa: E402
from app.models.models import (  # noqa: E402
    Base,
    CollectionJobStatus,
    CollectionRun,
    ConfidenceLevel,
    DataSourceType,
    EvidenceType,
    OpportunityScore,
    PriceEvidenceType,
    Product,
    ProductOffer,
    SourceRecord,
    _utcnow,
)
from app.services.evidence_verification import generate_capture_signature  # noqa: E402
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
        assert res1["counts_after"]["source_records"] == 16
        assert res1["counts_after"]["product_offers"] == 7
        assert res1["counts_after"]["opportunity_scores"] == 3
        assert res1["dedup_stats"]["products_created"] == 3
        assert res1["dedup_stats"]["offers_created"] == 7

        by_name = {rec["name"]: rec for rec in res1["records"]}

        # 1. Dog Car Seat Extender: RuffRover $159.95 is competitor benchmark -> obs_single MUST be None
        ext = by_name["Hard-Bottom Waterproof Dog Car Seat Extender"]
        assert ext["observed_single_price_usd"] is None
        assert ext["customer_aov_usd"] is None
        assert ext["pricing_evidence_component"]["is_competitor_benchmark_only"] is True
        assert ext["pricing_evidence_component"]["observed_competitor_price_usd"] == pytest.approx(159.95)
        assert ext["pricing_evidence_component"]["raw"] == 45.0

        # 2. Filtered Showerhead: Aquasana/AquaBliss/Weddell are competitor benchmarks -> obs_single MUST be None
        shower = by_name["Multi-Stage High-Pressure Filtered Showerhead (+ Quarterly Refill System)"]
        assert shower["observed_single_price_usd"] is None
        assert shower["customer_aov_usd"] is None
        assert len(shower["offers"]) == 3
        assert all(o["is_competitor_benchmark"] for o in shower["offers"])
        assert shower["pricing_evidence_component"]["is_competitor_benchmark_only"] is True

        # 3. Electric Air Duster: corded XPOWER ($65) excluded; HonkCare Jet Fan 29347 ($51.99) is equivalent OEM-direct
        duster = by_name["Brushless High-Speed Electric Air Duster (Canned Air Replacement)"]
        assert duster["observed_single_price_usd"] == pytest.approx(51.99)
        assert duster["customer_aov_usd"] is None
        duster_roles = {o["sku"]: o["offer_role"] for o in duster["offers"]}
        assert duster_roles["A-2"] == "category_benchmark_corded"
        assert duster_roles["fanttik-b10-pro"] == "competitor_retail_benchmark"
        assert duster_roles["29347"] == "equivalent_sourcing_retail_listing"

        for rec in res1["records"]:
            assert rec["verification_outcome"] == "VERIFIED"
            assert rec["opportunity_status"] == "PARTIALLY_VALIDATED"
            assert rec["opportunity_score_id"]
            assert rec["evidence_confidence"] <= 49.0

        async with session_maker() as session:
            res2 = await ingest_batch3_opportunities(session, score_date="2026-11-12")

        assert res2["counts_after"]["products"] == 3
        assert res2["counts_after"]["source_records"] == 16
        assert res2["counts_after"]["product_offers"] == 7
        assert res2["dedup_stats"]["products_created"] == 0
        assert res2["dedup_stats"]["products_reused"] == 3
        assert res2["dedup_stats"]["offers_created"] == 0
        assert res2["dedup_stats"]["offers_updated"] == 7
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_scoring_isolates_competitor_benchmark_from_candidate_price(tmp_path: Path):
    """
    A manual-origin candidate holding ONLY a verified competitor benchmark offer must never
    populate OpportunityScore.observed_single_price_usd or pretend it is a candidate price.
    """
    db_file = tmp_path / "competitor_isolation_test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_maker() as session:
            ts = "2026-11-12T06:46:19.913688+00:00"
            run_id = "run_test_comp_isolation"
            session.add(
                CollectionRun(
                    id=run_id,
                    job_id="job_test_comp_isolation",
                    status=CollectionJobStatus.COMPLETED,
                    started_at=_utcnow(),
                    completed_at=_utcnow(),
                )
            )
            sig = generate_capture_signature(run_id, "48906329850134", 159.95, ts)
            session.add(
                SourceRecord(
                    id="srec_comp_iso_1",
                    collection_run_id=run_id,
                    source_type=DataSourceType.OTHER,
                    external_id="48906329850134",
                    raw_data={
                        "provider": "authorized_http_collector",
                        "retailer": "ruffrover_dtc",
                        "url": "https://ruffrover.com/",
                        "source_url": "https://ruffrover.com/",
                        "external_id": "48906329850134",
                        "product_identity": "48906329850134",
                        "observed_price": 159.95,
                        "currency": "USD",
                        "source_timestamp": ts,
                        "artifact_path": "docs/run_reports/artifacts/capture_48906329850134_ruffrover_dtc.html",
                        "artifact_sha256": "5e33d2f8c2ab7ff9d2450946f1f05b920d914e3a9a94d2461ad1744907c37b1d",
                        "capture_signature": sig,
                    },
                    geographic_context="US",
                    geo_confidence=ConfidenceLevel.HIGH,
                    is_processed=True,
                )
            )
            prod = Product(
                id="prod_comp_iso_1",
                name="Generic Hard-Bottom Dog Seat Extender",
                normalized_name="generic hard-bottom dog seat extender",
                category="Pet Travel",
                source_url="https://ruffrover.com/",
                min_price_usd=159.95,  # deliberate dirty legacy min_price that scoring must ignore
                max_price_usd=159.95,
                target_country="US",
                is_physical=True,
                is_synthetic=False,
                source_type=DataSourceType.MANUAL_IMPORT,
                raw_data={"proposed_selling_price_usd": "$79.99 USD target"},
            )
            session.add(prod)
            session.add(
                ProductOffer(
                    id="off_comp_iso_1",
                    product_id="prod_comp_iso_1",
                    source_url="https://ruffrover.com/",
                    price_usd=159.95,
                    currency="USD",
                    quantity=1,
                    is_bundle=False,
                    observed_at=_utcnow(),
                    evidence_type=EvidenceType.DTC_MANUFACTURER_OBSERVED_PRICE,
                    price_evidence_type=PriceEvidenceType.DTC_MANUFACTURER_OBSERVED_PRICE,
                    raw_data={
                        "source_record_id": "srec_comp_iso_1",
                        "collection_run_id": run_id,
                        "capture_signature": sig,
                        "retailer": "ruffrover_dtc",
                        "offer_role": "competitor_retail_benchmark",
                        "is_competitor_benchmark": True,
                    },
                )
            )
            await session.commit()

            scorer = ScoringEngine(session, mode="balanced")
            await scorer.score_product_balanced("prod_comp_iso_1", score_date="2026-11-12")
            await session.commit()

            score = (
                await session.execute(
                    select(OpportunityScore).where(OpportunityScore.product_id == "prod_comp_iso_1")
                )
            ).scalar_one()

            assert score.observed_single_price_usd is None
            assert score.customer_aov_usd is None
            assert score.opportunity_status == "PARTIALLY_VALIDATED"
            assert score.evidence_confidence <= 49.0
            assert score.confidence_components["pricing_evidence"]["is_competitor_benchmark_only"] is True
            assert score.confidence_components["pricing_evidence"]["observed_price_usd"] is None
            assert score.confidence_components["pricing_evidence"]["observed_competitor_price_usd"] == pytest.approx(159.95)
            assert "Proposed target selling price" in score.what_evidence_supports_it
            assert "competitor" in score.what_evidence_supports_it.lower()
            assert "equivalent sourcing" in score.what_remains_unknown.lower()
    finally:
        await engine.dispose()
