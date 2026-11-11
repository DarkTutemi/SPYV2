"""
US WIN HUNTER — Evidence Lockdown & Anti-Bypass Test Suite
Tests all 10 adversarial/tampering scenarios for commercial evidence verification.

Scenarios:
1. Scenario 1: No capture signature and no verified_source flag -> REJECTED.
2. Scenario 2: Arbitrary fabricated capture_signature string -> REJECTED.
3. Scenario 3: Fake external_run_id -> REJECTED.
4. Scenario 4: Offer URL differs from captured item URL -> REJECTED.
5. Scenario 5: Price missing from source -> REJECTED.
6. Scenario 6: Malformed source price -> REJECTED.
7. Scenario 7: Claimed price differs from source price -> REJECTED.
8. Scenario 8: Reused capture evidence for different ASIN -> REJECTED.
9. Scenario 9: Source timestamp created manually during import -> REJECTED.
10. Scenario 10: Legacy script attempting to re-verify quarantined products -> RuntimeError.
11. Scenario 11 (Positive Control): Authentic record with canonical signature -> VERIFIED.
"""

import os
import tempfile
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy import select
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
    generate_capture_signature,
    EvidenceVerificationOutcome,
)
from app.services.remediation import (
    remediate_legacy_discovery_data,
    AUDITED_BATCH8_PRODUCTS,
    BATCH8_COLLECTION_RUN_ID,
)
import ingest_verified_us_products


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
async def test_scenario_1_no_capture_signature_and_no_verified_source_rejected(disposable_db):
    """Scenario 1: No capture signature and no verified_source flag -> REJECTED."""
    c_run = CollectionRun(
        id=f"run_valid_{_uuid()[:8]}",
        job_id="job_real_crawler",
        status=CollectionJobStatus.COMPLETED,
        started_at=_utcnow(),
        completed_at=_utcnow(),
    )
    disposable_db.add(c_run)

    srec = SourceRecord(
        id=f"srec_{_uuid()[:12]}",
        collection_run_id=c_run.id,
        source_type=DataSourceType.AMAZON,
        external_id="B08N5WRWNW",
        geo_confidence=ConfidenceLevel.HIGH,
        is_synthetic=False,
        raw_data={
            "url": "https://www.amazon.com/dp/B08N5WRWNW",
            "provider": "authentic_public_marketplace_capture",
            "retailer": "amazon",
            "asin": "B08N5WRWNW",
            "observed_price": 29.99,
            "source_timestamp": "2026-11-10T14:30:00Z",
            # No capture_signature and no verified_source flag!
        },
    )
    disposable_db.add(srec)
    await disposable_db.commit()

    result = await verify_commercial_evidence_db(
        db=disposable_db,
        url="https://www.amazon.com/dp/B08N5WRWNW",
        price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
        source_record_id=srec.id,
        expected_asin="B08N5WRWNW",
        observed_price=29.99,
    )
    assert result.outcome == EvidenceVerificationOutcome.REJECTED
    assert "lacks verifiable capture signature" in result.verification_notes


@pytest.mark.asyncio
async def test_scenario_2_arbitrary_fabricated_capture_signature_rejected(disposable_db):
    """Scenario 2: Arbitrary fabricated capture_signature string -> REJECTED."""
    c_run = CollectionRun(
        id=f"run_valid_{_uuid()[:8]}",
        job_id="job_real_crawler",
        status=CollectionJobStatus.COMPLETED,
        started_at=_utcnow(),
        completed_at=_utcnow(),
    )
    disposable_db.add(c_run)

    srec = SourceRecord(
        id=f"srec_{_uuid()[:12]}",
        collection_run_id=c_run.id,
        source_type=DataSourceType.AMAZON,
        external_id="B08N5WRWNW",
        geo_confidence=ConfidenceLevel.HIGH,
        is_synthetic=False,
        raw_data={
            "url": "https://www.amazon.com/dp/B08N5WRWNW",
            "provider": "authentic_public_marketplace_capture",
            "retailer": "amazon",
            "asin": "B08N5WRWNW",
            "observed_price": 29.99,
            "source_timestamp": "2026-11-10T14:30:00Z",
            "capture_signature": "arbitrary_fabricated_signature_123456",  # Arbitrary string!
        },
    )
    disposable_db.add(srec)
    await disposable_db.commit()

    result = await verify_commercial_evidence_db(
        db=disposable_db,
        url="https://www.amazon.com/dp/B08N5WRWNW",
        price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
        source_record_id=srec.id,
        expected_asin="B08N5WRWNW",
        observed_price=29.99,
    )
    assert result.outcome == EvidenceVerificationOutcome.REJECTED
    assert "arbitrary or fabricated" in result.verification_notes


