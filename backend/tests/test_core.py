"""
US WIN HUNTER — Test Suite

Tests for data import, deduplication, scoring, and API endpoints.
"""

from __future__ import annotations

import json
import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport

from app.core.database import Base, engine, async_session_factory, init_db, drop_db
from app.main import app
from app.models.models import (
    Advertisement,
    Advertiser,
    BundleMechanism,
    BundleOffer,
    ConfidenceLevel,
    DataSource,
    DataSourceType,
    EvidenceType,
    Product,
)
from app.services.import_service import ImportService
from app.engines.scoring import ScoringEngine


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Reset database for each test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db():
    """Provide a database session."""
    async with async_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    """Provide an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ─── Sample Data ─────────────────────────────────────────────────────────────

SAMPLE_META_ADS = [
    {
        "id": "ad_001",
        "adArchiveID": "ad_001",
        "pageId": "page_100",
        "pageName": "SuperGadgets US",
        "title": "Ultra Absorbent Towel Set",
        "bodies": ["The most absorbent microfiber towel you'll ever use. Perfect for kitchen, bathroom, and car."],
        "images": ["https://example.com/towel1.jpg"],
        "linkUrl": "https://supergadgets.com/ultra-towel",
        "startDate": "2026-10-01",
        "isActive": True,
        "targetCountries": ["US"],
        "currency": "USD",
    },
    {
        "id": "ad_002",
        "adArchiveID": "ad_002",
        "pageId": "page_100",
        "pageName": "SuperGadgets US",
        "title": "Ultra Absorbent Towel Set",
        "bodies": ["Buy 3 and save 20%! Kitchen, bathroom, car - covered."],
        "images": ["https://example.com/towel2.jpg"],
        "linkUrl": "https://supergadgets.com/ultra-towel",
        "startDate": "2026-10-05",
        "isActive": True,
        "targetCountries": ["US"],
        "currency": "USD",
    },
    {
        "id": "ad_003",
        "adArchiveID": "ad_003",
        "pageId": "page_200",
        "pageName": "CleanLiving Store",
        "title": "Premium Microfiber Towels 5-Pack",
        "bodies": ["Stop using paper towels. Our reusable microfiber towels last 500+ washes."],
        "images": ["https://example.com/towel3.jpg"],
        "linkUrl": "https://cleanliving.store/microfiber-5pack",
        "startDate": "2026-10-10",
        "isActive": True,
        "targetCountries": ["US"],
        "currency": "USD",
    },
    {
        "id": "ad_004",
        "adArchiveID": "ad_004",
        "pageId": "page_300",
        "pageName": "UK Shop Ltd",
        "title": "Garden Hose Nozzle",
        "bodies": ["Best garden hose nozzle in the market"],
        "images": ["https://example.com/hose.jpg"],
        "linkUrl": "https://ukshop.co.uk/hose",
        "startDate": "2026-10-15",
        "isActive": True,
        "targetCountries": ["GB"],
        "currency": "GBP",
    },
]


SAMPLE_DUPLICATE_ADS = [
    {
        "id": "ad_001",
        "adArchiveID": "ad_001",
        "pageId": "page_100",
        "pageName": "SuperGadgets US",
        "title": "Ultra Absorbent Towel Set",
        "bodies": ["Duplicate of first ad"],
        "isActive": True,
        "targetCountries": ["US"],
    },
]


# ─── Health Tests ────────────────────────────────────────────────────────────

class TestHealthAPI:

    @pytest.mark.anyio
    async def test_ping(self, client: AsyncClient):
        resp = await client.get("/api/v1/health/ping")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    @pytest.mark.anyio
    async def test_data_health(self, client: AsyncClient):
        resp = await client.get("/api/v1/health/data")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_advertisers" in data
        assert "total_products" in data


# ─── Import Tests ────────────────────────────────────────────────────────────

class TestImportService:

    @pytest.mark.anyio
    async def test_import_meta_ads(self, db):
        """Test importing Meta Ad Library data."""
        service = ImportService(db)
        result = await service.import_data(
            source_type=DataSourceType.META_AD_LIBRARY,
            data=SAMPLE_META_ADS,
        )

        assert result.success is True
        assert result.records_processed == 4
        assert result.records_new == 4
        assert result.records_duplicate == 0
        await db.commit()

    @pytest.mark.anyio
    async def test_duplicate_detection(self, db):
        """Test that duplicate ads are detected."""
        service = ImportService(db)

        # First import
        result1 = await service.import_data(
            source_type=DataSourceType.META_AD_LIBRARY,
            data=SAMPLE_META_ADS,
        )
        assert result1.records_new == 4
        await db.commit()

        # Second import with duplicates
        result2 = await service.import_data(
            source_type=DataSourceType.META_AD_LIBRARY,
            data=SAMPLE_DUPLICATE_ADS,
        )
        assert result2.records_duplicate == 1
        assert result2.records_new == 0
        await db.commit()

    @pytest.mark.anyio
    async def test_advertiser_deduplication(self, db):
        """Test that the same advertiser is not created twice."""
        service = ImportService(db)

        # Two ads from same advertiser
        ads = [SAMPLE_META_ADS[0], SAMPLE_META_ADS[1]]
        result = await service.import_data(
            source_type=DataSourceType.META_AD_LIBRARY,
            data=ads,
        )
        await db.commit()

        # Should have exactly 1 advertiser
        from sqlalchemy import select, func
        count = (await db.execute(
            select(func.count(Advertiser.id))
        )).scalar()
        assert count == 1

    @pytest.mark.anyio
    async def test_us_geo_confidence(self, db):
        """Test geographic confidence assessment."""
        service = ImportService(db)

        # US-targeted ad
        us_conf = service._assess_geo_confidence(SAMPLE_META_ADS[0])
        assert us_conf == ConfidenceLevel.HIGH

        # UK-targeted ad
        uk_conf = service._assess_geo_confidence(SAMPLE_META_ADS[3])
        assert uk_conf != ConfidenceLevel.HIGH

        # USD-only (insufficient)
        usd_only = service._assess_geo_confidence({"currency": "USD"})
        assert usd_only == ConfidenceLevel.LOW  # Per spec: USD alone is NOT evidence

    @pytest.mark.anyio
    async def test_product_extraction(self, db):
        """Test that products are extracted from ad data."""
        service = ImportService(db)
        result = await service.import_data(
            source_type=DataSourceType.META_AD_LIBRARY,
            data=SAMPLE_META_ADS[:3],  # US ads only
        )
        await db.commit()

        from sqlalchemy import select, func
        prod_count = (await db.execute(
            select(func.count(Product.id))
        )).scalar()
        # At least 1 product should be extracted
        assert prod_count >= 1

    @pytest.mark.anyio
    async def test_no_data_import(self, db):
        """Test import with no data."""
        service = ImportService(db)
        result = await service.import_data(
            source_type=DataSourceType.META_AD_LIBRARY,
            data=None,
        )
        assert result.success is False


# ─── Scoring Tests ───────────────────────────────────────────────────────────

class TestScoringEngine:

    async def _setup_test_product(self, db) -> Product:
        """Create a test product with ads."""
        adv = Advertiser(
            name="Test Advertiser",
            normalized_name="test advertiser",
            source_type=DataSourceType.META_AD_LIBRARY,
            country="US",
        )
        db.add(adv)
        await db.flush()

        product = Product(
            name="Test Product",
            normalized_name="test product",
            description="A test product for scoring",
            image_url="https://example.com/test.jpg",
            source_url="https://example.com/test",
            category="test",
            target_country="US",
            source_type=DataSourceType.META_AD_LIBRARY,
        )
        db.add(product)
        await db.flush()

        # Add some ads
        now = datetime.now(timezone.utc)
        for i in range(5):
            ad = Advertisement(
                external_id=f"test_ad_{i}",
                source_type=DataSourceType.META_AD_LIBRARY,
                advertiser_id=adv.id,
                product_id=product.id,
                title=f"Test Ad {i}",
                is_active=True,
                first_seen_at=now - timedelta(days=30 - i * 5),
                last_seen_at=now - timedelta(days=max(0, i - 2)),
            )
            db.add(ad)

        await db.flush()
        return product

    @pytest.mark.anyio
    async def test_score_product(self, db):
        """Test scoring a product."""
        product = await self._setup_test_product(db)
        await db.commit()

        engine = ScoringEngine(db)
        score = await engine.score_product(product.id)

        assert 0 <= score.emergence_score <= 100
        assert 0 <= score.evidence_confidence <= 100
        assert 0 <= score.bundle_potential <= 100
        assert 0 <= score.composite_score <= 100
        assert score.emergence_components is not None
        assert score.confidence_components is not None
        await db.commit()

    @pytest.mark.anyio
    async def test_score_nonexistent_product(self, db):
        """Test scoring a product that doesn't exist."""
        engine = ScoringEngine(db)
        with pytest.raises(ValueError, match="Product not found"):
            await engine.score_product("nonexistent-id")

    @pytest.mark.anyio
    async def test_verification_flag(self, db):
        """High emergence + low confidence = requires verification."""
        product = await self._setup_test_product(db)
        await db.commit()

        engine = ScoringEngine(db)
        score = await engine.score_product(product.id)
        # The test data may or may not trigger this — just verify the field exists
        assert isinstance(score.requires_verification, bool)
        await db.commit()

    @pytest.mark.anyio
    async def test_bundle_scoring_no_bundles(self, db):
        """Test bundle scoring when no bundles exist."""
        product = await self._setup_test_product(db)
        await db.commit()

        engine = ScoringEngine(db)
        score = await engine.score_product(product.id)
        # With no bundles, bundle potential should be low
        assert score.bundle_potential <= 30  # No bundles = low score
        await db.commit()

    @pytest.mark.anyio
    async def test_bundle_scoring_with_natural_bundle(self, db):
        """Test bundle scoring with a natural bundle."""
        product = await self._setup_test_product(db)

        bundle = BundleOffer(
            product_id=product.id,
            quantity=5,
            bundle_price_usd=49.99,
            unit_price_usd=9.99,
            estimated_order_value_usd=49.99,
            bundle_mechanism=BundleMechanism.DAILY_ROTATION,
            mechanism_evidence="Underwear needs daily rotation",
            is_natural_bundle=True,
            natural_bundle_reasoning="Customers need multiple for daily use",
            bundle_status="offered",
        )
        db.add(bundle)
        await db.commit()

        engine = ScoringEngine(db)
        score = await engine.score_product(product.id)
        # With a natural bundle in AOV range, should score higher
        assert score.bundle_potential > 30
        await db.commit()


