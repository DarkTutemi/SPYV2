"""
US WIN HUNTER — Remediation Procedure & Evidence Verification Test Suite
Tests:
1. Transactional remediation on disposable DB seeded with faulty legacy discovery data.
2. Verification of accurate status and evidence reclassification.
3. Strict idempotency check (0 modifications on second pass).
4. Evidence verification service: placeholder rejection, plausible ASIN rejection without receipt, verified receipt acceptance.
"""

import os
import tempfile
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.core.database import Base
from app.models.models import (
    Product,
    ProductOffer,
    BundleOffer,
    SourceRecord,
    CollectionRun,
    CollectionJobStatus,
    DataSourceType,
    ConfidenceLevel,
    EvidenceType,
    PriceEvidenceType,
    OpportunityScore,
)
from app.services.remediation import (
    remediate_legacy_discovery_data,
    AUDITED_LEGACY_PRODUCTS,
    TARGET_COLLECTION_RUN_ID,
)
from app.services.evidence_verification import (
    verify_commercial_listing_evidence,
    validate_commercial_evidence_strict,
    EvidenceVerificationOutcome,
)


@pytest_asyncio.fixture
async def disposable_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_url = f"sqlite+aiosqlite:///{path}"
    engine = create_async_engine(db_url, connect_args={"check_same_thread": False})

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()
    if os.path.exists(path):
        os.remove(path)


@pytest.mark.asyncio
async def test_remediation_transactional_and_idempotent(disposable_db: AsyncSession):
    session = disposable_db
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1. Seed faulty legacy discovery data
    c_run = CollectionRun(
        id=TARGET_COLLECTION_RUN_ID,
        job_id="job_legacy_discovery",
        status=CollectionJobStatus.COMPLETED,  # Faulty: should be PARTIAL
        records_fetched=6,
        records_new=6,
        records_updated=0,
        coverage_notes="Initial manual import",
    )
    session.add(c_run)

    for idx, (p_id, p_name) in enumerate(AUDITED_LEGACY_PRODUCTS.items()):
        # Faulty source record claiming authentic AMAZON with HIGH confidence
        srec = SourceRecord(
            id=f"manual_{p_id[:8]}",
            collection_run_id=TARGET_COLLECTION_RUN_ID,
            source_type=DataSourceType.AMAZON,  # Faulty
            external_id=f"B0XYZ{idx}",
            raw_data={"url": f"https://www.amazon.com/dp/B0XYZ{idx}"},
            geo_confidence=ConfidenceLevel.HIGH,  # Faulty
            is_synthetic=False,  # Faulty
        )
        session.add(srec)

        # Faulty product
        prod = Product(
            id=p_id,
            name=p_name,
            normalized_name=p_name.lower(),
            opportunity_status="PROMOTED",  # Faulty
            source_type=DataSourceType.AMAZON,  # Faulty
            us_relevance_confidence=ConfidenceLevel.HIGH,  # Faulty
            min_price_usd=29.99,
            max_price_usd=49.99,
        )
        session.add(prod)

        # 2 ProductOffers per product (12 total) claiming OBSERVED_RETAIL_LISTING_PRICE
        off1 = ProductOffer(
            id=f"off1_{p_id[:8]}",
            product_id=p_id,
            source_url=f"https://www.amazon.com/dp/B0XYZ{idx}",
            price_usd=29.99,
            evidence_type=EvidenceType.OBSERVED_FACT,  # Faulty
            price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE,  # Faulty
        )
        off2 = ProductOffer(
            id=f"off2_{p_id[:8]}",
            product_id=p_id,
            source_url=f"https://www.walmart.com/ip/XYZ{idx}",
            price_usd=34.99,
            evidence_type=EvidenceType.OBSERVED_FACT,  # Faulty
            price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE,  # Faulty
        )
        session.add_all([off1, off2])

        # 1 BundleOffer per product (6 total) claiming OBSERVED_RETAIL_LISTING_PRICE
        bnd = BundleOffer(
            id=f"bnd_{p_id[:8]}",
            product_id=p_id,
            source_url=f"https://www.amazon.com/dp/B0XYZ{idx}_bundle",
            quantity=2,
            bundle_price_usd=49.99,
            bundle_status="offered",  # Faulty
            evidence_type=EvidenceType.OBSERVED_FACT,  # Faulty
            price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE,  # Faulty
            is_natural_bundle=True,
        )
        session.add(bnd)

        # OpportunityScore claiming verified observation
        sc = OpportunityScore(
            id=f"sc_{p_id[:8]}",
            product_id=p_id,
            score_date=today,
            opportunity_status="PROMOTED",  # Faulty
            composite_score=85.0,  # Faulty
            evidence_confidence=80.0,  # Faulty
            observed_single_price_usd=29.99,  # Faulty
            observed_bundle_price_usd=49.99,  # Faulty
            requires_verification=False,
        )
        session.add(sc)

    await session.commit()

    # 2. First Run: Execute transactional remediation
    stats1 = await remediate_legacy_discovery_data(session)

    assert stats1["collection_runs_modified"] == 1
    assert stats1["products_modified"] == 6
    assert stats1["source_records_modified"] == 6
    assert stats1["product_offers_modified"] == 12
    assert stats1["bundle_offers_modified"] == 6
    assert stats1["scores_modified"] == 6

    # Verify remediated state
    c_run_after = await session.get(CollectionRun, TARGET_COLLECTION_RUN_ID)
    assert c_run_after.status == CollectionJobStatus.PARTIAL
    assert c_run_after.records_fetched == 0
    assert "QUARANTINED" in c_run_after.coverage_notes

    for p_id in AUDITED_LEGACY_PRODUCTS.keys():
        prod = await session.get(Product, p_id)
        assert prod.opportunity_status == "UNVERIFIED_IMPORT"
        assert prod.source_type == DataSourceType.MANUAL_IMPORT
        assert prod.us_relevance_confidence == ConfidenceLevel.UNKNOWN
        assert prod.raw_data.get("verification_status") == "QUARANTINED_UNVERIFIED"

    # 3. Second Run: Check strict idempotency (0 modifications)
    stats2 = await remediate_legacy_discovery_data(session)
    assert stats2["collection_runs_modified"] == 0
    assert stats2["products_modified"] == 0
    assert stats2["source_records_modified"] == 0
    assert stats2["product_offers_modified"] == 0
    assert stats2["bundle_offers_modified"] == 0
    assert stats2["scores_modified"] == 0