@pytest.mark.asyncio
async def test_scenario_3_fake_external_run_id_rejected(disposable_db):
    """Scenario 3: Fake external_run_id -> REJECTED."""
    c_run = CollectionRun(
        id=f"run_valid_{_uuid()[:8]}",
        job_id="job_real_crawler",
        status=CollectionJobStatus.COMPLETED,
        started_at=_utcnow(),
        completed_at=_utcnow(),
    )
    disposable_db.add(c_run)

    srec = SourceRecord(
        id=f"srec_{_uuid()[:12]}",
        collection_run_id=c_run.id,
        source_type=DataSourceType.AMAZON,
        external_id="B08N5WRWNW",
        geo_confidence=ConfidenceLevel.HIGH,
        is_synthetic=False,
        raw_data={
            "url": "https://www.amazon.com/dp/B08N5WRWNW",
            "provider": "authentic_public_marketplace_capture",
            "retailer": "amazon",
            "asin": "B08N5WRWNW",
            "observed_price": 29.99,
            "source_timestamp": "2026-11-10T14:30:00Z",
            "external_run_id": "fake_apify_run_id_99999",  # Fake external run ID!
        },
    )
    disposable_db.add(srec)
    await disposable_db.commit()

    result = await verify_commercial_evidence_db(
        db=disposable_db,
        url="https://www.amazon.com/dp/B08N5WRWNW",
        price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
        source_record_id=srec.id,
        expected_asin="B08N5WRWNW",
        observed_price=29.99,
    )
    assert result.outcome == EvidenceVerificationOutcome.REJECTED
    assert "fabricated or mock" in result.verification_notes


@pytest.mark.asyncio
async def test_scenario_4_offer_url_differs_from_captured_url_rejected(disposable_db):
    """Scenario 4: Offer URL differs from captured item URL -> REJECTED."""
    c_run = CollectionRun(
        id=f"run_valid_{_uuid()[:8]}",
        job_id="job_real_crawler",
        status=CollectionJobStatus.COMPLETED,
        started_at=_utcnow(),
        completed_at=_utcnow(),
    )
    disposable_db.add(c_run)

    srec = SourceRecord(
        id=f"srec_{_uuid()[:12]}",
        collection_run_id=c_run.id,
        source_type=DataSourceType.AMAZON,
        external_id="B08N5WRWNW",
        geo_confidence=ConfidenceLevel.HIGH,
        is_synthetic=False,
        raw_data={
            "url": "https://www.amazon.com/dp/B08N5WRWNW",
            "provider": "authentic_public_marketplace_capture",
            "retailer": "amazon",
            "asin": "B08N5WRWNW",
            "observed_price": 29.99,
            "source_timestamp": "2026-11-10T14:30:00Z",
            "capture_signature": "sha256_mock_sig_ok",
        },
    )
    disposable_db.add(srec)
    await disposable_db.commit()

    # Offer claims URL for a different product
    result = await verify_commercial_evidence_db(
        db=disposable_db,
        url="https://www.amazon.com/dp/B07984Q864",  # Different URL!
        price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
        source_record_id=srec.id,
        expected_asin="B08N5WRWNW",
        observed_price=29.99,
    )
    assert result.outcome == EvidenceVerificationOutcome.REJECTED
    assert "differs from captured item URL" in result.verification_notes


@pytest.mark.asyncio
async def test_scenario_5_price_missing_from_source_rejected(disposable_db):
    """Scenario 5: Price missing from source -> REJECTED."""
    c_run = CollectionRun(
        id=f"run_valid_{_uuid()[:8]}",
        job_id="job_real_crawler",
        status=CollectionJobStatus.COMPLETED,
        started_at=_utcnow(),
        completed_at=_utcnow(),
    )
    disposable_db.add(c_run)

    srec = SourceRecord(
        id=f"srec_{_uuid()[:12]}",
        collection_run_id=c_run.id,
        source_type=DataSourceType.AMAZON,
        external_id="B08N5WRWNW",
        geo_confidence=ConfidenceLevel.HIGH,
        is_synthetic=False,
        raw_data={
            "url": "https://www.amazon.com/dp/B08N5WRWNW",
            "provider": "authentic_public_marketplace_capture",
            "retailer": "amazon",
            "asin": "B08N5WRWNW",
            # "observed_price" is missing!
            "source_timestamp": "2026-11-10T14:30:00Z",
            "capture_signature": "sha256_mock_sig_ok",
        },
    )
    disposable_db.add(srec)
    await disposable_db.commit()

    result = await verify_commercial_evidence_db(
        db=disposable_db,
        url="https://www.amazon.com/dp/B08N5WRWNW",
        price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
        source_record_id=srec.id,
        expected_asin="B08N5WRWNW",
        observed_price=29.99,
    )
    assert result.outcome == EvidenceVerificationOutcome.REJECTED
    assert "Observed price missing" in result.verification_notes


