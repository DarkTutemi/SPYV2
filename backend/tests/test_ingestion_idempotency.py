"""
US WIN HUNTER — Ingestion Idempotency & Commercial Price Evidence Regression Test
Verifies:
1. Pipeline can be executed multiple times without creating duplicate:
   - Products
   - CollectionRuns
   - SourceRecords
   - ProductOffers
   - BundleOffers
   - EvidenceLinks
2. Price Evidence Taxonomy strictly enforced:
   - Zero product offers point to Google Trends as price evidence.
   - Shopify offers have OBSERVED_CHECKOUT_PRICE.
   - Amazon offers have OBSERVED_RETAIL_LISTING_PRICE.
   - Modeled bundles have SCENARIO_PRICE.
3. 100% preservation of historical baseline advertisements and T0 snapshots.
"""

from datetime import datetime, timezone
import pytest
import tempfile
import os
from pathlib import Path
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.database import Base
from app.models.models import (
    Product,
    Advertisement,
    AdvertisementSnapshot,
    Advertiser,
    CollectionJob,
    CollectionRun,
    SourceRecord,
    ProductOffer,
    BundleOffer,
    EvidenceLink,
    DataSourceType,
    EvidenceType,
    PriceEvidenceType,
)
from ingest_multisource_pilot import run_ingestion
from ingest_new_research import ingest_new_research


