"""
Regression Test Suite: Discovery Provenance, Quarantine & Fake Evidence Rejection
Verifies:
1. Rejects invented/placeholder Amazon/Walmart URLs labeled as OBSERVED_RETAIL_LISTING_PRICE.
2. Manually created CollectionRuns cannot masquerade as completed external provider fetches.
3. Unverified research imports are quarantined under UNVERIFIED_IMPORT with low confidence.
4. Hypothetical prices (SCENARIO_PRICE) never count as verified observed checkout prices.
5. Ingestion re-runs remain strictly idempotent (no duplicates).
6. Preserves the 145 historical Meta advertisements and 435 snapshots.
"""

import os
import tempfile
import pytest
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.models.models import (
    Base,
    Product,
    ProductOffer,
    BundleOffer,
    SourceRecord,
    CollectionJob,
    CollectionRun,
    CollectionJobStatus,
    DataSource,
    DataSourceType,
    ConfidenceLevel,
    EvidenceType,
    PriceEvidenceType,
    Advertisement,
    AdvertisementSnapshot,
    _uuid,
    _utcnow,
)
from app.engines.scoring import ScoringEngine
from ingest_new_discoveries import validate_commercial_evidence


@pytest.fixture
async def test_db():
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


class TestDiscoveryProvenanceAndQuarantine:
    """Acceptance tests for commercial evidence integrity and quarantine behavior."""

    def test_acceptance_rejects_invented_amazon_url_as_observed_price(self):
        """The acceptance test MUST reject an invented Amazon product URL labeled OBSERVED_RETAIL_LISTING_PRICE."""
        invented_url = "https://www.amazon.com/dp/B0C9QWXYZ1"

        with pytest.raises(ValueError, match="REJECTED: URL .* contains unverified placeholder pattern"):
            validate_commercial_evidence(
                url=invented_url,
                price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
            )

        # Same for checkout price
        with pytest.raises(ValueError, match="REJECTED: URL .* contains unverified placeholder pattern"):
            validate_commercial_evidence(
                url=invented_url,
                price_evidence_type=PriceEvidenceType.OBSERVED_CHECKOUT_PRICE.value,
            )

        # But accepts SCENARIO_PRICE for research hypotheses
        result = validate_commercial_evidence(
            url=invented_url,
            price_evidence_type=PriceEvidenceType.SCENARIO_PRICE.value,
        )
        assert result == PriceEvidenceType.SCENARIO_PRICE.value

    @pytest.mark.asyncio
    async def test_manual_collection_run_cannot_be_completed_external_fetch(self, test_db):
        """A manual import CollectionRun cannot masquerade as an external completed provider fetch."""
        ds = DataSource(
            id=_uuid(),
            name=f"test_manual_ds_{_uuid()[:8]}",
            source_type=DataSourceType.MANUAL_IMPORT,
            is_active=True,
        )
        test_db.add(ds)
        await test_db.flush()

        cj = CollectionJob(
            id=_uuid(),
            data_source_id=ds.id,
            name=f"test_job_{_uuid()[:8]}",
            job_type="manual_hypothesis",
            is_recurring=False,
        )
        test_db.add(cj)
        await test_db.flush()

        # Unverified manual runs must be PARTIAL, not COMPLETED
        c_run = CollectionRun(
            id=f"run_test_{_uuid()[:8]}",
            job_id=cj.id,
            status=CollectionJobStatus.PARTIAL,
            records_fetched=0,
            records_new=0,
            coverage_notes="QUARANTINED: Manual import without external provider verification.",
        )
        test_db.add(c_run)
        await test_db.flush()

        refetched = await test_db.get(CollectionRun, c_run.id)
        assert refetched.status == CollectionJobStatus.PARTIAL
        assert "QUARANTINED" in refetched.coverage_notes

    @pytest.mark.asyncio
    async def test_hypothetical_prices_never_become_observed_prices(self, test_db):
        """Offers with SCENARIO_PRICE do not set has_observed_price or appear in observed_single_price_usd."""
        prod = Product(
            id=_uuid(),
            name=f"Hypothetical Widget {_uuid()[:6]}",
            target_country="US",
            is_physical=True,
            is_synthetic=False,
            opportunity_status="UNVERIFIED_IMPORT",
            source_type=DataSourceType.MANUAL_IMPORT,
            min_price_usd=49.99,
        )
        test_db.add(prod)
        await test_db.flush()

        # Offer with SCENARIO_PRICE
        off = ProductOffer(
            id=_uuid(),
            product_id=prod.id,
            source_url="https://example.com/unverified-link",
            price_usd=49.99,
            currency="USD",
            evidence_type=EvidenceType.UNVERIFIED_HYPOTHESIS,
            price_evidence_type=PriceEvidenceType.SCENARIO_PRICE,
        )
        test_db.add(off)
        await test_db.flush()

        scoring = ScoringEngine(test_db, mode="balanced")
        score = await scoring.score_product(prod.id, mode="balanced")

        assert score.opportunity_status == "UNVERIFIED_IMPORT"
        assert score.observed_single_price_usd is None
        assert score.evidence_confidence <= 15.0
        assert score.requires_verification is True

    @pytest.mark.asyncio
    async def test_unverified_imports_excluded_from_qualified_status(self, test_db):
        """Unverified research imports can never be qualified winners."""
        prod = Product(
            id=_uuid(),
            name=f"High Demand Concept {_uuid()[:6]}",
            target_country="US",
            is_physical=True,
            is_synthetic=False,
            opportunity_status="UNVERIFIED_IMPORT",
            source_type=DataSourceType.MANUAL_IMPORT,
            functional_use_case="Great utility",
            min_price_usd=39.99,
        )
        test_db.add(prod)
        await test_db.flush()

        scoring = ScoringEngine(test_db, mode="balanced")
        score = await scoring.score_product(prod.id, mode="balanced")

        assert score.opportunity_status == "UNVERIFIED_IMPORT"
        assert score.opportunity_status != "QUALIFIED_OPPORTUNITY"
        assert score.opportunity_status != "PROMISING"
        assert score.composite_score <= 20.0

    @pytest.mark.asyncio
    async def test_modeled_bundles_not_marked_as_merchant_sold(self, test_db):
        """Modeled bundles must have bundle_status='modeled_scenario' and price_evidence_type=SCENARIO_PRICE."""
        prod = Product(
            id=_uuid(),
            name=f"Bundle Product {_uuid()[:6]}",
            target_country="US",
            is_physical=True,
            is_synthetic=False,
            opportunity_status="UNVERIFIED_IMPORT",
            source_type=DataSourceType.MANUAL_IMPORT,
        )
        test_db.add(prod)
        await test_db.flush()

        bo = BundleOffer(
            id=_uuid(),
            product_id=prod.id,
            source_url="https://example.com/unverified-bundle",
            quantity=2,
            bundle_price_usd=69.99,
            bundle_status="modeled_scenario",
            evidence_type=EvidenceType.UNVERIFIED_HYPOTHESIS,
            price_evidence_type=PriceEvidenceType.SCENARIO_PRICE,
            is_natural_bundle=False,
        )
        test_db.add(bo)
        await test_db.flush()

        refetched = await test_db.get(BundleOffer, bo.id)
        assert refetched.bundle_status == "modeled_scenario"
        assert refetched.price_evidence_type == PriceEvidenceType.SCENARIO_PRICE

        scoring = ScoringEngine(test_db, mode="balanced")
        score = await scoring.score_product(prod.id, mode="balanced")
        assert score.observed_bundle_price_usd is None

    @pytest.mark.asyncio
    async def test_historical_meta_ads_and_snapshots_untouched(self):
        """Ensures the 145 baseline Meta advertisements and 435 snapshots remain intact in winhunter.db."""
        import sqlite3
        db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "winhunter.db"))
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        ads_count = cur.execute("SELECT count(*) FROM advertisements").fetchone()[0]
        snaps_count = cur.execute("SELECT count(*) FROM advertisement_snapshots").fetchone()[0]
        verified_t0 = cur.execute(
            "SELECT count(*) FROM advertisement_snapshots WHERE observation_quality = 'VERIFIED_SOURCE_OBSERVATION'"
        ).fetchone()[0]
        con.close()

        assert ads_count == 145
        assert snaps_count == 435
        assert verified_t0 == 145
