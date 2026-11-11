"""
US WIN HUNTER — Adversarial Regression Test Suite (Commit A)
Rigorous Fail-Closed Verification Against Commercial Evidence Fabrication

Tests:
Test A: Valid Amazon ASIN with invented price -> REJECTED (price mismatch).
Test B: SourceRecord ID string that does not exist in DB -> UNKNOWN / REJECTED.
Test C: SourceRecord created manually with fake HTTP_200_EXTRACTED -> REJECTED (is_synthetic or manual).
Test D: Receipt with valid URL but incorrect product identity -> REJECTED (identity mismatch).
Test E: Receipt whose observed price differs from persisted source data -> REJECTED.
Test F: Receipt whose observation timestamp was generated during import rather than obtained from source -> REJECTED.
Test G: Synthetic or manual CollectionRun masquerading as provider fetch -> REJECTED.
Test H: Invented bundle labeled as actual merchant offer -> REJECTED.
Test I: Claimed supplier quote without identifiable supplier evidence -> REJECTED.
Test J: Repeated ingestion causing duplicate products or offers -> Idempotent (0 duplicates).
"""

import os
import tempfile
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy import select, func
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
    _uuid,
    _utcnow,
)
from app.services.evidence_verification import (
    verify_commercial_evidence_db,
    validate_commercial_evidence_strict_db,
    verify_commercial_listing_evidence,
    EvidenceVerificationOutcome,
)
from app.services.remediation import (
    remediate_legacy_discovery_data,
    AUDITED_BATCH8_PRODUCTS,
    BATCH8_COLLECTION_RUN_ID,
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
async def test_a_valid_asin_with_invented_price_rejected(disposable_db):
    """Test A: Valid Amazon ASIN with invented price -> REJECTED (price mismatch)."""
    c_run = CollectionRun(
        id=f"run_external_{_uuid()[:8]}",
        job_id="job_amazon_crawler",
        status=CollectionJobStatus.COMPLETED,
        started_at=_utcnow(),
        completed_at=_utcnow(),
        coverage_notes="Authentic provider run for test",
    )
    disposable_db.add(c_run)

    # Persist authentic SourceRecord with real observed price $34.99
    srec = SourceRecord(
        id=f"srec_{_uuid()[:12]}",
        collection_run_id=c_run.id,
        source_type=DataSourceType.AMAZON,
        external_id="B07984Q864",
        geo_confidence=ConfidenceLevel.HIGH,
        is_synthetic=False,
        raw_data={
            "url": "https://www.amazon.com/dp/B07984Q864",
            "provider": "authentic_public_marketplace_capture",
            "retailer": "amazon",
            "asin": "B07984Q864",
            "observed_price": 34.99,
            "raw_http_status": 200,
            "source_timestamp": "2026-11-10T14:30:00Z",
            "capture_signature": "sha256_mock_sig_9918237",
        },
    )
    disposable_db.add(srec)
    await disposable_db.commit()

    # Attempt to claim invented price $59.99 for this ASIN
    result = await verify_commercial_evidence_db(
        db=disposable_db,
        url="https://www.amazon.com/dp/B07984Q864",
        price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
        source_record_id=srec.id,
        expected_asin="B07984Q864",
        observed_price=59.99,  # Invented price!
    )
    assert result.outcome == EvidenceVerificationOutcome.REJECTED
    assert "Price mismatch" in result.verification_notes
    assert "$59.99" in result.verification_notes
    assert "$34.99" in result.verification_notes

    # Strict validation MUST raise ValueError
    with pytest.raises(ValueError, match="Price mismatch"):
        await validate_commercial_evidence_strict_db(
            db=disposable_db,
            url="https://www.amazon.com/dp/B07984Q864",
            price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
            source_record_id=srec.id,
            expected_asin="B07984Q864",
            observed_price=59.99,
        )


@pytest.mark.asyncio
async def test_b_nonexistent_source_record_id_rejected(disposable_db):
    """Test B: SourceRecord ID string that does not exist in DB -> UNKNOWN / REJECTED."""
    ghost_id = "srec_ghost_nonexistent_99999"

    result = await verify_commercial_evidence_db(
        db=disposable_db,
        url="https://www.amazon.com/dp/B08N5WRWNW",
        price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
        source_record_id=ghost_id,
        expected_asin="B08N5WRWNW",
        observed_price=29.99,
    )
    assert result.outcome == EvidenceVerificationOutcome.UNKNOWN
    assert "does not exist in the database" in result.verification_notes

    with pytest.raises(ValueError, match="does not exist in the database"):
        await validate_commercial_evidence_strict_db(
            db=disposable_db,
            url="https://www.amazon.com/dp/B08N5WRWNW",
            price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
            source_record_id=ghost_id,
            expected_asin="B08N5WRWNW",
            observed_price=29.99,
        )


@pytest.mark.asyncio
async def test_c_source_record_with_fake_receipt_rejected(disposable_db):
    """Test C: SourceRecord created manually with fake HTTP_200_EXTRACTED -> REJECTED (is_synthetic or manual)."""
    c_run = CollectionRun(
        id=f"run_synthetic_{_uuid()[:8]}",
        job_id="job_manual_script",
        status=CollectionJobStatus.COMPLETED,
        started_at=_utcnow(),
        completed_at=_utcnow(),
        coverage_notes="Manual script run",
    )
    disposable_db.add(c_run)

    srec = SourceRecord(
        id=f"srec_fake_{_uuid()[:8]}",
        collection_run_id=c_run.id,
        source_type=DataSourceType.MANUAL_IMPORT,
        external_id="B08ABC1234",
        geo_confidence=ConfidenceLevel.UNKNOWN,
        is_synthetic=True,
        raw_data={
            "url": "https://www.amazon.com/dp/B08ABC1234",
            "retrieval_status": "HTTP_200_EXTRACTED",
            "verified_source": True,
            "provider": "amazon_scraper",
            "observed_price": 49.99,
            "source_timestamp": "import_time_now",
        },
    )
    disposable_db.add(srec)
    await disposable_db.commit()

    result = await verify_commercial_evidence_db(
        db=disposable_db,
        url="https://www.amazon.com/dp/B08ABC1234",
        price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
        source_record_id=srec.id,
        expected_asin="B08ABC1234",
        observed_price=49.99,
    )
    assert result.outcome == EvidenceVerificationOutcome.REJECTED
    assert "synthetic" in result.verification_notes or "MANUAL_IMPORT" in result.verification_notes


@pytest.mark.asyncio
async def test_d_receipt_with_product_identity_mismatch_rejected(disposable_db):
    """Test D: Receipt with valid URL but incorrect product identity -> REJECTED (identity mismatch)."""
    c_run = CollectionRun(
        id=f"run_external_{_uuid()[:8]}",
        job_id="job_amazon_crawler",
        status=CollectionJobStatus.COMPLETED,
        started_at=_utcnow(),
        completed_at=_utcnow(),
        coverage_notes="Authentic provider run for test",
    )
    disposable_db.add(c_run)

    srec = SourceRecord(
        id=f"srec_{_uuid()[:12]}",
        collection_run_id=c_run.id,
        source_type=DataSourceType.AMAZON,
        external_id="B08N5WRWNW",  # Actual source ASIN
        geo_confidence=ConfidenceLevel.HIGH,
        is_synthetic=False,
        raw_data={
            "url": "https://www.amazon.com/dp/B08N5WRWNW",
            "provider": "authentic_public_marketplace_capture",
            "retailer": "amazon",
            "asin": "B08N5WRWNW",
            "observed_price": 29.99,
            "raw_http_status": 200,
            "source_timestamp": "2026-11-10T14:30:00Z",
            "capture_signature": "sha256_mock_sig_1234",
        },
    )
    disposable_db.add(srec)
    await disposable_db.commit()

    # Offer claims expected ASIN is B001EJMS6K
    result = await verify_commercial_evidence_db(
        db=disposable_db,
        url="https://www.amazon.com/dp/B08N5WRWNW",
        price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
        source_record_id=srec.id,
        expected_asin="B001EJMS6K",  # Mismatched!
        observed_price=29.99,
    )
    assert result.outcome == EvidenceVerificationOutcome.REJECTED
    assert "Product identity mismatch" in result.verification_notes


@pytest.mark.asyncio
async def test_e_receipt_with_differing_price_rejected(disposable_db):
    """Test E: Receipt whose observed price differs from persisted source data -> REJECTED."""
    c_run = CollectionRun(
        id=f"run_external_{_uuid()[:8]}",
        job_id="job_amazon_crawler",
        status=CollectionJobStatus.COMPLETED,
        started_at=_utcnow(),
        completed_at=_utcnow(),
        coverage_notes="Authentic provider run for test",
    )
    disposable_db.add(c_run)

    srec = SourceRecord(
        id=f"srec_{_uuid()[:12]}",
        collection_run_id=c_run.id,
        source_type=DataSourceType.AMAZON,
        external_id="B07984Q864",
        geo_confidence=ConfidenceLevel.HIGH,
        is_synthetic=False,
        raw_data={
            "url": "https://www.amazon.com/dp/B07984Q864",
            "provider": "authentic_public_marketplace_capture",
            "retailer": "amazon",
            "asin": "B07984Q864",
            "observed_price": 24.50,
            "raw_http_status": 200,
            "source_timestamp": "2026-11-10T14:30:00Z",
            "capture_signature": "sha256_mock_sig_5544",
        },
    )
    disposable_db.add(srec)
    await disposable_db.commit()

    # Offer claims $34.50 ($10 difference)
    result = await verify_commercial_evidence_db(
        db=disposable_db,
        url="https://www.amazon.com/dp/B07984Q864",
        price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
        source_record_id=srec.id,
        expected_asin="B07984Q864",
        observed_price=34.50,
    )
    assert result.outcome == EvidenceVerificationOutcome.REJECTED
    assert "Price mismatch" in result.verification_notes


@pytest.mark.asyncio
async def test_f_observation_timestamp_generated_during_import_rejected(disposable_db):
    """Test F: Receipt whose observation timestamp was generated during import rather than obtained from source -> REJECTED."""
    c_run = CollectionRun(
        id=f"run_external_{_uuid()[:8]}",
        job_id="job_amazon_crawler",
        status=CollectionJobStatus.COMPLETED,
        started_at=_utcnow(),
        completed_at=_utcnow(),
        coverage_notes="Authentic provider run for test",
    )
    disposable_db.add(c_run)

    srec = SourceRecord(
        id=f"srec_{_uuid()[:12]}",
        collection_run_id=c_run.id,
        source_type=DataSourceType.AMAZON,
        external_id="B07984Q864",
        geo_confidence=ConfidenceLevel.HIGH,
        is_synthetic=False,
        raw_data={
            "url": "https://www.amazon.com/dp/B07984Q864",
            "provider": "authentic_public_marketplace_capture",
            "retailer": "amazon",
            "asin": "B07984Q864",
            "observed_price": 24.50,
            "raw_http_status": 200,
            "source_timestamp": "import_time_20261111_120000",  # Generated during import!
            "capture_signature": "sha256_mock_sig_5544",
        },
    )
    disposable_db.add(srec)
    await disposable_db.commit()

    result = await verify_commercial_evidence_db(
        db=disposable_db,
        url="https://www.amazon.com/dp/B07984Q864",
        price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
        source_record_id=srec.id,
        expected_asin="B07984Q864",
        observed_price=24.50,
    )
    assert result.outcome == EvidenceVerificationOutcome.REJECTED
    assert "generated during import" in result.verification_notes


@pytest.mark.asyncio
async def test_g_synthetic_collection_run_masquerading_rejected(disposable_db):
    """Test G: Synthetic or manual CollectionRun masquerading as provider fetch -> REJECTED."""
    c_run = CollectionRun(
        id="run_us_verified_discovery_20261111",
        job_id="job_script_import",
        status=CollectionJobStatus.COMPLETED,
        started_at=_utcnow(),
        completed_at=_utcnow(),
        coverage_notes="QUARANTINED: Manual research import with self-generated receipts",
    )
    disposable_db.add(c_run)

    srec = SourceRecord(
        id=f"srec_{_uuid()[:12]}",
        collection_run_id=c_run.id,
        source_type=DataSourceType.AMAZON,
        external_id="B07984Q864",
        geo_confidence=ConfidenceLevel.HIGH,
        is_synthetic=False,
        raw_data={
            "url": "https://www.amazon.com/dp/B07984Q864",
            "provider": "authentic_public_marketplace_capture",
            "retailer": "amazon",
            "asin": "B07984Q864",
            "observed_price": 24.50,
            "source_timestamp": "2026-11-10T14:30:00Z",
            "capture_signature": "sha256_sig",
        },
    )
    disposable_db.add(srec)
    await disposable_db.commit()

    result = await verify_commercial_evidence_db(
        db=disposable_db,
        url="https://www.amazon.com/dp/B07984Q864",
        price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
        source_record_id=srec.id,
        expected_asin="B07984Q864",
        observed_price=24.50,
    )
    assert result.outcome == EvidenceVerificationOutcome.REJECTED
    assert "manual research import" in result.verification_notes


@pytest.mark.asyncio
async def test_h_invented_bundle_labeled_as_merchant_offer_rejected(disposable_db):
    """Test H: Invented bundle labeled as actual merchant offer -> REJECTED."""
    invented_bundle_url = "https://www.amazon.com/bundle/clean_water_pack_combo"

    # Synchronous check without source_record_id cannot be VERIFIED
    result = verify_commercial_listing_evidence(
        url=invented_bundle_url,
        price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
        source_record_id=None,
    )
    assert result.outcome != EvidenceVerificationOutcome.VERIFIED

    # In DB check: bundle without authentic SourceRecord is rejected from being OBSERVED_RETAIL_LISTING_PRICE
    with pytest.raises(ValueError, match="lacks authentic provider extraction receipt"):
        await validate_commercial_evidence_strict_db(
            db=disposable_db,
            url=invented_bundle_url,
            price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
            source_record_id=None,
        )


@pytest.mark.asyncio
async def test_i_claimed_supplier_quote_without_evidence_rejected(disposable_db):
    """Test I: Claimed supplier quote without identifiable supplier evidence -> REJECTED."""
    placeholder_supplier_url = "https://www.alibaba.com/product-detail/placeholder_supplier_quote_123.html"

    # Must be rejected due to placeholder pattern
    with pytest.raises(ValueError, match="REJECTED: URL .* contains unverified placeholder pattern"):
        await validate_commercial_evidence_strict_db(
            db=disposable_db,
            url=placeholder_supplier_url,
            price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
            source_record_id="srec_supplier_fake",
        )


@pytest.mark.asyncio
async def test_j_repeated_remediation_idempotency_zero_duplicates(disposable_db):
    """Test J: Repeated ingestion/remediation causing duplicate products or offers -> Idempotent (0 duplicates)."""
    # Seed disposable DB with Batch 8 records
    c_run = CollectionRun(
        id=BATCH8_COLLECTION_RUN_ID,
        job_id="job_batch8_crawler",
        status=CollectionJobStatus.COMPLETED,
        started_at=_utcnow(),
        completed_at=_utcnow(),
        coverage_notes="Batch 8 run",
    )
    disposable_db.add(c_run)

    for p_id, p_name in AUDITED_BATCH8_PRODUCTS.items():
        prod = Product(
            id=p_id,
            name=p_name,
            source_type=DataSourceType.AMAZON,
            opportunity_status="ACTIVE_DISCOVERY",
            raw_data={"verification_status": "CLAIMED_VERIFIED"},
        )
        disposable_db.add(prod)

        offer = ProductOffer(
            id=f"off_{p_id[:8]}",
            product_id=p_id,
            price_usd=29.99,
            price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
            evidence_type=EvidenceType.OBSERVED_FACT.value,
            source_url=f"https://www.amazon.com/dp/B07FZ8S74R",
        )
        disposable_db.add(offer)

    await disposable_db.commit()

    # Pass 1 of remediation
    stats1 = await remediate_legacy_discovery_data(disposable_db)
    assert stats1["collection_runs_modified"] >= 1
    assert stats1["products_modified"] >= 6
    assert stats1["product_offers_modified"] >= 6

    # Pass 2 of remediation (MUST BE STRICTLY 0 MODIFICATIONS)
    stats2 = await remediate_legacy_discovery_data(disposable_db)
    assert stats2["collection_runs_modified"] == 0
    assert stats2["source_records_modified"] == 0
    assert stats2["products_modified"] == 0
    assert stats2["product_offers_modified"] == 0
    assert stats2["bundle_offers_modified"] == 0
    assert stats2["scores_modified"] == 0

    # Ensure count of products in DB did not change or duplicate
    prod_count = (await disposable_db.execute(select(func.count(Product.id)))).scalar()
    assert prod_count == 6
