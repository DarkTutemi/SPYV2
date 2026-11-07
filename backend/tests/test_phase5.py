"""
US WIN HUNTER — Phase 5: Pain Discovery & Trends Tests

Tests for:
- GoogleTrendsAdapter observation & trajectory
- PainDiscoveryService language group classification
- Pain cluster ingestion and evidence categorization
- Pain discovery and trends API endpoints
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import Base, engine, async_session_factory
from app.adapters.trends import GoogleTrendsAdapter
from app.services.pain_service import PainDiscoveryService
from app.models.models import (
    DataSourceType,
    PainCluster,
    PainEvidence,
    PainLanguageGroup,
    TrendObservation,
)


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


class TestGoogleTrendsAdapter:

    @pytest.mark.asyncio
    async def test_observe_and_trajectory(self, db):
        adapter = GoogleTrendsAdapter(db)
        obs = await adapter.observe_keyword_interest(
            keyword="magnetic cable clips",
            observation_date="2026-11-01",
            mock_interest=75.5,
        )
        assert obs.keyword == "magnetic cable clips"
        assert obs.interest_value == 75.5
        assert obs.geographic_scope == "US"

        # Trajectory
        traj = await adapter.get_keyword_trajectory("magnetic cable clips")
        assert len(traj) == 1
        assert traj[0]["interest"] == 75.5


class TestPainDiscoveryService:

    def test_language_group_classification(self):
        service = PainDiscoveryService(None)
        # Product failure
        assert service._classify_language_group("The zipper broke after 2 days") == PainLanguageGroup.PRODUCT_FAILURE
        # Failed workaround
        assert service._classify_language_group("I tried using duct tape as a workaround") == PainLanguageGroup.FAILED_WORKAROUND
        # Purchase intent
        assert service._classify_language_group("Looking for a good durable sponge to buy") == PainLanguageGroup.PURCHASE_INTENT
        # Product replacement
        assert service._classify_language_group("Replacing my old worn out kitchen towels") == PainLanguageGroup.PRODUCT_REPLACEMENT
        # General complaint
        assert service._classify_language_group("This is so annoying and frustrating") == PainLanguageGroup.COMPLAINT

    @pytest.mark.asyncio
    async def test_import_evidence_and_cluster(self, db):
        service = PainDiscoveryService(db)
        cluster = await service.import_evidence_and_cluster(
            cluster_name="Smelly Kitchen Sponges",
            core_problem="Traditional cellulose sponges trap bacteria and smell bad within days",
            category="Kitchen & Home",
            evidence_items=[
                {
                    "content_excerpt": "My sponge smells like mildew after just 3 days of washing dishes",
                    "source_url": "https://example.com/reddit/1",
                    "author_id": "user_a",
                },
                {
                    "content_excerpt": "Looking for a silicone sponge that doesn't hold odors",
                    "source_url": "https://example.com/reddit/2",
                    "author_id": "user_b",
                },
            ],
            product_hypotheses=["Quick-drying silicone scrubber multi-pack for rotation"],
            search_keywords=["silicone kitchen sponge", "odor free sponge"],
        )

        assert cluster.name == "Smelly Kitchen Sponges"
        assert cluster.distinct_source_count == 2
        assert cluster.distinct_author_count == 2

        # Verify detail
        detail = await service.get_cluster_detail(cluster.id)
        assert detail is not None
        assert len(detail["evidence"]) == 2
        assert len(detail["hypotheses"]) == 1
        assert len(detail["keywords"]) == 2


@pytest.mark.asyncio
async def test_pain_api_endpoints(client, db):
    # Import cluster
    payload = {
        "cluster_name": "Tangled Charging Cables",
        "core_problem": "Messy desk and car cables getting tangled and dropping behind furniture",
        "category": "Electronics & Accessories",
        "evidence_items": [
            {
                "content_excerpt": "Cables constantly fall behind my nightstand and desk",
                "source_url": "https://example.com/discussion/101",
                "author_id": "author_x",
            }
        ],
        "product_hypotheses": ["Magnetic cable organizer clips for car and desk"],
        "search_keywords": ["magnetic cable clips", "desk cable organizer"],
    }
    res = await client.post("/api/v1/pain/import", json=payload)
    assert res.status_code == 201
    cluster_id = res.json()["id"]

    # List clusters
    list_res = await client.get("/api/v1/pain/clusters")
    assert list_res.status_code == 200
    clusters = list_res.json()
    assert len(clusters) >= 1

    # Detail
    detail_res = await client.get(f"/api/v1/pain/clusters/{cluster_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["name"] == "Tangled Charging Cables"

    # Trends lookup endpoint
    trends_res = await client.get("/api/v1/pain/trends/magnetic%20cable%20clips")
    assert trends_res.status_code == 200
    trends_body = trends_res.json()
    assert trends_body["keyword"] == "magnetic cable clips"
    assert trends_body["geo"] == "US"
    assert len(trends_body["trajectory"]) >= 1