@pytest.mark.asyncio
async def test_scenario_6_malformed_source_price_rejected(disposable_db):
    """Scenario 6: Malformed or non-positive source price -> REJECTED."""
    c_run = CollectionRun(
        id=f"run_valid_{_uuid()[:8]}",
        job_id="job_real_crawler",
        status=CollectionJobStatus.COMPLETED,
        started_at=_utcnow(),
        completed_at=_utcnow(),
    )
    disposable_db.add(c_run)

    srec = SourceRecord(
        id=f"srec_{_uuid()[:12]}",
        collection_run_id=c_run.id,
        source_type=DataSourceType.AMAZON,
        external_id="B08N5WRWNW",
        geo_confidence=ConfidenceLevel.HIGH,
        is_synthetic=False,
        raw_data={
            "url": "https://www.amazon.com/dp/B08N5WRWNW",
            "provider": "authentic_public_marketplace_capture",
            "retailer": "amazon",
            "asin": "B08N5WRWNW",
            "observed_price": "NOT_A_PRICE",  # Malformed string!
            "source_timestamp": "2026-11-10T14:30:00Z",
            "capture_signature": "sha256_mock_sig_ok",
        },
    )
    disposable_db.add(srec)
    await disposable_db.commit()

    result = await verify_commercial_evidence_db(
        db=disposable_db,
        url="https://www.amazon.com/dp/B08N5WRWNW",
        price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
        source_record_id=srec.id,
        expected_asin="B08N5WRWNW",
        observed_price=29.99,
    )
    assert result.outcome == EvidenceVerificationOutcome.REJECTED
    assert "malformed or non-positive" in result.verification_notes


@pytest.mark.asyncio
async def test_scenario_7_claimed_price_differs_from_source_price_rejected(disposable_db):
    """Scenario 7: Claimed price differs from source price -> REJECTED."""
    c_run = CollectionRun(
        id=f"run_valid_{_uuid()[:8]}",
        job_id="job_real_crawler",
        status=CollectionJobStatus.COMPLETED,
        started_at=_utcnow(),
        completed_at=_utcnow(),
    )
    disposable_db.add(c_run)

    srec = SourceRecord(
        id=f"srec_{_uuid()[:12]}",
        collection_run_id=c_run.id,
        source_type=DataSourceType.AMAZON,
        external_id="B08N5WRWNW",
        geo_confidence=ConfidenceLevel.HIGH,
        is_synthetic=False,
        raw_data={
            "url": "https://www.amazon.com/dp/B08N5WRWNW",
            "provider": "authentic_public_marketplace_capture",
            "retailer": "amazon",
            "asin": "B08N5WRWNW",
            "observed_price": 29.99,
            "source_timestamp": "2026-11-10T14:30:00Z",
            "capture_signature": "sha256_mock_sig_ok",
        },
    )
    disposable_db.add(srec)
    await disposable_db.commit()

    # Offer claims $49.99 ($20 difference)
    result = await verify_commercial_evidence_db(
        db=disposable_db,
        url="https://www.amazon.com/dp/B08N5WRWNW",
        price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
        source_record_id=srec.id,
        expected_asin="B08N5WRWNW",
        observed_price=49.99,
    )
    assert result.outcome == EvidenceVerificationOutcome.REJECTED
    assert "Price mismatch" in result.verification_notes


@pytest.mark.asyncio
async def test_scenario_8_reused_capture_evidence_for_different_asin_rejected(disposable_db):
    """Scenario 8: Reused capture evidence for different ASIN -> REJECTED."""
    c_run = CollectionRun(
        id=f"run_valid_{_uuid()[:8]}",
        job_id="job_real_crawler",
        status=CollectionJobStatus.COMPLETED,
        started_at=_utcnow(),
        completed_at=_utcnow(),
    )
    disposable_db.add(c_run)

    srec = SourceRecord(
        id=f"srec_{_uuid()[:12]}",
        collection_run_id=c_run.id,
        source_type=DataSourceType.AMAZON,
        external_id="B08N5WRWNW",  # Captured for ASIN A
        geo_confidence=ConfidenceLevel.HIGH,
        is_synthetic=False,
        raw_data={
            "url": "https://www.amazon.com/dp/B08N5WRWNW",
            "provider": "authentic_public_marketplace_capture",
            "retailer": "amazon",
            "asin": "B08N5WRWNW",
            "observed_price": 29.99,
            "source_timestamp": "2026-11-10T14:30:00Z",
            "capture_signature": "sha256_mock_sig_ok",
        },
    )
    disposable_db.add(srec)
    await disposable_db.commit()

    # Reused for ASIN B
    result = await verify_commercial_evidence_db(
        db=disposable_db,
        url="https://www.amazon.com/dp/B08N5WRWNW",
        price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
        source_record_id=srec.id,
        expected_asin="B001EJMS6K",  # Different ASIN!
        observed_price=29.99,
    )
    assert result.outcome == EvidenceVerificationOutcome.REJECTED
    assert "Product identity mismatch" in result.verification_notes


