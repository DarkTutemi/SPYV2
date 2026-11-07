"""
US WIN HUNTER — Phase 4: Engine F Bundle Intelligence Tests

Tests for:
- LandingPageExtractor bundle pattern extraction
- LLMService heuristic & fallback classification
- Natural vs forced bundle distinction
- AOV scenario modeling ($30-$90 USD target for 3, 5, 10 units)
- Bundle intelligence API endpoints
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import Base, engine, async_session_factory
from app.adapters.landing_page import LandingPageExtractor
from app.engines.bundle_engine import BundleIntelligenceEngine
from app.models.models import (
    BundleMechanism,
    BundleOffer,
    DataSourceType,
    Product,
)
from app.services.llm_service import LLMService


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db():
    async with async_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestLandingPageExtractor:

    def test_extract_explicit_offers(self):
        extractor = LandingPageExtractor()
        html = """
        <div class="product-bundles">
            <h3>Special Bundle Offers</h3>
            <p>Buy 3 Pack for $45.00 - Save 20%</p>
            <p>Pack of 5 for $65.00 - Save 35%</p>
            <p>10 Units: $110.00 - Save 50%</p>
        </div>
        """
        offers = extractor.extract_offers(html, source_url="https://example.com/item")
        assert len(offers) == 3

        # Check 3-pack
        offer_3 = next(o for o in offers if o["quantity"] == 3)
        assert offer_3["bundle_price_usd"] == 45.0
        assert offer_3["unit_price_usd"] == 15.0

        # Check 5-pack
        offer_5 = next(o for o in offers if o["quantity"] == 5)
        assert offer_5["bundle_price_usd"] == 65.0
        assert offer_5["unit_price_usd"] == 13.0

    def test_derive_from_single_price(self):
        extractor = LandingPageExtractor()
        html = "<p>Price: $19.99</p><p>Available in 3 pack and 5 pack options</p>"
        offers = extractor.extract_offers(html)
        assert len(offers) >= 1
        quantities = [o["quantity"] for o in offers]
        assert 3 in quantities or 5 in quantities


class TestBundleMechanismClassification:

    @pytest.mark.asyncio
    async def test_daily_rotation_classification(self):
        llm = LLMService()
        result = await llm.classify_bundle_mechanism(
            product_name="Ultra Soft Breathable Underwear Set",
            description="Daily wear briefs designed for maximum comfort and rotational use.",
            observed_bundles=[{"quantity": 5, "bundle_price": 49.99}],
        )
        assert result["mechanism"] == BundleMechanism.DAILY_ROTATION
        assert result["is_natural"] is True
        assert result["confidence"] > 0.4

    @pytest.mark.asyncio
    async def test_multiple_locations_classification(self):
        llm = LLMService()
        result = await llm.classify_bundle_mechanism(
            product_name="Magnetic Cable Organizer Clip",
            description="Keep cables tidy across multiple rooms, your car dashboard, and office desk.",
            observed_bundles=[{"quantity": 3, "bundle_price": 29.99}],
        )
        assert result["mechanism"] == BundleMechanism.MULTIPLE_LOCATIONS
        assert result["is_natural"] is True

    @pytest.mark.asyncio
    async def test_unknown_mechanism_when_no_functional_reason(self):
        llm = LLMService()
        result = await llm.classify_bundle_mechanism(
            product_name="Decorative Glass Vase",
            description="A beautiful unique centerpiece for your living room table.",
            observed_bundles=[],
        )
        assert result["mechanism"] == BundleMechanism.UNKNOWN
        assert result["is_natural"] is False


class TestBundleIntelligenceEngine:

    @pytest.mark.asyncio
    async def test_analyze_product_bundles_and_aov(self, db):
        product = Product(
            name="Leakproof Everyday Underwear",
            description="Designed for daily rotational use and effortless washing.",
            min_price_usd=12.0,
            target_country="US",
            source_type=DataSourceType.MANUAL_IMPORT,
        )
        db.add(product)
        await db.flush()

        engine = BundleIntelligenceEngine(db)
        page_html = """
        <div>
            <h2>Select Quantity</h2>
            <button>Buy 3 for $32.00</button>
            <button>Buy 5 for $48.00</button>
            <button>Buy 10 for $85.00</button>
        </div>
        """
        analysis = await engine.analyze_product_bundles(
            product_id=product.id,
            page_content=page_html,
            source_url="https://example.com/product",
        )

        assert analysis["bundle_mechanism"] == "daily_rotation"
        assert analysis["is_natural_bundle"] is True
        assert len(analysis["bundles"]) == 3

        # Verify AOV scenarios
        scenarios = analysis["aov_scenarios"]
        assert len(scenarios) == 3  # 3, 5, 10
        # All 3 observed bundles ($32, $48, $85) fall in $30-$90 range!
        assert all(s["is_within_target_aov"] is True for s in scenarios)


@pytest.mark.asyncio
async def test_bundle_api_endpoints(client, db):
    product = Product(
        name="Silicone Kitchen Sponge Scrubber",
        description="Reusable kitchen sink sponges for heavy daily cleaning.",
        min_price_usd=8.0,
        target_country="US",
        source_type=DataSourceType.MANUAL_IMPORT,
    )
    db.add(product)
    await db.commit()

    # Call analyze endpoint
    res = await client.post(
        f"/api/v1/bundles/analyze/{product.id}",
        json={"page_content": "Buy 5 for $35.00 - Save 25%"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["product_id"] == product.id
    assert len(data["bundles"]) >= 1

    # Call scenarios endpoint
    res_scenarios = await client.get(f"/api/v1/bundles/scenarios/{product.id}")
    assert res_scenarios.status_code == 200
    scenarios_data = res_scenarios.json()
    assert len(scenarios_data["aov_scenarios"]) == 3
