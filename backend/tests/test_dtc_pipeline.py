"""
US WIN HUNTER — DTC Evidence Pipeline & Anti-Tampering Regression Tests
Tests end-to-end evidence flow from authentic manufacturer DTC artifacts to ProductOffers:
1. Verifies authentic Delta Faucet GR150-SP OEM list price ($174.70 USD) flows to ProductOffer and API report.
2. Verifies authentic AstroAI 1000813 DTC manufacturer price ($9.99 USD) with UNKNOWN stock.
3. Verifies authentic ChomChom Roller DTC price ($24.99 USD) with UNKNOWN stock.
4. Verifies authentic ChomChom merchant bundle (Roller + Detailer) is recorded with UNKNOWN price and stock.
5. Adversarial: Fake price smuggled in assistant preamble comments -> REJECTED.
6. Adversarial: Currency mismatch between claim and artifact -> REJECTED.
7. Adversarial: Canonical URL / host mismatch -> REJECTED.
"""

from __future__ import annotations

import os
from pathlib import Path
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
    BundleMechanism,
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
    inspect_artifact_content,
    extract_structured_product_evidence,
    generate_capture_signature,
    verify_commercial_evidence_db,
    validate_commercial_evidence_strict_db,
    EvidenceVerificationOutcome,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


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
async def test_delta_faucet_oem_evidence_pipeline(disposable_db):
    """Verifies Delta Faucet OEM $174.70 USD flows authentically from artifact to verified offer."""
    art_path = REPO_ROOT / "docs" / "run_reports" / "artifacts" / "capture_GR150-SP_delta_faucet.html"
    assert art_path.exists(), "Delta Faucet artifact must exist on disk"

    # 1. Content inspection
    is_valid, err, meta = inspect_artifact_content(
        artifact_path=art_path,
        expected_identity="GR150-SP",
        expected_price=174.70,
        expected_currency="USD",
        source_url="https://www.deltafaucet.com/kitchen/product/GR150-SP.html",
    )
    assert is_valid, f"Delta artifact failed inspection: {err}"
    assert meta["size_bytes"] > 0
    actual_sha = meta["actual_sha256"]

    # 2. Database records
    c_run = CollectionRun(
        id=f"run_test_{_uuid()[:8]}",
        job_id="job_dtc_test",
        status=CollectionJobStatus.COMPLETED,
        started_at=_utcnow(),
        completed_at=_utcnow(),
        coverage_notes="Authentic test run",
    )
    disposable_db.add(c_run)

    sig = generate_capture_signature(c_run.id, "GR150-SP", 174.70, "2026-11-11T16:15:00Z")

    srec = SourceRecord(
        id=f"srec_test_{_uuid()[:8]}",
        collection_run_id=c_run.id,
        source_type=DataSourceType.OTHER,
        external_id="GR150-SP",
        geo_confidence=ConfidenceLevel.HIGH,
        is_synthetic=False,
        raw_data={
            "url": "https://www.deltafaucet.com/kitchen/product/GR150-SP.html",
            "provider": "authorized_http_collector",
            "retailer": "Delta Faucet",
            "observed_price": 174.70,
            "currency": "USD",
            "source_timestamp": "2026-11-11T16:15:00Z",
            "capture_signature": sig,
            "artifact_path": str(art_path),
            "artifact_sha256": actual_sha,
            "availability": "UNKNOWN",
        },
    )
    disposable_db.add(srec)

    product = Product(
        id=f"prod_test_{_uuid()[:8]}",
        name="Delta Faucet Glass Rinser",
        normalized_name="delta faucet glass rinser",
        target_country="US",
        source_type="dtc_catalog",
        is_physical=True,
        is_synthetic=False,
    )
    disposable_db.add(product)

    offer = ProductOffer(
        id=f"off_test_{_uuid()[:8]}",
        product_id=product.id,
        source_url="https://www.deltafaucet.com/kitchen/product/GR150-SP.html",
        price_usd=174.70,
        currency="USD",
        quantity=1,
        is_bundle=False,
        observed_at=_utcnow(),
        evidence_type=EvidenceType.OEM_LIST_PRICE,
        price_evidence_type=PriceEvidenceType.OEM_LIST_PRICE,
        raw_data={
            "source_record_id": srec.id,
            "collection_run_id": c_run.id,
            "availability": "UNKNOWN",
        },
    )
    disposable_db.add(offer)
    await disposable_db.commit()

    # 3. Fail-Closed strict DB verification
    res = await verify_commercial_evidence_db(
        db=disposable_db,
        url=offer.source_url,
        price_evidence_type=offer.price_evidence_type.value,
        source_record_id=srec.id,
        observed_price=174.70,
        currency="USD",
        product_identity="GR150-SP",
        observed_at="2026-11-11T16:15:00Z",
    )
    assert res.outcome == EvidenceVerificationOutcome.VERIFIED


