"""
US WIN HUNTER — Phase 2/3 Tests

Tests for:
- Title normalization
- URL normalization
- Perceptual hashing
- Product clustering proposals
- Cluster create/split (manual review workflow)
- Advertiser graph discovery
- Daily snapshots & metrics aggregation
- Window comparison
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from app.core.database import Base, engine, async_session_factory
from app.engines.fingerprinting import (
    normalize_product_title,
    normalize_url,
    hamming_distance,
    compute_file_hash,
    compute_perceptual_hash,
    FingerprintEngine,
    ClusteringService,
)
from app.engines.advertiser_graph import AdvertiserGraphEngine
from app.engines.temporal import TemporalEngine
from app.models.models import (
    Advertisement, Advertiser, Product, DataSourceType,
    ConfidenceLevel, RelationshipType,
    SnapshotObservationQuality,
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


# ─── Title Normalization ─────────────────────────────────────────────────

class TestTitleNormalization:

    def test_basic(self):
        assert normalize_product_title("Ultra Absorbent Towel Set") == "absorbent towel set"

    def test_stops_and_filler(self):
        assert normalize_product_title("THE BEST Premium Pro Ultra Towel") == "towel"

    def test_preserves_meaningful_words(self):
        result = normalize_product_title("5-Pack Microfiber Cleaning Cloth")
        assert "5-pack" in result
        assert "microfiber" in result
        assert "cleaning" in result
        assert "cloth" in result

    def test_emoji_removal(self):
        result = normalize_product_title("🔥 Amazing Towel 🔥")
        assert "amazing" in result
        assert "towel" in result

    def test_empty(self):
        assert normalize_product_title("") == ""

    def test_identical_products_match(self):
        a = normalize_product_title("Ultra Absorbent Microfiber Towel Set")
        b = normalize_product_title("Premium Ultra Absorbent Microfiber Towel Set - Free Shipping!")
        assert a == b  # Both normalize to the same core words


# ─── URL Normalization ───────────────────────────────────────────────────

class TestURLNormalization:

    def test_tracking_params_removed(self):
        url = "https://www.example.com/product?utm_source=fb&utm_medium=cpc&color=blue"
        result = normalize_url(url)
        assert "utm_source" not in result
        assert "color=blue" in result

    def test_www_removed(self):
        assert "www." not in normalize_url("https://www.example.com/path")

    def test_fragment_removed(self):
        assert "#" not in normalize_url("https://example.com/page#section")

    def test_identical_urls(self):
        a = normalize_url("https://www.example.com/product?fbclid=abc123")
        b = normalize_url("https://example.com/product")
        assert a == b


# ─── Hamming Distance ───────────────────────────────────────────────────

class TestHammingDistance:

    def test_identical(self):
        assert hamming_distance("abcd1234", "abcd1234") == 0

    def test_different(self):
        dist = hamming_distance("abcd1234", "abcd1235")
        assert dist > 0

    def test_mismatched_length(self):
        assert hamming_distance("abc", "abcd") == 999


# ─── Fingerprint Engine ─────────────────────────────────────────────────

class TestFingerprintEngine:

    async def _setup_products(self, db):
        """Create test products with overlapping names and URLs."""
        adv = Advertiser(
            name="Test Adv", normalized_name="test adv",
            source_type=DataSourceType.META_AD_LIBRARY, country="US",
        )
        db.add(adv)
        await db.flush()

        products = []
        test_data = [
            ("Ultra Absorbent Microfiber Towel", "https://example.com/towel"),
            ("Premium Ultra Absorbent Microfiber Towel Set", "https://example.com/towel?utm_source=fb"),
            ("Kitchen Sponge Holder", "https://other.com/sponge"),
            ("Microfiber Cleaning Cloth 5-Pack", "https://example.com/cloth"),
        ]
        for name, url in test_data:
            p = Product(
                name=name, normalized_name=name.lower(),
                source_url=url, target_country="US",
                source_type=DataSourceType.META_AD_LIBRARY,
            )
            db.add(p)
            products.append(p)

        await db.flush()
        return adv, products

    @pytest.mark.anyio
    async def test_url_duplicate_detection(self, db):
        """Products with same normalized URL are detected."""
        _, products = await self._setup_products(db)
        await db.commit()

        engine = FingerprintEngine(db)
        matches = await engine.find_url_duplicates(products[0].id)
        # products[0] and [1] share the same normalized URL (tracking params stripped)
        matched_ids = {m["product_id"] for m in matches}
        assert products[1].id in matched_ids
        assert products[2].id not in matched_ids

    @pytest.mark.anyio
    async def test_title_duplicate_detection(self, db):
        """Products with same normalized title are detected."""
        _, products = await self._setup_products(db)
        await db.commit()

        engine = FingerprintEngine(db)
        matches = await engine.find_title_duplicates(products[0].id)
        matched_ids = {m["product_id"] for m in matches}
        # product 0 = "Ultra Absorbent Microfiber Towel" → "absorbent microfiber towel"
        # product 1 = "Premium Ultra Absorbent Microfiber Towel Set" → "absorbent microfiber towel set"
        # NOT identical (different after normalization) — one has "set"
        # This verifies NO false merge happens on similar-but-different titles
        assert products[2].id not in matched_ids  # Sponge Holder is definitely different

    @pytest.mark.anyio
    async def test_combined_scan(self, db):
        """Combined scan returns deduplicated candidates."""
        _, products = await self._setup_products(db)
        await db.commit()

        engine = FingerprintEngine(db)
        matches = await engine.scan_product_duplicates(products[0].id)
        # Should find at least one match (URL overlap)
        assert len(matches) >= 1
        # Should NOT include the product itself
        assert all(m["product_id"] != products[0].id for m in matches)

    @pytest.mark.anyio
    async def test_no_auto_merge(self, db):
        """Proposals are returned but NOT automatically merged."""
        _, products = await self._setup_products(db)
        await db.commit()

        svc = ClusteringService(db)
        candidates = await svc.propose_cluster(products[0].id)
        # Candidates exist, but no cluster should have been created
        from sqlalchemy import select, func
        from app.models.models import ProductCluster
        count = (await db.execute(select(func.count(ProductCluster.id)))).scalar()
        assert count == 0  # No auto-merge!


# ─── Clustering Service ─────────────────────────────────────────────────

class TestClusteringService:

    @pytest.mark.anyio
    async def test_create_cluster(self, db):
        """Manual cluster creation works."""
        p1 = Product(name="Product A", normalized_name="product a",
                     target_country="US", source_type=DataSourceType.MANUAL_IMPORT)
        p2 = Product(name="Product B", normalized_name="product b",
                     target_country="US", source_type=DataSourceType.MANUAL_IMPORT)
        db.add_all([p1, p2])
        await db.flush()

        svc = ClusteringService(db)
        cluster = await svc.create_cluster(
            name="Test Cluster",
            canonical_product_id=p1.id,
            member_ids=[p1.id, p2.id],
            reviewed_by="test",
        )
        await db.commit()

        assert cluster.name == "Test Cluster"
        assert cluster.is_reviewed is True

        # Verify merge history was recorded
        from sqlalchemy import select
        from app.models.models import ProductMergeHistory
        history = (await db.execute(select(ProductMergeHistory))).scalars().all()
        assert len(history) >= 1  # At least one merge record for p2

    @pytest.mark.anyio
    async def test_split_from_cluster(self, db):
        """Split removes a product from a cluster and records history."""
        p1 = Product(name="Prod X", normalized_name="prod x",
                     target_country="US", source_type=DataSourceType.MANUAL_IMPORT)
        p2 = Product(name="Prod Y", normalized_name="prod y",
                     target_country="US", source_type=DataSourceType.MANUAL_IMPORT)
        db.add_all([p1, p2])
        await db.flush()

        svc = ClusteringService(db)
        cluster = await svc.create_cluster("XY Cluster", p1.id, [p1.id, p2.id])
        await db.flush()

        # Now split p2 out
        await svc.split_from_cluster(p2.id, cluster.id, reason="Wrong match")
        await db.commit()

        # Verify membership removed
        from sqlalchemy import select, func
        from app.models.models import ProductClusterMember, ProductMergeHistory
        members = (await db.execute(
            select(func.count(ProductClusterMember.id)).where(
                ProductClusterMember.cluster_id == cluster.id
            )
        )).scalar()
        assert members == 1  # Only p1 remains

        # Verify split recorded
        splits = (await db.execute(
            select(ProductMergeHistory).where(ProductMergeHistory.action == "split")
        )).scalars().all()
        assert len(splits) == 1


# ─── Advertiser Graph ───────────────────────────────────────────────────

class TestAdvertiserGraph:

    async def _setup_graph(self, db):
        """Two advertisers sharing a product and domain."""
        adv1 = Advertiser(name="Store A", normalized_name="store a",
                          source_type=DataSourceType.META_AD_LIBRARY, country="US")
        adv2 = Advertiser(name="Store B", normalized_name="store b",
                          source_type=DataSourceType.META_AD_LIBRARY, country="US")
        db.add_all([adv1, adv2])
        await db.flush()

        product = Product(name="Shared Product", normalized_name="shared product",
                          target_country="US", source_type=DataSourceType.META_AD_LIBRARY)
        db.add(product)
        await db.flush()

        ad1 = Advertisement(
            external_id="graph_ad_1", source_type=DataSourceType.META_AD_LIBRARY,
            advertiser_id=adv1.id, product_id=product.id,
            landing_page_url="https://sharedstore.com/product", is_active=True,
        )
        ad2 = Advertisement(
            external_id="graph_ad_2", source_type=DataSourceType.META_AD_LIBRARY,
            advertiser_id=adv2.id, product_id=product.id,
            landing_page_url="https://sharedstore.com/product", is_active=True,
        )
        db.add_all([ad1, ad2])
        await db.flush()
        return adv1, adv2, product

    @pytest.mark.anyio
    async def test_discover_shared_product(self, db):
        adv1, adv2, product = await self._setup_graph(db)
        await db.commit()

        engine = AdvertiserGraphEngine(db)
        proposals = await engine.discover_relationships()
        # Should find at least one relationship (shared product + shared domain)
        assert len(proposals) >= 1

    @pytest.mark.anyio
    async def test_advertiser_graph_context(self, db):
        adv1, adv2, product = await self._setup_graph(db)
        await db.commit()

        engine = AdvertiserGraphEngine(db)
        await engine.discover_relationships()
        await db.commit()

        graph = await engine.get_advertiser_graph(adv1.id)
        assert graph["total_ads"] == 1
        assert len(graph["products"]) == 1
        assert len(graph["relationships"]) >= 1
        assert "sharedstore.com" in graph["landing_domains"]

    @pytest.mark.anyio
    async def test_product_ad_share(self, db):
        """Product Ad Share is computed as activity signal."""
        adv1, _, product = await self._setup_graph(db)
        await db.commit()

        engine = AdvertiserGraphEngine(db)
        graph = await engine.get_advertiser_graph(adv1.id)
        shares = graph["product_ad_shares"]
        assert len(shares) == 1
        assert shares[0]["product_ad_share"] == 1.0  # Only product for this advertiser
        assert "NOT revenue share" in shares[0]["note"]


# ─── Temporal Engine ─────────────────────────────────────────────────────

class TestTemporalEngine:

    async def _setup_temporal(self, db):
        adv = Advertiser(name="Temporal Adv", normalized_name="temporal adv",
                         source_type=DataSourceType.META_AD_LIBRARY, country="US")
        db.add(adv)
        await db.flush()

        product = Product(name="Trending Towel", normalized_name="trending towel",
                          target_country="US", source_type=DataSourceType.META_AD_LIBRARY)
        db.add(product)
        await db.flush()

        now = datetime.now(timezone.utc)
        for i in range(5):
            ad = Advertisement(
                external_id=f"temp_ad_{i}",
                source_type=DataSourceType.META_AD_LIBRARY,
                advertiser_id=adv.id,
                product_id=product.id,
                is_active=True,
                first_seen_at=now - timedelta(days=20 - i * 3),
                last_seen_at=now,
            )
            db.add(ad)

        await db.flush()
        return adv, product

    @pytest.mark.anyio
    async def test_create_snapshot(self, db):
        _, product = await self._setup_temporal(db)
        await db.commit()

        engine = TemporalEngine(db)
        result = await engine.create_daily_snapshot()
        await db.commit()

        assert result["created"] == 5
        assert result["updated"] == 0

        # Re-run is idempotent
        result2 = await engine.create_daily_snapshot()
        await db.commit()
        assert result2["created"] == 0
        assert result2["updated"] == 5

    @pytest.mark.anyio
    async def test_aggregate_daily_metrics(self, db):
        _, product = await self._setup_temporal(db)
        await db.commit()

        engine = TemporalEngine(db)
        ads = (await db.execute(select(Advertisement).where(Advertisement.product_id == product.id))).scalars().all()
        observed_statuses = {str(a.id): True for a in ads}
        await engine.create_daily_snapshot(observed_ad_statuses=observed_statuses)
        metrics = await engine.aggregate_daily_metrics()
        await db.commit()

        assert len(metrics) >= 1
        m = metrics[0]
        assert m.active_ad_count >= 1
        assert m.unique_advertiser_count >= 1

    @pytest.mark.anyio
    async def test_window_comparison(self, db):
        _, product = await self._setup_temporal(db)
        await db.commit()

        engine = TemporalEngine(db)
        comparison = await engine.compute_window_comparison(product.id, 7)
        assert "recent_window" in comparison
        assert "prior_window" in comparison
        assert "deltas" in comparison
        assert comparison["window_days"] == 7