@pytest.mark.asyncio
async def test_scenario_9_source_timestamp_created_manually_rejected(disposable_db):
    """Scenario 9: Source timestamp created manually during import -> REJECTED."""
    c_run = CollectionRun(
        id=f"run_valid_{_uuid()[:8]}",
        job_id="job_real_crawler",
        status=CollectionJobStatus.COMPLETED,
        started_at=_utcnow(),
        completed_at=_utcnow(),
    )
    disposable_db.add(c_run)

    srec = SourceRecord(
        id=f"srec_{_uuid()[:12]}",
        collection_run_id=c_run.id,
        source_type=DataSourceType.AMAZON,
        external_id="B08N5WRWNW",
        geo_confidence=ConfidenceLevel.HIGH,
        is_synthetic=False,
        raw_data={
            "url": "https://www.amazon.com/dp/B08N5WRWNW",
            "provider": "authentic_public_marketplace_capture",
            "retailer": "amazon",
            "asin": "B08N5WRWNW",
            "observed_price": 29.99,
            "source_timestamp": "import_time_20261111_manual_entry",  # Manual import timestamp!
            "capture_signature": "sha256_mock_sig_ok",
        },
    )
    disposable_db.add(srec)
    await disposable_db.commit()

    result = await verify_commercial_evidence_db(
        db=disposable_db,
        url="https://www.amazon.com/dp/B08N5WRWNW",
        price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
        source_record_id=srec.id,
        expected_asin="B08N5WRWNW",
        observed_price=29.99,
    )
    assert result.outcome == EvidenceVerificationOutcome.REJECTED
    assert "generated during import" in result.verification_notes


@pytest.mark.asyncio
async def test_scenario_10_legacy_script_permanently_disabled_raises_runtime_error():
    """Scenario 10: Legacy script attempting to re-verify quarantined products -> RuntimeError."""
    with pytest.raises(RuntimeError, match="DEPRECATED_ENTRYPOINT"):
        await ingest_verified_us_products.run_genuine_us_discovery_ingestion()


@pytest.mark.asyncio
async def test_scenario_11_authentic_record_with_canonical_signature_verified(disposable_db):
    """Positive Control: Truly authentic record with canonical SHA-256 signature is VERIFIED."""
    run_id = f"run_valid_{_uuid()[:8]}"
    asin = "B08N5WRWNW"
    price = 29.99
    ts = "2026-11-10T14:30:00Z"

    c_run = CollectionRun(
        id=run_id,
        job_id="job_real_crawler",
        status=CollectionJobStatus.COMPLETED,
        started_at=_utcnow(),
        completed_at=_utcnow(),
    )
    disposable_db.add(c_run)

    canonical_sig = generate_capture_signature(run_id, asin, price, ts)

    srec = SourceRecord(
        id=f"srec_{_uuid()[:12]}",
        collection_run_id=run_id,
        source_type=DataSourceType.AMAZON,
        external_id=asin,
        geo_confidence=ConfidenceLevel.HIGH,
        is_synthetic=False,
        raw_data={
            "url": f"https://www.amazon.com/dp/{asin}",
            "provider": "authentic_public_marketplace_capture",
            "retailer": "amazon",
            "asin": asin,
            "observed_price": price,
            "source_timestamp": ts,
            "capture_signature": canonical_sig,
        },
    )
    disposable_db.add(srec)
    await disposable_db.commit()

    result = await verify_commercial_evidence_db(
        db=disposable_db,
        url=f"https://www.amazon.com/dp/{asin}",
        price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
        source_record_id=srec.id,
        expected_asin=asin,
        observed_price=price,
    )
    assert result.outcome == EvidenceVerificationOutcome.VERIFIED
    assert "Documented external provider acquisition record" in result.verification_notes

    # Strict validation also passes without raising
    validated_type = await validate_commercial_evidence_strict_db(
        db=disposable_db,
        url=f"https://www.amazon.com/dp/{asin}",
        price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
        source_record_id=srec.id,
        expected_asin=asin,
        observed_price=price,
    )
    assert validated_type == PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value