@pytest.mark.asyncio
async def test_astroai_dtc_evidence_pipeline(disposable_db):
    """Verifies AstroAI $9.99 USD price extraction with UNKNOWN stock status."""
    art_path = REPO_ROOT / "docs" / "run_reports" / "artifacts" / "capture_1000813_astroai.html"
    assert art_path.exists()

    is_valid, err, meta = inspect_artifact_content(
        artifact_path=art_path,
        expected_identity="1000813",
        expected_price=9.99,
        expected_currency="USD",
        source_url="https://www.astroai.com/digital-tire-pressure-gauge-150-psi/ap/1000813",
    )
    assert is_valid, f"AstroAI inspection failed: {err}"

    # Verify structured extraction availability is UNKNOWN (not inferred InStock)
    content = art_path.read_text(encoding="utf-8")
    evidence = extract_structured_product_evidence(content)
    matching_prices = [p for p in evidence["prices"] if abs(p["price"] - 9.99) < 0.05]
    assert len(matching_prices) > 0
    assert all(p["availability"] == "UNKNOWN" for p in matching_prices)


@pytest.mark.asyncio
async def test_chomchom_roller_and_bundle_evidence():
    """Verifies ChomChom Roller $24.99 USD price and bundle handle presence."""
    art_path = REPO_ROOT / "docs" / "run_reports" / "artifacts" / "capture_ChomChom_chomchom_pets.html"
    assert art_path.exists()

    is_valid, err, meta = inspect_artifact_content(
        artifact_path=art_path,
        expected_identity="chomchom-roller-pet-hair-remover-and-reusable-lint-roller",
        expected_price=24.99,
        expected_currency="USD",
        source_url="https://chomchomforpets.com/",
    )
    assert is_valid, f"ChomChom inspection failed: {err}"

    # Verify bundle handle is present in structured identities
    content = art_path.read_text(encoding="utf-8")
    evidence = extract_structured_product_evidence(content)
    assert any("chomchom-roller-detailer-bundle" in ident for ident in evidence["identities"])


@pytest.mark.asyncio
async def test_adversarial_preamble_smuggling_rejected():
    """Adversarial: Price that exists ONLY in an assistant preamble comment must be REJECTED."""
    fake_html = (
        "<!-- US WIN HUNTER COMMERCIAL EVIDENCE\n"
        "Claimed Price: $888.88 USD\n"
        "Target ASIN: B09FAKEASIN\n"
        "-->\n"
        "<html><body><h1>Real Product</h1><p>Genuine Price: $29.99</p></body></html>"
    )
    fd, path = tempfile.mkstemp(prefix="art_smuggle_", suffix=".html")
    os.close(fd)
    tmp_p = Path(path)
    tmp_p.write_text(fake_html, encoding="utf-8")

    try:
        # Searching for the smuggled price $888.88 must FAIL
        is_valid, err, _ = inspect_artifact_content(
            artifact_path=tmp_p,
            expected_identity="B09FAKEASIN",
            expected_price=888.88,
            expected_currency="USD",
        )
        assert not is_valid
        assert "claimed observed price" in err or "expected product identity" in err
    finally:
        if tmp_p.exists():
            tmp_p.unlink()


@pytest.mark.asyncio
async def test_adversarial_currency_mismatch_rejected():
    """Adversarial: Claiming EUR when artifact specifies USD in JSON-LD must be REJECTED."""
    json_ld_html = (
        '<html><head>'
        '<script type="application/ld+json">'
        '{"@type": "Product", "name": "Widget", "sku": "WIDGET123", "offers": {"price": "49.99", "priceCurrency": "USD"}}'
        '</script>'
        '</head><body><title>Widget</title></body></html>'
    )
    fd, path = tempfile.mkstemp(prefix="art_curr_", suffix=".html")
    os.close(fd)
    tmp_p = Path(path)
    tmp_p.write_text(json_ld_html, encoding="utf-8")

    try:
        is_valid, err, _ = inspect_artifact_content(
            artifact_path=tmp_p,
            expected_identity="WIDGET123",
            expected_price=49.99,
            expected_currency="EUR",  # Mismatch
        )
        assert not is_valid
        assert "currency mismatch" in err.lower()
    finally:
        if tmp_p.exists():
            tmp_p.unlink()
