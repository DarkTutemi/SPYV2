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

import json
import os
from pathlib import Path
import tempfile
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.core.database import Base
from app.engines.scoring import BalancedScoringEngine
from app.models.models import (
    Product,
    ProductOffer,
    BundleOffer,
    BundleMechanism,
    OpportunityScore,
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

    delta_ts = "2026-11-11T16:40:18.013475+00:00"
    sig = generate_capture_signature(c_run.id, "GR150-SP", 174.70, delta_ts)

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
            "source_timestamp": delta_ts,
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
        observed_at=delta_ts,
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


@pytest.mark.asyncio
async def test_scoring_recognizes_dtc_and_oem_offers_preserves_provenance(disposable_db):
    """
    Task 1 & 2 Regression:
    - Manual-origin (RESEARCH_HYPOTHESIS / MANUAL_IMPORT) products with manifest-backed
      Delta ($174.70 OEM_LIST_PRICE), AstroAI ($9.99 DTC_MANUFACTURER_OBSERVED_PRICE), and
      ChomChom ($24.99 DTC_MANUFACTURER_OBSERVED_PRICE) offers get observed prices & partial validation.
    - Manual scenario offers and modeled scenario bundles NEVER count.
    - Original manual provenance stays intact, qualification requires independent ad demand.
    """
    manifest = json.loads(
        (REPO_ROOT / "docs" / "run_reports" / "sanitized_acquisition_manifest.json").read_text(encoding="utf-8")
    )
    by_art = {
        e["sanitized_artifact_path"]: e
        for e in manifest["dtc_manufacturer_evidence"]
        if e.get("sanitized_artifact_path")
    }

    c_run = CollectionRun(
        id="run_dtc_scoring_reg_20261111",
        job_id="job_dtc_scoring_reg",
        status=CollectionJobStatus.COMPLETED,
        started_at=_utcnow(),
        completed_at=_utcnow(),
        coverage_notes="Authentic public DTC catalog acquisition for scoring regression",
    )
    disposable_db.add(c_run)

    cases = [
        {
            "name": "Delta Faucet Glass Rinser (GR150-SP)",
            "category": "Kitchen DIY",
            "art_rel": "docs/run_reports/artifacts/capture_GR150-SP_delta_faucet.html",
            "ext_id": "GR150-SP",
            "price": 174.70,
            "scenario_price": 69.00,
            "pet": PriceEvidenceType.OEM_LIST_PRICE,
            "et": EvidenceType.OEM_LIST_PRICE,
            "prov": "unverified_manual_import",
            "init_status": "UNVERIFIED_IMPORT",
            "expected_pricing_raw": 75.0,
            "expected_is_oem": True,
        },
        {
            "name": "AstroAI Digital Tire Pressure Gauge 150 PSI",
            "category": "Automotive / DIY",
            "art_rel": "docs/run_reports/artifacts/capture_1000813_astroai.html",
            "ext_id": "1000813",
            "price": 9.99,
            "scenario_price": 11.99,
            "pet": PriceEvidenceType.DTC_MANUFACTURER_OBSERVED_PRICE,
            "et": EvidenceType.DTC_MANUFACTURER_OBSERVED_PRICE,
            "prov": "unverified_manual_hypothesis",
            "init_status": "RESEARCH_HYPOTHESIS",
            "expected_pricing_raw": 85.0,
            "expected_is_oem": False,
        },
        {
            "name": "ChomChom Roller Pet Hair Remover",
            "category": "Home Organization / Cleaning",
            "art_rel": "docs/run_reports/artifacts/capture_ChomChom_chomchom_pets.html",
            "ext_id": "chomchom-roller-pet-hair-remover-and-reusable-lint-roller",
            "price": 24.99,
            "scenario_price": 29.99,
            "pet": PriceEvidenceType.DTC_MANUFACTURER_OBSERVED_PRICE,
            "et": EvidenceType.DTC_MANUFACTURER_OBSERVED_PRICE,
            "prov": "unverified_manual_hypothesis",
            "init_status": "RESEARCH_HYPOTHESIS",
            "expected_pricing_raw": 85.0,
            "expected_is_oem": False,
        },
    ]

    engine = BalancedScoringEngine(disposable_db)

    for idx, c in enumerate(cases):
        m = by_art[c["art_rel"]]
        sig = generate_capture_signature(c_run.id, c["ext_id"], c["price"], m["capture_timestamp"])

        srec = SourceRecord(
            id=f"srec_reg_{idx}_{_uuid()[:6]}",
            collection_run_id=c_run.id,
            source_type=DataSourceType.SHOPIFY if idx == 2 else DataSourceType.OTHER,
            external_id=c["ext_id"],
            geo_confidence=ConfidenceLevel.HIGH,
            is_synthetic=False,
            raw_data={
                "url": m["source_url"],
                "provider": "authorized_http_collector",
                "observed_price": c["price"],
                "currency": "USD",
                "availability": "UNKNOWN",
                "source_timestamp": m["capture_timestamp"],
                "capture_signature": sig,
                "artifact_path": c["art_rel"],
                "artifact_sha256": m["sanitized_artifact_sha256"],
            },
        )
        disposable_db.add(srec)

        prod = Product(
            id=f"prod_reg_{idx}_{_uuid()[:6]}",
            name=c["name"],
            normalized_name=c["name"].lower(),
            description=f"{c['name']} description",
            category=c["category"],
            source_url=m["source_url"],
            target_country="US",
            is_physical=True,
            is_synthetic=False,
            source_type=DataSourceType.MANUAL_IMPORT,
            opportunity_status=c["init_status"],
            min_price_usd=c["scenario_price"],
            raw_data={"provenance": c["prov"], "verification_status": c["init_status"]},
        )
        disposable_db.add(prod)

        # Scenario offer (must never count!)
        scen_off = ProductOffer(
            id=f"off_scen_{idx}_{_uuid()[:6]}",
            product_id=prod.id,
            source_url="https://www.amazon.com/dp/B00SCEN000",
            price_usd=c["scenario_price"],
            currency="USD",
            evidence_type=EvidenceType.UNVERIFIED_HYPOTHESIS,
            price_evidence_type=PriceEvidenceType.SCENARIO_PRICE,
        )
        # Authentic manifest-backed DTC / OEM offer
        dtc_off = ProductOffer(
            id=f"off_dtc_{idx}_{_uuid()[:6]}",
            product_id=prod.id,
            source_url=m["source_url"],
            price_usd=c["price"],
            currency="USD",
            quantity=1,
            is_bundle=False,
            observed_at=datetime.fromisoformat(m["capture_timestamp"]),
            evidence_type=c["et"],
            price_evidence_type=c["pet"],
            raw_data={
                "source_record_id": srec.id,
                "collection_run_id": c_run.id,
                "availability": "UNKNOWN",
            },
        )
        # Hypothetical modeled bundle (must NEVER count as observed merchant offer!)
        hyp_bundle = BundleOffer(
            id=f"bnd_hyp_{idx}_{_uuid()[:6]}",
            product_id=prod.id,
            source_url="https://www.amazon.com/dp/B00HYP000",
            quantity=2,
            bundle_price_usd=c["scenario_price"] * 1.8,
            bundle_status="modeled_scenario",
            evidence_type=EvidenceType.UNVERIFIED_HYPOTHESIS,
            price_evidence_type=PriceEvidenceType.SCENARIO_PRICE,
            is_natural_bundle=False,
        )
        disposable_db.add_all([scen_off, dtc_off, hyp_bundle])

        if idx == 2:
            # Also link ChomChom's real unobserved bundle offer (price & availability UNKNOWN)
            real_bnd = BundleOffer(
                id="bnd_dtc_chom_reg",
                product_id=prod.id,
                source_url="https://chomchomforpets.com/products/chomchom-roller-detailer-bundle-pet-hair-remover-and-reusable-lint-roller",
                quantity=2,
                bundle_price_usd=None,
                bundle_mechanism=BundleMechanism.COMPLETE_COVERAGE,
                bundle_status="unobserved_price",
                evidence_type=EvidenceType.UNKNOWN,
                price_evidence_type=PriceEvidenceType.UNKNOWN,
            )
            disposable_db.add(real_bnd)

        await disposable_db.commit()

        score = await engine.score_product(prod.id, mode="balanced")
        await disposable_db.commit()

        # Re-read persisted OpportunityScore & Product from DB
        persisted_score = (
            await disposable_db.execute(
                select(OpportunityScore).where(OpportunityScore.product_id == prod.id)
            )
        ).scalar_one()
        persisted_prod = await disposable_db.get(Product, prod.id)

        # Recognized verified commercial price (never scenario price)
        assert persisted_score.observed_single_price_usd == c["price"]
        assert persisted_score.observed_bundle_price_usd is None
        assert persisted_score.customer_aov_usd is None
        assert persisted_score.opportunity_status == "PARTIALLY_VALIDATED"
        assert persisted_score.opportunity_status != "QUALIFIED_OPPORTUNITY"
        assert persisted_score.requires_verification is True
        assert 40.0 < persisted_score.evidence_confidence < 50.0
        assert persisted_score.confidence_components["pricing_evidence"]["raw"] == c["expected_pricing_raw"]
        assert persisted_score.confidence_components["pricing_evidence"]["is_branded_oem_catalog"] is c["expected_is_oem"]

        # Original manual provenance remains intact & auditable
        assert persisted_prod.source_type == DataSourceType.MANUAL_IMPORT
        assert persisted_prod.raw_data["provenance"] == c["prov"]


@pytest.mark.asyncio
async def test_unbacked_dtc_offer_on_manual_product_rejected_by_scoring(disposable_db):
    """Manual-origin product claiming DTC_MANUFACTURER_OBSERVED_PRICE without a SourceRecord must stay quarantined."""
    prod = Product(
        id=f"prod_fake_dtc_{_uuid()[:6]}",
        name="Unverified Concept Claiming DTC",
        normalized_name="unverified concept claiming dtc",
        target_country="US",
        is_physical=True,
        is_synthetic=False,
        source_type=DataSourceType.MANUAL_IMPORT,
        opportunity_status="RESEARCH_HYPOTHESIS",
        raw_data={"provenance": "unverified_manual_hypothesis"},
    )
    disposable_db.add(prod)
    fake_dtc = ProductOffer(
        id=f"off_unbacked_{_uuid()[:6]}",
        product_id=prod.id,
        source_url="https://example.org/dtc",
        price_usd=44.99,
        currency="USD",
        evidence_type=EvidenceType.DTC_MANUFACTURER_OBSERVED_PRICE,
        price_evidence_type=PriceEvidenceType.DTC_MANUFACTURER_OBSERVED_PRICE,
    )
    disposable_db.add(fake_dtc)
    await disposable_db.commit()

    score = await BalancedScoringEngine(disposable_db).score_product(prod.id)
    assert score.observed_single_price_usd is None
    assert score.opportunity_status == "RESEARCH_HYPOTHESIS"
    assert score.evidence_confidence <= 10.0


@pytest.mark.asyncio
async def test_artifact_timestamp_and_manifest_binding():
    """Artifact content inspection rejects mismatched capture timestamp or host even if file hash matches."""
    art_path = REPO_ROOT / "docs" / "run_reports" / "artifacts" / "capture_GR150-SP_delta_faucet.html"
    ok_bad_ts, err_ts, _ = inspect_artifact_content(
        artifact_path=art_path,
        expected_identity="GR150-SP",
        expected_price=174.70,
        expected_currency="USD",
        source_url="https://www.deltafaucet.com/kitchen/product/GR150-SP.html",
        expected_timestamp="2026-11-11T00:00:00Z",  # Mismatched timestamp
        repo_root=REPO_ROOT,
    )
    assert not ok_bad_ts
    assert "timestamp" in err_ts.lower()

    ok_bad_url, err_url, _ = inspect_artifact_content(
        artifact_path=art_path,
        expected_identity="GR150-SP",
        expected_price=174.70,
        expected_currency="USD",
        source_url="https://www.evil-mirror.com/GR150-SP.html",
        repo_root=REPO_ROOT,
    )
    assert not ok_bad_url
    assert "url" in err_url.lower()

    # ChomChom homepage bundle trace succeeds with matching manifest timestamp & URL (price stays None/UNKNOWN)
    chom_path = REPO_ROOT / "docs" / "run_reports" / "artifacts" / "capture_ChomChom_chomchom_pets.html"
    ok_bundle, err_bundle, _ = inspect_artifact_content(
        artifact_path=chom_path,
        expected_identity="chomchom-roller-detailer-bundle-pet-hair-remover-and-reusable-lint-roller",
        expected_price=None,
        source_url="https://chomchomforpets.com/",
        expected_timestamp="2026-11-11T17:25:10Z",
        repo_root=REPO_ROOT,
    )
    assert ok_bundle, f"ChomChom bundle trace failed: {err_bundle}"
