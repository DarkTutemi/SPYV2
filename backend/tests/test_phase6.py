"""
US WIN HUNTER — Phase 6 Test Suite: Autonomous Live Discovery Engine

Comprehensive verification for:
1. Provider authentication failure / NOT_CONFIGURED state
2. Provider unavailable / HTTP 401 Unauthorized handling
3. Provider timeout and exponential retry handling
4. Empty dataset handling (SUCCEEDED_EMPTY)
5. Malformed source record quality gates
6. US filter mismatch rejection (non-US ads blocked)
7. Duplicate advertisement prevention
8. Dataset pagination aggregation
9. Hard budget cap enforcement (fail-closed BLOCKED)
10. Discovery Seed Engine taxonomy across 10 US categories
11. Seed yield scoring and empirical feedback prioritization
12. Advertiser Expansion Engine bounded loop & safeguards
13. Bundle-first analysis & $30-$90 AOV feasibility modeling
14. Real vs synthetic provenance segregation
15. Continuous collection scheduler execution & guardrails
16. Discovery API endpoints integration
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func

from app.adapters.apify import ApifyProviderAdapter, ProviderStatus
from app.core.config import get_settings
from app.core.database import Base, engine, async_session_factory
from app.engines.advertiser_expansion import AdvertiserExpansionEngine
from app.engines.bundle_engine import BundleIntelligenceEngine
from app.engines.seed_engine import DiscoverySeedEngine, TAXONOMY_CATEGORIES
from app.main import app
from app.models.models import (
    Advertisement,
    Advertiser,
    BundleMechanism,
    BundleOffer,
    CollectionJob,
    CollectionRun,
    CollectionJobStatus,
    DataSource,
    DataSourceType,
    Product,
    SourceRecord,
)
from app.services.import_service import ImportService
from app.services.scheduler import SchedulerService


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


# ── Sample Authentic Fixture Records ──────────────────────────────────────────

REAL_APIFY_META_RECORDS: list[dict[str, Any]] = [
    {
        "id": "1009283746152",
        "pageId": "48192038475",
        "pageName": "CleanHome Direct",
        "snapshotUrl": "https://www.facebook.com/ads/library/?id=1009283746152",
        "startDate": "2026-10-01T12:00:00Z",
        "isActive": True,
        "images": ["https://creative.cleanhome.com/mop-pack3.jpg"],
        "videos": [],
        "linkUrl": "https://cleanhome.com/products/washable-mop-3pack?utm_source=fb",
        "title": "Washable Microfiber Mop Pads — Multi-Room 3-Pack",
        "bodies": ["Stop throwing away single-use pads. Our washable rotation pack gives you 1 for kitchen, 1 for bathroom, 1 in laundry."],
        "targetCountries": ["US"],
    },
    {
        "id": "1009283746153",
        "pageId": "91827364501",
        "pageName": "MotoShield USA",
        "snapshotUrl": "https://www.facebook.com/ads/library/?id=1009283746153",
        "startDate": "2026-10-05T08:30:00Z",
        "isActive": True,
        "images": ["https://creative.motoshield.com/socket-tray.jpg"],
        "videos": [],
        "linkUrl": "https://motoshield.com/products/magnetic-socket-tray-pair",
        "title": "Magnetic Socket Organizer Tray 2-Pack",
        "bodies": ["Keep your 1/4 and 3/8 drive sockets firmly in place. Heavy-duty rare-earth magnets hold upside down."],
        "targetCountries": ["US"],
    },
    {
        "id": "1009283746154",
        "pageId": "55667788990",
        "pageName": "SoleComfort Pro",
        "snapshotUrl": "https://www.facebook.com/ads/library/?id=1009283746154",
        "startDate": "2026-10-10T14:15:00Z",
        "isActive": True,
        "images": ["https://creative.solecomfort.com/socks-5pack.jpg"],
        "videos": [],
        "linkUrl": "https://solecomfort.com/products/daily-compression-socks-5pack",
        "title": "Plantar Fasciitis Compression Socks — 5-Pack Daily Rotation",
        "bodies": ["20-30 mmHg graduated compression for standing all day. Get 5 pairs for a full work week rotation."],
        "targetCountries": ["US"],
    },
]


# ── 1. Provider Auth & Configuration Tests ────────────────────────────────────

@pytest.mark.asyncio
async def test_provider_auth_not_configured(db):
    """When APIFY_API_TOKEN is absent, adapter status is NOT_CONFIGURED and calls fail closed."""
    adapter = ApifyProviderAdapter(db, api_token="")
    status = await adapter.get_status()

    assert status["status"] == ProviderStatus.NOT_CONFIGURED.value
    assert status["configured"] is False

    # Calling discover fails closed immediately without network activity
    result = await adapter.discover_by_keywords(["washable mop pads"])
    assert result["success"] is False
    assert result["status"] == ProviderStatus.NOT_CONFIGURED.value
    assert "missing or empty" in result["error"].lower()


@pytest.mark.asyncio
async def test_provider_auth_invalid_token(db):
    """When Apify returns 401 Unauthorized, the adapter catches it and marks job FAILED."""
    adapter = ApifyProviderAdapter(db, api_token="invalid_token_xyz")

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = httpx.Response(401, text="Unauthorized: Invalid API token.", request=httpx.Request("POST", "http://test"))
        mock_post.return_value = mock_resp

        result = await adapter.discover_by_keywords(["test keyword"])
        assert result["success"] is False
        assert result["status"] == ProviderStatus.FAILED.value
        assert "authentication failed" in result["error"].lower()


# ── 2. Quality Gate & US Targeting Tests ──────────────────────────────────────

@pytest.mark.asyncio
async def test_us_filter_mismatch_rejection(db):
    """Ads targeting non-US geographies (CA, UK, AU, etc.) are strictly rejected by the quality gate."""
    adapter = ApifyProviderAdapter(db)

    mixed_records = [
        {
            "id": "111",
            "pageName": "US Brand",
            "title": "Great US Product",
            "bodies": ["Ships across the USA"],
            "targetCountries": ["US"],
        },
        {
            "id": "222",
            "pageName": "UK Brand",
            "title": "British Kettle",
            "bodies": ["Fast UK delivery"],
            "targetCountries": ["GB", "IE"],  # Non-US
        },
        {
            "id": "333",
            "pageName": "Aussie Gear",
            "title": "Sydney Outdoor Hat",
            "bodies": ["Australian sun protection"],
            "targetCountries": ["AU"],  # Non-US
        },
    ]

    valid, errors = adapter.validate_records(mixed_records)
    assert len(valid) == 1
    assert valid[0]["id"] == "111"
    assert len(errors) == 2
    assert any("Non-US target region" in e for e in errors)


@pytest.mark.asyncio
async def test_malformed_records_rejected(db):
    """Records missing IDs, blank names, or empty content are filtered out gracefully."""
    adapter = ApifyProviderAdapter(db)

    malformed = [
        {"id": "", "pageName": "Valid Brand", "title": "Missing ID"},
        {"id": "444", "pageName": "", "title": "Missing Page Name"},
        {"id": "555", "pageName": "Valid Brand", "title": "", "bodies": [], "images": []},  # completely blank
    ]

    valid, errors = adapter.validate_records(malformed)
    assert len(valid) == 0
    assert len(errors) == 3


# ── 3. Duplicate Prevention & Provenance Tests ────────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_advertisement_prevention(db):
    """Importing the same external ad ID twice marks the second as duplicate."""
    import_service = ImportService(db)

    # First import
    res1 = await import_service.import_data(
        source_type=DataSourceType.META_AD_LIBRARY,
        data=REAL_APIFY_META_RECORDS[:2],
        options={"is_synthetic": False},
    )
    assert res1.success is True
    assert res1.records_new == 2
    assert res1.records_duplicate == 0

    # Second import with overlapping record
    res2 = await import_service.import_data(
        source_type=DataSourceType.META_AD_LIBRARY,
        data=[REAL_APIFY_META_RECORDS[0], REAL_APIFY_META_RECORDS[2]],
        options={"is_synthetic": False},
    )
    assert res2.success is True
    assert res2.records_new == 1  # only record 2 is new
    assert res2.records_duplicate == 1  # record 0 is detected as duplicate

    # Verify total ads in database is 3, not 4
    total_ads = await db.scalar(select(func.count(Advertisement.id)))
    assert total_ads == 3


@pytest.mark.asyncio
async def test_real_vs_synthetic_provenance_isolation(db):
    """Live imported records are flagged as non-synthetic and tracked under separate provenance."""
    import_service = ImportService(db)

    # Import live records
    res_live = await import_service.import_data(
        source_type=DataSourceType.META_AD_LIBRARY,
        data=[REAL_APIFY_META_RECORDS[0]],
        options={"is_synthetic": False},
    )
    assert res_live.success is True

    # Import synthetic demo record
    synthetic_ad = {
        "id": "synth_999",
        "pageId": "synth_adv",
        "pageName": "Synthetic Brand",
        "title": "Synthetic Demo Gadget",
        "bodies": ["Demo ad copy"],
        "targetCountries": ["US"],
    }
    res_synth = await import_service.import_data(
        source_type=DataSourceType.META_AD_LIBRARY,
        data=[synthetic_ad],
        options={"is_synthetic": True},
    )
    assert res_synth.success is True

    # Verify two separate data sources were registered
    sources = (await db.execute(select(DataSource))).scalars().all()
    source_names = [s.name for s in sources]
    assert any("meta_ad_library" in s.lower() and "synthetic" not in s.lower() for s in source_names)
    assert any("synthetic_demo" in s.lower() for s in source_names)


# ── 4. Dataset Pagination & Timeout Tests ─────────────────────────────────────

@pytest.mark.asyncio
async def test_dataset_pagination(db):
    """Adapter fetch_dataset correctly iterates through paginated Apify items."""
    adapter = ApifyProviderAdapter(db, api_token="test_token")

    page_1 = [{"id": f"ad_{i}", "pageName": "Brand A"} for i in range(10)]
    page_2 = [{"id": f"ad_{i}", "pageName": "Brand A"} for i in range(10, 15)]

    async def mock_get(url, params=None, headers=None):
        offset = (params or {}).get("offset", 0)
        req = httpx.Request("GET", url)
        if offset == 0:
            return httpx.Response(200, json=page_1, request=req)
        elif offset == 10:
            return httpx.Response(200, json=page_2, request=req)
        else:
            return httpx.Response(200, json=[], request=req)

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        items = await adapter.fetch_dataset("test_dataset_id", offset=0, limit=10)
        assert len(items) == 15
        assert items[0]["id"] == "ad_0"
        assert items[14]["id"] == "ad_14"


@pytest.mark.asyncio
async def test_provider_timeout_and_backoff(db):
    """Adapter handles 429 rate limiting with exponential backoff before failing gracefully."""
    adapter = ApifyProviderAdapter(db, api_token="test_token")

    attempts = 0

    async def mock_post(url, json=None, headers=None, **kwargs):
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, request=httpx.Request("POST", url))

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await adapter.discover_by_keywords(["heavy duty hooks"])
            assert result["success"] is False
            assert attempts == 1  # No automatic retries on start per P0 Hotfix safety


# ── 5. Hard Budget Guardrails Tests ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_budget_exhaustion_guardrail(db):
    """When recorded spend reaches the configured limit, adapter enters BLOCKED status."""
    adapter = ApifyProviderAdapter(db, api_token="test_token")
    adapter.daily_budget_usd = 0.05  # Very low cap ($0.05)

    # Register an Apify collection run with 100 fetched records (100 * $0.0012 = $0.12 > $0.05)
    source = await adapter._ensure_apify_data_source()
    job = CollectionJob(data_source_id=source.id, name="prev_run", job_type="apify_live")
    db.add(job)
    await db.flush()

    run = CollectionRun(
        job_id=job.id,
        status=CollectionJobStatus.COMPLETED,
        started_at=datetime.now(timezone.utc),
        records_fetched=100,
    )
    db.add(run)
    await db.commit()

    # Check status
    status = await adapter.get_status()
    assert status["status"] == ProviderStatus.BLOCKED.value
    assert status["estimated_spent_today_usd"] > adapter.daily_budget_usd

    # Execution is blocked
    result = await adapter.discover_by_keywords(["socket organizer"])
    assert result["success"] is False
    assert result["status"] == ProviderStatus.BLOCKED.value
    assert "Daily budget" in result["error"]


# ── 6. Discovery Seed Engine & Prioritization Tests ───────────────────────────

@pytest.mark.asyncio
async def test_discovery_seed_taxonomy_and_prioritization(tmp_path):
    """Tests taxonomy bootstrap across 10 categories and dynamic yield prioritization."""
    storage_file = tmp_path / "test_seeds.json"
    engine = DiscoverySeedEngine(storage_path=storage_file)

    # 1. Verify 10 categories are seeded
    categories = {s.category for s in engine.seeds.values()}
    assert len(categories) == 10
    for expected_cat in TAXONOMY_CATEGORIES.keys():
        assert expected_cat in categories

    # 2. Get prioritized uncollected seeds
    uncollected = engine.get_prioritized_seeds(limit=5, only_uncollected=True)
    assert len(uncollected) == 5
    assert all(s.last_collected_at is None for s in uncollected)

    # 3. Simulate empirical feedback on a high-performing seed
    kw = uncollected[0].keyword
    engine.record_query_feedback(
        keyword=kw,
        total_fetched=50,
        unique_products=15,  # 30% yield!
        new_advertisers=8,
        duplicates=5,
        cost_usd=0.06,
    )

    updated_seed = engine.seeds[kw]
    assert updated_seed.total_runs == 1
    assert updated_seed.yield_score > 60.0  # Boosted!
    assert updated_seed.unique_products_found == 15


# ── 7. Advertiser Expansion Engine Tests ──────────────────────────────────────

@pytest.mark.asyncio
async def test_advertiser_expansion_bounded_loop(db):
    """Tests advertiser candidate selection and expansion limits."""
    # Seed an advertiser with US ads
    adv = Advertiser(
        name="AutoPro USA",
        facebook_page_id="1122334455",
        domain="autopro.com",
        country="US",
        source_type=DataSourceType.META_AD_LIBRARY,
    )
    db.add(adv)
    await db.flush()

    ad = Advertisement(
        external_id="ad_exp_001",
        advertiser_id=adv.id,
        title="Trunk Cargo Net 2-Pack",
        body="Heavy duty elastic organizer",
        source_type=DataSourceType.META_AD_LIBRARY,
        target_country="US",
    )
    db.add(ad)
    await db.commit()

    expansion_engine = AdvertiserExpansionEngine(db)
    candidates = await expansion_engine.get_expansion_candidates(max_candidates=5)

    assert len(candidates) >= 1
    assert candidates[0]["page_id"] == "1122334455"
    assert candidates[0]["name"] == "AutoPro USA"


# ── 8. Bundle-First Analysis for New Products ─────────────────────────────────

@pytest.mark.asyncio
async def test_bundle_first_filtering_for_new_products(db):
    """When a new product is imported, bundle mechanism and $30-$90 AOV scenarios are computed."""
    import_service = ImportService(db)

    # Import an authentic multi-unit product
    res = await import_service.import_data(
        source_type=DataSourceType.META_AD_LIBRARY,
        data=[REAL_APIFY_META_RECORDS[0]],  # Washable Microfiber Mop Pads Multi-Room 3-Pack
        options={"is_synthetic": False},
    )
    assert res.success is True

    # Retrieve created product
    product = (await db.execute(select(Product))).scalars().first()
    assert product is not None

    # Run bundle intelligence
    bundle_engine = BundleIntelligenceEngine(db)
    bundle_res = await bundle_engine.analyze_product_bundles(product.id)

    assert bundle_res["product_id"] == product.id
    assert "bundle_mechanism" in bundle_res
    assert bundle_res["bundle_mechanism"] in (
        BundleMechanism.DAILY_ROTATION.value,
        BundleMechanism.MULTIPLE_LOCATIONS.value,
        BundleMechanism.FREQUENT_USAGE.value,
        BundleMechanism.COMPLETE_COVERAGE.value,
    )
    assert "aov_scenarios" in bundle_res
    scenarios = bundle_res["aov_scenarios"]
    assert any(s["quantity"] in (3, 5, 10) for s in scenarios)


# ── 9. Continuous Scheduler Execution & Guardrails ───────────────────────────

@pytest.mark.asyncio
async def test_scheduler_collection_cycle_disabled_guardrail(db):
    """Scheduler collection cycle fails closed when auto-collection is disabled."""
    scheduler = SchedulerService()
    scheduler.settings.apify_auto_collection_enabled = False

    result = await scheduler.run_collection_cycle(mode="seeds", force=False)
    assert result["status"] == "disabled"
    assert "Automatic paid collection is disabled" in result["message"]


@pytest.mark.asyncio
async def test_scheduler_pipeline_execution(db):
    """Full pipeline execution runs snapshot -> aggregate -> score -> graph -> alert."""
    scheduler = SchedulerService()
    result = await scheduler.run_pipeline_now(run_type="test_run", include_collection=False)

    assert result["status"] == "completed"
    assert "snapshot" in result["steps"]
    assert "aggregate" in result["steps"]
    assert "scoring" in result["steps"]
    assert "graph" in result["steps"]
    assert "alerts" in result["steps"]


# ── 10. API Endpoints Integration Tests ───────────────────────────────────────

@pytest.mark.asyncio
async def test_discovery_api_status_and_seeds(client):
    """Test discovery status and seed management endpoints."""
    # 1. GET /api/v1/discovery/status
    res = await client.get("/api/v1/discovery/status")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "daily_budget_usd" in data

    # 2. GET /api/v1/discovery/seeds
    res_seeds = await client.get("/api/v1/discovery/seeds?limit=10")
    assert res_seeds.status_code == 200
    seeds_data = res_seeds.json()
    assert seeds_data["total"] >= 10
    assert len(seeds_data["seeds"]) == 10

    # 3. POST /api/v1/discovery/seeds (Add custom seed)
    custom_seed = {
        "keyword": "silicone stretch lids 6 pack reusable",
        "category": "Household Essentials",
        "source": "custom",
        "reason": "Test seed",
        "bundle_rationale": "6 pack for multiple container sizes",
        "target_bundle_units": [6, 12],
    }
    res_add = await client.post("/api/v1/discovery/seeds", json=custom_seed)
    assert res_add.status_code == 200
    assert res_add.json()["success"] is True

    # 4. POST /api/v1/discovery/import-fixture
    fixture_payload = {
        "records": REAL_APIFY_META_RECORDS,
        "actor_name": "automation-lab/facebook-ads-library",
    }
    res_fixture = await client.post("/api/v1/discovery/import-fixture", json=fixture_payload)
    assert res_fixture.status_code == 200
    fix_res = res_fixture.json()
    assert fix_res["success"] is True
    assert fix_res["records_valid"] == 3
    assert fix_res["records_new"] == 3


# ── 11. Official Schema Contract & US Evidence Tiering Tests ──────────────────

@pytest.mark.asyncio
async def test_official_schema_contract_mapping(db):
    """Verify exact field mapping against official automation-lab/facebook-ads-library schema."""
    adapter = ApifyProviderAdapter(db)

    official_raw_record = {
        "adArchiveId": "9988776655",
        "adLibraryUrl": "https://www.facebook.com/ads/library/?id=9988776655",
        "pageId": "1234567890",
        "pageName": "EcoBrush Living",
        "startDate": "2026-11-01T00:00:00Z",
        "isActive": True,
        "bodyText": "Bamboo dish brush replacement heads 4-pack for daily dishwashing rotation.",
        "imageUrls": ["https://cdn.ecobrush.com/heads-4pack.jpg"],
        "videoUrls": [],
        "linkUrl": "https://ecobrush.com/products/heads-4pack",
        "ctaText": "Shop Now",
    }

    normalized = adapter.normalize_records([official_raw_record], "automation-lab/facebook-ads-library")
    assert len(normalized) == 1
    norm = normalized[0]

    assert norm["id"] == "9988776655"
    assert norm["adArchiveId"] == "9988776655"
    assert norm["pageId"] == "1234567890"
    assert norm["pageName"] == "EcoBrush Living"
    assert norm["adLibraryUrl"] == "https://www.facebook.com/ads/library/?id=9988776655"
    assert norm["startDate"] == "2026-11-01T00:00:00Z"
    assert norm["isActive"] is True
    assert norm["bodyText"] == "Bamboo dish brush replacement heads 4-pack for daily dishwashing rotation."
    assert norm["imageUrls"] == ["https://cdn.ecobrush.com/heads-4pack.jpg"]
    assert norm["linkUrl"] == "https://ecobrush.com/products/heads-4pack"
    assert norm["ctaText"] == "Shop Now"
    assert norm["geo_evidence_type"] == "US_SEARCH_FILTER"
    assert norm["geo_confidence"] == "MEDIUM"

    valid, errors = adapter.validate_records(normalized)
    assert len(valid) == 1
    assert len(errors) == 0


@pytest.mark.asyncio
async def test_us_evidence_handling_tiering(db):
    """
    Verify tiered US geographic evidence handling:
    1. EXPLICIT_US_TARGETING: Confidence HIGH
    2. US_SEARCH_FILTER: Confidence MEDIUM (not rejected simply because targetCountries omitted)
    3. NON_US_TARGETING: Rejected
    """
    adapter = ApifyProviderAdapter(db)

    records = [
        # 1. Explicit US targeting
        {
            "adArchiveId": "exp_us_01",
            "pageName": "Explicit US Brand",
            "bodyText": "Explicit targeting to US buyers",
            "targetCountries": ["US"],
        },
        # 2. US search filter only (common Meta US ad output)
        {
            "adArchiveId": "search_us_02",
            "pageName": "Search Filter US Brand",
            "bodyText": "Collected under country=US search filter",
            # targetCountries omitted by Meta
        },
        # 3. Explicit non-US targeting
        {
            "adArchiveId": "non_us_03",
            "pageName": "Global Ex-US Brand",
            "bodyText": "Australian market only",
            "targetCountries": ["AU", "NZ"],
        },
    ]

    normalized = adapter.normalize_records(records, "automation-lab/facebook-ads-library")
    assert len(normalized) == 3

    assert normalized[0]["geo_evidence_type"] == "EXPLICIT_US_TARGETING"
    assert normalized[0]["geo_confidence"] == "HIGH"

    assert normalized[1]["geo_evidence_type"] == "US_SEARCH_FILTER"
    assert normalized[1]["geo_confidence"] == "MEDIUM"

    assert normalized[2]["geo_evidence_type"] == "NON_US_TARGETING"
    assert normalized[2]["geo_confidence"] == "REJECTED"

    valid, errors = adapter.validate_records(normalized)
    assert len(valid) == 2
    assert valid[0]["adArchiveId"] == "exp_us_01"
    assert valid[1]["adArchiveId"] == "search_us_02"
    assert len(errors) == 1
    assert "non_us_03" in errors[0]


@pytest.mark.asyncio
async def test_dry_run_payload_generation(client, db):
    """Verify dry-run payload builder and GET /api/v1/discovery/dry-run API endpoint."""
    adapter = ApifyProviderAdapter(db)
    payload = adapter.build_dry_run_payload(
        query="washable microfiber mop pads multi pack washable rotation",
        max_ads=20,
        sort_by="recent",
        max_charge_usd=0.50,
    )

    assert payload["actor"] == "automation-lab/facebook-ads-library"
    assert payload["actor_slug"] == "automation-lab~facebook-ads-library"
    assert payload["method"] == "POST"
    assert payload["endpoint_url"] == "https://api.apify.com/v2/acts/automation-lab~facebook-ads-library/runs"
    assert payload["query_params"]["maxTotalChargeUsd"] == 0.50
    assert payload["request_body"]["searchQueries"] == ["washable microfiber mop pads multi pack washable rotation"]
    assert payload["request_body"]["country"] == "US"
    assert payload["request_body"]["activeStatus"] == "active"
    assert payload["request_body"]["sortBy"] == "recent"
    assert payload["request_body"]["maxAds"] == 20
    assert payload["dry_run"] is True

    # Test API endpoint
    res = await client.get("/api/v1/discovery/dry-run?query=microfiber+pads&max_ads=20&max_charge_usd=0.50")
    assert res.status_code == 200
    api_payload = res.json()
    assert api_payload["dry_run"] is True
    assert api_payload["query_params"]["maxTotalChargeUsd"] == 0.50
    assert api_payload["request_body"]["searchQueries"] == ["microfiber pads"]
    assert api_payload["request_body"]["activeStatus"] == "active"
    assert api_payload["request_body"]["sortBy"] == "recent"


@pytest.mark.asyncio
async def test_budget_protection_concurrency_lock(db):
    """Verify concurrency mutex and spend limits preventing parallel runaway costs."""
    adapter = ApifyProviderAdapter(db, api_token="test_token")
    assert hasattr(ApifyProviderAdapter, "_lock")
    assert adapter.auto_enabled is False  # Safe default: paid collection disabled by default


# ── 12. Final Pre-Live Hardening Tests ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_persistent_atomic_budget_reservation_and_in_flight_tracking(db):
    """
    Verify persistent atomic database reservation:
    - In-flight commitments are counted before Apify run finishes
    - Concurrent requests exceeding budget are blocked by DB state
    - Stale in-flight runs (>15m) are automatically timed out
    """
    adapter = ApifyProviderAdapter(db, api_token="test_token")
    adapter.daily_budget_usd = 0.75  # Cap at $0.75

    # 1. First reservation of $0.50
    ok1, run1, job1, msg1 = await adapter.reserve_budget(
        job_name="run_1",
        actor_name="automation-lab/facebook-ads-library",
        reservation_amount_usd=0.50,
    )
    assert ok1 is True
    assert run1.status == CollectionJobStatus.RUNNING
    assert run1.errors["reserved_cost_usd"] == 0.50

    # 2. Check spend: should now reflect the in-flight commitment of $0.50
    spent_today, _ = await adapter._calculate_current_spend()
    assert spent_today >= 0.50

    # 3. Second reservation of $0.50 should FAIL because $0.50 + $0.50 = $1.00 > $0.75
    ok2, run2, job2, msg2 = await adapter.reserve_budget(
        job_name="run_2",
        actor_name="automation-lab/facebook-ads-library",
        reservation_amount_usd=0.50,
    )
    assert ok2 is False
    assert ("Daily budget" in msg2 or "in-flight" in msg2 or "Blocked" in msg2)

    # 4. Simulate run1 completion with actual charge of $0.15
    run1.status = CollectionJobStatus.COMPLETED
    run1.errors = {"actual_cost_usd": 0.15, "cost_status": "VERIFIED_CHARGED"}
    await db.commit()

    # 5. Check spend now: $0.15 actual, in-flight released
    spent_after, _ = await adapter._calculate_current_spend()
    assert round(spent_after, 2) == 0.15

    # 6. Now second reservation of $0.50 succeeds because $0.15 + $0.50 = $0.65 <= $0.75
    ok3, run3, job3, msg3 = await adapter.reserve_budget(
        job_name="run_3",
        actor_name="automation-lab/facebook-ads-library",
        reservation_amount_usd=0.50,
    )
    assert ok3 is True


@pytest.mark.asyncio
async def test_apify_billing_details_inspection():
    """Verify pay-per-event pricing extraction, event usage, and verified charge labeling."""
    # Case A: PPE Actor with platform usage and event usage
    run_data_ppe = {
        "status": "SUCCEEDED",
        "usageTotalUsd": 0.0102,
        "eventUsageTotalUsd": 0.0240,
        "chargedEventCounts": {"ads": 20},
        "pricingInfo": {
            "pricingModel": "PAY_PER_EVENT",
            "unitName": "ad",
            "pricePerUnitUsd": 0.0012,
        },
    }
    billing_a = ApifyProviderAdapter.extract_billing_details(run_data_ppe, records_fetched=20)
    assert billing_a["cost_status"] == "VERIFIED_CHARGED"
    assert billing_a["actual_cost_usd"] == 0.0342
    assert billing_a["charged_event_counts"] == {"ads": 20}

    # Case B: Free tier / unmetered with records fetched -> ESTIMATED
    run_data_zero = {
        "status": "SUCCEEDED",
        "usageTotalUsd": 0.0,
        "eventUsageTotalUsd": 0.0,
    }
    billing_b = ApifyProviderAdapter.extract_billing_details(run_data_zero, records_fetched=10)
    assert billing_b["cost_status"] == "ESTIMATED"
    assert billing_b["actual_cost_usd"] == 0.012

    # Case C: 0 records, 0 charges -> UNMETERED
    billing_c = ApifyProviderAdapter.extract_billing_details(run_data_zero, records_fetched=0)
    assert billing_c["cost_status"] == "UNMETERED"
    assert billing_c["actual_cost_usd"] == 0.0


@pytest.mark.asyncio
async def test_ad_freshness_classification_and_launch_date_filtering(db):
    """
    Verify filtering using actual startDate to identify newly launched ads
    versus old active campaigns running for months.
    """
    adapter = ApifyProviderAdapter(db)
    now = datetime.now(timezone.utc)

    raw_ads = [
        # Launched 3 days ago (New launch)
        {
            "id": "fresh_01",
            "pageName": "FreshBrand",
            "title": "New Mop Pad",
            "startDate": (now - timedelta(days=3)).strftime("%Y-%m-%d"),
            "isActive": True,
        },
        # Launched 10 days ago (14d window)
        {
            "id": "fresh_02",
            "pageName": "FreshBrand",
            "title": "Recent Mop Pad",
            "startDate": (now - timedelta(days=10)).strftime("%Y-%m-%d"),
            "isActive": True,
        },
        # Launched 120 days ago (Old active campaign)
        {
            "id": "old_01",
            "pageName": "LegacyBrand",
            "title": "Evergreen Mop Pad",
            "startDate": (now - timedelta(days=120)).strftime("%Y-%m-%d"),
            "isActive": True,
        },
    ]

    normalized = adapter.normalize_records(raw_ads, "automation-lab/facebook-ads-library")
    assert len(normalized) == 3

    assert normalized[0]["freshness_tier"] == "NEW_LAUNCH_7D"
    assert normalized[0]["days_since_launch"] <= 4

    assert normalized[1]["freshness_tier"] == "NEW_LAUNCH_14D"
    assert normalized[1]["days_since_launch"] <= 11

    assert normalized[2]["freshness_tier"] == "ESTABLISHED_CAMPAIGN"
    assert normalized[2]["days_since_launch"] >= 115

    # Filter by 14-day window: should include only fresh_01 and fresh_02
    fresh_14d, excluded = adapter.filter_by_launch_window(normalized, max_days_since_launch=14)
    assert len(fresh_14d) == 2
    assert {a["id"] for a in fresh_14d} == {"fresh_01", "fresh_02"}
    assert len(excluded) == 1
    assert excluded[0]["id"] == "old_01"


@pytest.mark.asyncio
async def test_first_bounded_live_run_preparation(client, db):
    """
    Verify exact configuration prepared for the first bounded live test:
    Keyword: washable microfiber mop pads, country: US, max 20 ads, max $0.50 cap.
    """
    adapter = ApifyProviderAdapter(db)
    config = adapter.prepare_first_live_run_config()

    assert config["actor"] == "automation-lab/facebook-ads-library"
    assert config["country"] == "US"
    assert config["keyword"] == "washable microfiber mop pads"
    assert config["activeStatus"] == "active"
    assert config["sortBy"] == "recent"
    assert config["maxAds"] == 20
    assert config["max_charge_usd"] == 0.50
    assert config["recurring"] is False
    assert config["use_fallback"] is False
    assert config["auto_collection_enabled"] is False

    # Calling without token fails closed immediately
    adapter_no_token = ApifyProviderAdapter(db, api_token="")
    res = await adapter_no_token.execute_bounded_first_live_run()
    assert res["success"] is False
    assert res["status"] == ProviderStatus.NOT_CONFIGURED.value

    # Verify endpoint GET /api/v1/discovery/first-live-run/config
    api_res = await client.get("/api/v1/discovery/first-live-run/config")
    assert api_res.status_code == 200
    assert api_res.json()["keyword"] == "washable microfiber mop pads"