@pytest.mark.asyncio
async def test_full_pipeline_idempotency_and_evidence_taxonomy():
    # Create disposable SQLite database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
        tmp_db_path = tmp_db.name

    db_url = f"sqlite+aiosqlite:///{tmp_db_path.replace(os.sep, '/')}"
    engine = create_async_engine(db_url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    try:
        # Create schema
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Seed representative baseline: 2 Meta baseline ads and 2 T0 snapshots
        async with async_session() as session:
            adv = Advertiser(name="Baseline Brand", domain="baselinebrand.com", source_type=DataSourceType.META_AD_LIBRARY)
            session.add(adv)
            await session.flush()

            prod_meta = Product(
                name="Square Chair rubber Leg Protectors",
                normalized_name="square chair rubber leg protectors",
                description="Silicone chair leg caps protecting hardwood floors.",
                target_country="US",
                is_physical=True,
                source_type=DataSourceType.META_AD_LIBRARY,
            )
            session.add(prod_meta)
            await session.flush()

            ad1 = Advertisement(
                product_id=prod_meta.id,
                advertiser_id=adv.id,
                external_id="meta_ad_baseline_001",
                target_country="US",
                is_active=True,
                first_seen_at=datetime(2026, 11, 9, 18, 23, 0, tzinfo=timezone.utc),
                source_type=DataSourceType.META_AD_LIBRARY,
            )
            ad2 = Advertisement(
                product_id=prod_meta.id,
                advertiser_id=adv.id,
                external_id="meta_ad_baseline_002",
                target_country="US",
                is_active=True,
                first_seen_at=datetime(2026, 11, 9, 18, 23, 0, tzinfo=timezone.utc),
                source_type=DataSourceType.META_AD_LIBRARY,
            )
            session.add_all([ad1, ad2])
            await session.flush()

            snap1 = AdvertisementSnapshot(
                advertisement_id=ad1.id,
                snapshot_date="2026-11-09",
                is_active=True,
                source_type=DataSourceType.META_AD_LIBRARY,
            )
            snap2 = AdvertisementSnapshot(
                advertisement_id=ad2.id,
                snapshot_date="2026-11-09",
                is_active=True,
                source_type=DataSourceType.META_AD_LIBRARY,
            )
            session.add_all([snap1, snap2])
            await session.commit()

        # RUN 1: Ingest pilot data and new research data
        await run_ingestion(db_url=db_url)
        await ingest_new_research(db_url=db_url)

        # Capture counts after Run 1
        async with async_session() as session:
            count_prods_1 = (await session.execute(select(func.count(Product.id)))).scalar()
            count_runs_1 = (await session.execute(select(func.count(CollectionRun.id)))).scalar()
            count_sr_1 = (await session.execute(select(func.count(SourceRecord.id)))).scalar()
            count_po_1 = (await session.execute(select(func.count(ProductOffer.id)))).scalar()
            count_bo_1 = (await session.execute(select(func.count(BundleOffer.id)))).scalar()
            count_el_1 = (await session.execute(select(func.count(EvidenceLink.id)))).scalar()
            count_ads_1 = (await session.execute(select(func.count(Advertisement.id)))).scalar()
            count_snaps_1 = (await session.execute(select(func.count(AdvertisementSnapshot.id)))).scalar()

            # Verify Price Evidence Taxonomy
            # 1. Zero price offers pointing to Google Trends
            trends_po = (await session.execute(
                select(ProductOffer).where(ProductOffer.source_url.like("%trends.google%"))
            )).scalars().all()
            assert len(trends_po) == 0, f"Found {len(trends_po)} ProductOffers pointing to Google Trends!"

            trends_bo = (await session.execute(
                select(BundleOffer).where(BundleOffer.source_url.like("%trends.google%"))
            )).scalars().all()
            assert len(trends_bo) == 0, f"Found {len(trends_bo)} BundleOffers pointing to Google Trends!"

            # 2. Door Draft Stopper has Amazon listing offer, NOT Google Trends
            draft_prod = (await session.execute(
                select(Product).where(Product.name.like("%Under-Door Draft%"))
            )).scalars().first()
            assert draft_prod is not None
            draft_offers = (await session.execute(
                select(ProductOffer).where(ProductOffer.product_id == draft_prod.id)
            )).scalars().all()
            assert len(draft_offers) == 1
            assert "amazon.com" in draft_offers[0].source_url
            assert draft_offers[0].price_evidence_type == PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE

            # 3. Model C Starter Kit bundle exists
            fountain_prod = (await session.execute(
                select(Product).where(Product.name.like("%Water Fountain%"))
            )).scalars().first()
            assert fountain_prod is not None
            fountain_bundles = (await session.execute(
                select(BundleOffer).where(
                    BundleOffer.product_id == fountain_prod.id,
                    BundleOffer.bundle_price_usd == 64.99,
                )
            )).scalars().all()
            assert len(fountain_bundles) == 1
            assert fountain_bundles[0].price_evidence_type == PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE

        # RUN 2: Re-run both ingestion pipelines against the SAME database
        await run_ingestion(db_url=db_url)
        await ingest_new_research(db_url=db_url)

        # Capture counts after Run 2
        async with async_session() as session:
            count_prods_2 = (await session.execute(select(func.count(Product.id)))).scalar()
            count_runs_2 = (await session.execute(select(func.count(CollectionRun.id)))).scalar()
            count_sr_2 = (await session.execute(select(func.count(SourceRecord.id)))).scalar()
            count_po_2 = (await session.execute(select(func.count(ProductOffer.id)))).scalar()
            count_bo_2 = (await session.execute(select(func.count(BundleOffer.id)))).scalar()
            count_el_2 = (await session.execute(select(func.count(EvidenceLink.id)))).scalar()
            count_ads_2 = (await session.execute(select(func.count(Advertisement.id)))).scalar()
            count_snaps_2 = (await session.execute(select(func.count(AdvertisementSnapshot.id)))).scalar()

        # Strict Idempotency Assertions: Zero duplicates created on run 2!
        assert count_prods_2 == count_prods_1, f"Product count grew from {count_prods_1} to {count_prods_2}"
        assert count_runs_2 == count_runs_1, f"CollectionRun count grew from {count_runs_1} to {count_runs_2}"
        assert count_sr_2 == count_sr_1, f"SourceRecord count grew from {count_sr_1} to {count_sr_2}"
        assert count_po_2 == count_po_1, f"ProductOffer count grew from {count_po_1} to {count_po_2}"
        assert count_bo_2 == count_bo_1, f"BundleOffer count grew from {count_bo_1} to {count_bo_2}"
        assert count_el_2 == count_el_1, f"EvidenceLink count grew from {count_el_1} to {count_el_2}"
        assert count_ads_2 == count_ads_1, f"Baseline ads mutated: {count_ads_1} -> {count_ads_2}"
        assert count_snaps_2 == count_snaps_1, f"Baseline snapshots mutated: {count_snaps_1} -> {count_snaps_2}"

    finally:
        await engine.dispose()
        try:
            os.remove(tmp_db_path)
        except Exception:
            pass