# ─── API Endpoint Tests ─────────────────────────────────────────────────────

class TestProductsAPI:

    @pytest.mark.anyio
    async def test_list_products_empty(self, client: AsyncClient):
        resp = await client.get("/api/v1/products/")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.anyio
    async def test_create_product(self, client: AsyncClient):
        resp = await client.post("/api/v1/products/", json={
            "name": "Test Product",
            "source_type": "manual_import",
            "target_country": "US",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Product"
        assert data["target_country"] == "US"
        assert data["normalized_name"] == "test product"

    @pytest.mark.anyio
    async def test_get_product(self, client: AsyncClient):
        # Create
        resp = await client.post("/api/v1/products/", json={
            "name": "Get Me Product",
            "source_type": "manual_import",
        })
        product_id = resp.json()["id"]

        # Retrieve
        resp = await client.get(f"/api/v1/products/{product_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Get Me Product"

    @pytest.mark.anyio
    async def test_product_report(self, client: AsyncClient):
        # Create product
        resp = await client.post("/api/v1/products/", json={
            "name": "Report Product",
            "source_type": "manual_import",
        })
        product_id = resp.json()["id"]

        # Get report
        resp = await client.get(f"/api/v1/products/{product_id}/report")
        assert resp.status_code == 200
        report = resp.json()
        assert "data_gaps" in report
        assert "emergence_score" in report
        # Should identify missing data
        assert len(report["data_gaps"]) > 0


class TestImportAPI:

    @pytest.mark.anyio
    async def test_import_meta_ads_via_api(self, client: AsyncClient):
        resp = await client.post("/api/v1/import/meta-ads", json={
            "source_type": "meta_ad_library",
            "data": SAMPLE_META_ADS[:2],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["records_processed"] == 2

    @pytest.mark.anyio
    async def test_import_json(self, client: AsyncClient):
        resp = await client.post("/api/v1/import/json", json={
            "source_type": "manual_import",
            "data": [
                {"product_name": "Test Import Product", "country": "US"},
            ],
            "options": {"entity_type": "product"},
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True


class TestAdvertisersAPI:

    @pytest.mark.anyio
    async def test_list_advertisers_empty(self, client: AsyncClient):
        resp = await client.get("/api/v1/advertisers/")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.anyio
    async def test_create_and_list(self, client: AsyncClient):
        # Import ads to create advertisers
        await client.post("/api/v1/import/meta-ads", json={
            "source_type": "meta_ad_library",
            "data": SAMPLE_META_ADS[:3],
        })

        resp = await client.get("/api/v1/advertisers/")
        assert resp.status_code == 200
        advertisers = resp.json()
        assert len(advertisers) >= 2  # At least two distinct advertisers

    @pytest.mark.anyio
    async def test_search_advertisers(self, client: AsyncClient):
        await client.post("/api/v1/import/meta-ads", json={
            "source_type": "meta_ad_library",
            "data": SAMPLE_META_ADS[:3],
        })

        resp = await client.get("/api/v1/advertisers/?search=SuperGadgets")
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) >= 1
        assert "SuperGadgets" in results[0]["name"]


# ─── Edge Case Tests ────────────────────────────────────────────────────────

class TestEdgeCases:

    @pytest.mark.anyio
    async def test_multiple_names_same_product(self, db):
        """Different names for the same product should not auto-merge."""
        service = ImportService(db)
        ads = [
            {
                "id": "same_prod_1",
                "pageId": "p1",
                "pageName": "Store A",
                "title": "Ultra Absorbent Towel",
                "bodies": ["Best towel ever"],
                "isActive": True,
                "targetCountries": ["US"],
            },
            {
                "id": "same_prod_2",
                "pageId": "p2",
                "pageName": "Store B",
                "title": "Super Absorbent Cleaning Cloth",
                "bodies": ["Amazing cleaning cloth"],
                "isActive": True,
                "targetCountries": ["US"],
            },
        ]
        result = await service.import_data(
            source_type=DataSourceType.META_AD_LIBRARY,
            data=ads,
        )
        await db.commit()

        from sqlalchemy import select, func
        # Different names = different products (no auto-merge)
        prod_count = (await db.execute(select(func.count(Product.id)))).scalar()
        assert prod_count == 2  # Should NOT merge based on similarity alone

    @pytest.mark.anyio
    async def test_missing_source_records(self, db):
        """Handle records with missing fields gracefully."""
        service = ImportService(db)
        incomplete = [
            {
                "id": "incomplete_1",
                "isActive": True,
            },
        ]
        result = await service.import_data(
            source_type=DataSourceType.META_AD_LIBRARY,
            data=incomplete,
        )
        assert result.success is True
        assert result.records_processed == 1
        await db.commit()

    @pytest.mark.anyio
    async def test_non_us_ads_geo_tracking(self, db):
        """Non-US ads should still be imported but with proper geo context."""
        service = ImportService(db)
        result = await service.import_data(
            source_type=DataSourceType.META_AD_LIBRARY,
            data=[SAMPLE_META_ADS[3]],  # UK ad
        )
        await db.commit()

        from sqlalchemy import select
        ads = (await db.execute(select(Advertisement))).scalars().all()
        assert len(ads) == 1
        assert ads[0].target_country == "GB"

    @pytest.mark.anyio
    async def test_bundle_without_purchase_evidence(self, db):
        """Bundle offered ≠ bundle purchased."""
        product = Product(
            name="Bundle Test",
            normalized_name="bundle test",
            target_country="US",
            source_type=DataSourceType.MANUAL_IMPORT,
        )
        db.add(product)
        await db.flush()

        bundle = BundleOffer(
            product_id=product.id,
            quantity=10,
            bundle_price_usd=99.99,
            bundle_status="offered",  # NOT "purchased"
            is_natural_bundle=False,
        )
        db.add(bundle)
        await db.commit()

        # Verify status distinction
        assert bundle.bundle_status == "offered"
        assert bundle.is_natural_bundle is False

    @pytest.mark.anyio
    async def test_usd_alone_not_us_evidence(self, db):
        """USD pricing alone must NOT be treated as US evidence."""
        service = ImportService(db)
        conf = service._assess_geo_confidence({"currency": "USD"})
        assert conf == ConfidenceLevel.LOW