def test_evidence_verification_placeholder_rejection():
    # URL with placeholder pattern must be REJECTED
    res = verify_commercial_listing_evidence(
        url="https://www.amazon.com/dp/B0C9QWXYZ1",
        price_evidence_type="OBSERVED_RETAIL_LISTING_PRICE",
    )
    assert res.outcome == EvidenceVerificationOutcome.REJECTED
    assert not res.is_valid_observed_price
    assert "placeholder" in res.verification_notes.lower()


def test_evidence_verification_plausible_asin_without_receipt():
    # Valid-looking ASIN without authentic provider extraction receipt must return UNKNOWN
    res = verify_commercial_listing_evidence(
        url="https://www.amazon.com/dp/B07FZ8S74R",
        price_evidence_type="OBSERVED_RETAIL_LISTING_PRICE",
        source_record_id=None,
        raw_extraction=None,
    )
    assert res.outcome == EvidenceVerificationOutcome.UNKNOWN
    assert not res.is_valid_observed_price

    # Attempting to validate as OBSERVED_RETAIL_LISTING_PRICE must raise ValueError
    with pytest.raises(ValueError, match="REJECTED: Offer at"):
        validate_commercial_evidence_strict(
            url="https://www.amazon.com/dp/B07FZ8S74R",
            price_evidence_type="OBSERVED_RETAIL_LISTING_PRICE",
            raw_extraction=None,
            source_record_id=None,
        )


def test_evidence_verification_verified_receipt():
    # Listing with authentic extraction receipt and source record must return VERIFIED
    res = verify_commercial_listing_evidence(
        url="https://www.amazon.com/dp/B07FZ8S74R",
        price_evidence_type="OBSERVED_RETAIL_LISTING_PRICE",
        source_record_id="rec_amazon_ext_123",
        raw_extraction={
            "retrieval_status": "HTTP_200_EXTRACTED",
            "provider": "amazon_product_scraper",
            "retailer": "Amazon US",
            "title": "Authentic Water Filter",
            "pack_size": "2-pack",
        },
        observed_at="2026-11-11T12:00:00Z",
        observed_price=39.99,
    )
    assert res.outcome == EvidenceVerificationOutcome.VERIFIED
    assert res.is_valid_observed_price

    val = validate_commercial_evidence_strict(
        url="https://www.amazon.com/dp/B07FZ8S74R",
        price_evidence_type="OBSERVED_RETAIL_LISTING_PRICE",
        raw_extraction={
            "retrieval_status": "HTTP_200_EXTRACTED",
            "provider": "amazon_product_scraper",
        },
        source_record_id="rec_amazon_ext_123",
    )
    assert val == "OBSERVED_RETAIL_LISTING_PRICE"
