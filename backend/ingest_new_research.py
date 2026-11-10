"""
US WIN HUNTER — Ingest Newly Discovered Research Candidates (Idempotent)
Ingests authentic records from:
- Google Trends (Run XxUAv1fy5qQ1yp3nR, 10 items)
- Amazon US (Run LlPmsdtloU2fWOHj1, 24 items)
Adds canonical products, offers, evidence links, and rescores with BalancedScoringEngine.
Guaranteed 100% idempotent: running multiple times never creates duplicate runs,
products, offers, source records, or evidence links.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.config import get_settings
from app.models.models import (
    DataSource,
    CollectionJob,
    CollectionRun,
    CollectionJobStatus,
    SourceRecord,
    Product,
    ProductOffer,
    BundleOffer,
    BundleMechanism,
    EvidenceLink,
    EvidenceType,
    PriceEvidenceType,
    DataSourceType,
    ConfidenceLevel,
)
from app.engines.scoring import BalancedScoringEngine

settings = get_settings()

async def ingest_new_research(db_url: str = None):
    url = db_url or settings.database_url
    base_dir = Path(__file__).resolve().parent
    engine = create_async_engine(url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    with open(base_dir / "new_research_manifest.json", encoding="utf-8") as f:
        manifest = json.load(f)
    with open(base_dir / "new_research_raw_trends.json", encoding="utf-8") as f:
        trends_raw = json.load(f)
    with open(base_dir / "new_research_raw_amazon.json", encoding="utf-8") as f:
        amazon_raw = json.load(f)

    async with async_session() as session:
        print("Ingesting New Research Runs into DB (Idempotent Pipeline)...")
        try:
            # 1. Collection Runs for Provenance
            # Google Trends
            trends_ds_res = await session.execute(select(DataSource).where(DataSource.name == "Google Trends Scraper"))
            trends_ds = trends_ds_res.scalar_one_or_none()
            if not trends_ds:
                trends_ds = DataSource(name="Google Trends Scraper", source_type=DataSourceType.GOOGLE_TRENDS)
                session.add(trends_ds)
                await session.flush()

            trends_job_res = await session.execute(select(CollectionJob).where(CollectionJob.name == "trends_pilot_queries"))
            trends_job = trends_job_res.scalar_one_or_none()
            if not trends_job:
                trends_job = CollectionJob(data_source_id=trends_ds.id, name="trends_pilot_queries", job_type="trends_scan")
                session.add(trends_job)
                await session.flush()

            trends_run_res = await session.execute(select(CollectionRun).where(CollectionRun.id == "XxUAv1fy5qQ1yp3nR"))
            trends_run = trends_run_res.scalar_one_or_none()
            if not trends_run:
                trends_run = CollectionRun(
                    id="XxUAv1fy5qQ1yp3nR",
                    job_id=trends_job.id,
                    status=CollectionJobStatus.COMPLETED,
                    started_at=datetime(2026, 11, 10, 18, 7, 7, tzinfo=timezone.utc),
                    completed_at=datetime(2026, 11, 10, 18, 8, 20, tzinfo=timezone.utc),
                    records_fetched=len(trends_raw),
                    errors={"actual_cost_usd": 0.0541, "cost_status": "VERIFIED_BILLED"},
                )
                session.add(trends_run)
                await session.flush()

            # Amazon US
            amz_ds_res = await session.execute(select(DataSource).where(DataSource.name == "Amazon US Scraper"))
            amz_ds = amz_ds_res.scalar_one_or_none()
            if not amz_ds:
                amz_ds = DataSource(name="Amazon US Scraper", source_type=DataSourceType.AMAZON)
                session.add(amz_ds)
                await session.flush()

            amz_job_res = await session.execute(select(CollectionJob).where(CollectionJob.name == "amazon_pilot_benchmark"))
            amz_job = amz_job_res.scalar_one_or_none()
            if not amz_job:
                amz_job = CollectionJob(data_source_id=amz_ds.id, name="amazon_pilot_benchmark", job_type="product_scrape")
                session.add(amz_job)
                await session.flush()

            amz_run_res = await session.execute(select(CollectionRun).where(CollectionRun.id == "LlPmsdtloU2fWOHj1"))
            amz_run = amz_run_res.scalar_one_or_none()
            if not amz_run:
                amz_run = CollectionRun(
                    id="LlPmsdtloU2fWOHj1",
                    job_id=amz_job.id,
                    status=CollectionJobStatus.COMPLETED,
                    started_at=datetime(2026, 11, 10, 18, 8, 21, tzinfo=timezone.utc),
                    completed_at=datetime(2026, 11, 10, 18, 8, 45, tzinfo=timezone.utc),
                    records_fetched=len(amazon_raw),
                    errors={"actual_cost_usd": 0.0241, "cost_status": "VERIFIED_BILLED"},
                )
                session.add(amz_run)
                await session.flush()

            # 2. SourceRecords (Idempotent by run_id + external_id)
            for item in trends_raw:
                q = item.get("searchTerm") or item.get("query")
                ext_id = f"trends_new_{q.replace(' ', '_')}"
                sr_check = await session.execute(
                    select(SourceRecord).where(
                        SourceRecord.collection_run_id == trends_run.id,
                        SourceRecord.external_id == ext_id,
                    )
                )
                if not sr_check.scalar_one_or_none():
                    session.add(SourceRecord(
                        collection_run_id=trends_run.id,
                        source_type=DataSourceType.GOOGLE_TRENDS,
                        external_id=ext_id,
                        raw_data=item,
                        is_processed=True,
                        geographic_context="US",
                        geo_confidence=ConfidenceLevel.HIGH,
                    ))

            for item in amazon_raw:
                asin = item.get("asin")
                if asin:
                    ext_id = f"amazon_asin_{asin}"
                    sr_check = await session.execute(
                        select(SourceRecord).where(
                            SourceRecord.collection_run_id == amz_run.id,
                            SourceRecord.external_id == ext_id,
                        )
                    )
                    if not sr_check.scalar_one_or_none():
                        session.add(SourceRecord(
                            collection_run_id=amz_run.id,
                            source_type=DataSourceType.AMAZON,
                            external_id=ext_id,
                            raw_data=item,
                            is_processed=True,
                            geographic_context="US",
                            geo_confidence=ConfidenceLevel.HIGH,
                        ))

            # 3. Canonical New Products (Idempotent by external_id)
            # Candidate 1: Automatic Electric Jar Opener for Seniors & Arthritis
            jar_check = await session.execute(
                select(Product).where(Product.external_id == "amazon_product_electric_jar_opener")
            )
            jar_opener = jar_check.scalar_one_or_none()
            if not jar_opener:
                jar_opener = Product(
                    name="Automatic Hands-Free Electric Jar Opener for Seniors & Weak Hands",
                    normalized_name="automatic hands-free electric jar opener for seniors & weak hands",
                    description="One-touch motorized automatic jar opener that grips jar body and twists stubborn vacuum-sealed lids off hands-free. Specifically engineered for seniors, arthritis patients, and individuals with carpal tunnel or weak grip strength.",
                    category="Kitchen & Ergonomic Utility",
                    source_url="https://www.amazon.com/dp/B0D86Q1PZV",
                    min_price_usd=24.95,
                    max_price_usd=35.99,
                    target_country="US",
                    is_physical=True,
                    opportunity_status="PROMISING",
                    functional_use_case="Motorized hands-free jar lid release eliminating manual wrist twisting torque.",
                    customer_pain="Severe joint pain or inability to open tight, vacuum-sealed food jars without assistance.",
                    primary_bundle_qty=1,
                    source_type=DataSourceType.AMAZON,
                    external_id="amazon_product_electric_jar_opener",
                    first_seen_at=datetime(2026, 11, 10, 18, 8, 45, tzinfo=timezone.utc),
                )
                session.add(jar_opener)
                await session.flush()
                print("Created Canonical Product: Electric Jar Opener")

            # Jar Opener Offers (Idempotent & Accurately Typed)
            jar_offers_data = [
                (24.95, 1, False, "https://www.amazon.com/dp/B08779FHLS", {"asin": "B08779FHLS", "model": "Robotwist Automatic Jar Opener"}),
                (35.99, 1, False, "https://www.amazon.com/dp/B0HMWBGDBR", {"asin": "B0HMWBGDBR", "model": "USB-C Rechargeable Higher Torque Model"}),
            ]
            for price, qty, is_b, url, raw_d in jar_offers_data:
                po_check = await session.execute(
                    select(ProductOffer).where(
                        ProductOffer.product_id == jar_opener.id,
                        ProductOffer.price_usd == price,
                        ProductOffer.quantity == qty,
                    )
                )
                if not po_check.scalar_one_or_none():
                    session.add(ProductOffer(
                        product_id=jar_opener.id,
                        price_usd=price,
                        quantity=qty,
                        is_bundle=is_b,
                        evidence_type=EvidenceType.OBSERVED_RETAIL_LISTING_PRICE,
                        price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE,
                        source_url=url,
                        raw_data=raw_d,
                    ))

            # Jar Opener Modeled Bundle Offer
            bo_jar_check = await session.execute(
                select(BundleOffer).where(
                    BundleOffer.product_id == jar_opener.id,
                    BundleOffer.bundle_price_usd == 39.99,
                )
            )
            if not bo_jar_check.scalar_one_or_none():
                session.add(BundleOffer(
                    product_id=jar_opener.id,
                    quantity=1,
                    bundle_price_usd=39.99,
                    unit_price_usd=39.99,
                    bundle_mechanism=BundleMechanism.FREQUENT_USAGE,
                    bundle_status="modeled_scenario",
                    evidence_type=EvidenceType.SCENARIO_PRICE,
                    price_evidence_type=PriceEvidenceType.SCENARIO_PRICE,
                    discount_claim="Complete Senior Kitchen Bundle (Jar Opener + Silicone Anti-Slip Base Mat + Bottle Gripper)",
                ))

            # Jar Opener Evidence Links
            el_jar_check = await session.execute(
                select(EvidenceLink).where(
                    EvidenceLink.entity_type == "product",
                    EvidenceLink.entity_id == jar_opener.id,
                    EvidenceLink.source_url == "https://www.amazon.com/dp/B0D86Q1PZV",
                )
            )
            if not el_jar_check.scalar_one_or_none():
                session.add(EvidenceLink(
                    entity_type="product",
                    entity_id=jar_opener.id,
                    evidence_type=EvidenceType.OBSERVED_FACT,
                    source_type=DataSourceType.AMAZON,
                    source_url="https://www.amazon.com/dp/B0D86Q1PZV",
                    description="Amazon US listing benchmark: $31.99, 4.2 stars, active sales depth in kitchen gadgets.",
                ))

            # Candidate 2: Clear Under-Couch & Under-Bed Toy Blocker (Multi-Pack Gap Barrier)
            couch_check = await session.execute(
                select(Product).where(Product.external_id == "amazon_product_under_couch_blocker")
            )
            couch_blocker = couch_check.scalar_one_or_none()
            if not couch_blocker:
                couch_blocker = Product(
                    name="Clear Under-Couch & Under-Bed Toy Blocker (Multi-Piece Gap Barrier)",
                    normalized_name="clear under-couch & under-bed toy blocker (multi-piece gap barrier)",
                    description="Clear rigid PVC / acrylic under-furniture barrier panels with traceless adhesive anchoring. Blocks pet toys, toddler balls, and dust bunnies from rolling under low sofas, couches, and beds without ruining room aesthetics.",
                    category="Home Organization & Household Utility",
                    source_url="https://www.amazon.com/dp/B0DBQ3LLSF",
                    min_price_usd=23.99,
                    max_price_usd=34.98,
                    target_country="US",
                    is_physical=True,
                    opportunity_status="PROMISING",
                    functional_use_case="Prevents pet toys and balls rolling into dark, inaccessible under-furniture gaps.",
                    customer_pain="Constantly having to crawl on floor with brooms to retrieve lost pet toys from under heavy sofas.",
                    primary_bundle_qty=8,
                    source_type=DataSourceType.AMAZON,
                    external_id="amazon_product_under_couch_blocker",
                    first_seen_at=datetime(2026, 11, 10, 18, 8, 45, tzinfo=timezone.utc),
                )
                session.add(couch_blocker)
                await session.flush()
                print("Created Canonical Product: Under-Couch Toy Blocker")

            # Couch Blocker Offers (Idempotent & Accurately Typed)
            couch_offers_data = [
                (23.99, 8, True, "https://www.amazon.com/dp/B0FDKNNCWH", {"asin": "B0FDKNNCWH", "pack_size": "8-Pack Starter (128 Inches)"}),
                (34.98, 16, True, "https://www.amazon.com/dp/B0DBQ3LLSF", {"asin": "B0DBQ3LLSF", "pack_size": "16-Pack Whole-Room Perimeter Set (252 Inches)"}),
            ]
            for price, qty, is_b, url, raw_d in couch_offers_data:
                po_check = await session.execute(
                    select(ProductOffer).where(
                        ProductOffer.product_id == couch_blocker.id,
                        ProductOffer.price_usd == price,
                        ProductOffer.quantity == qty,
                    )
                )
                if not po_check.scalar_one_or_none():
                    session.add(ProductOffer(
                        product_id=couch_blocker.id,
                        price_usd=price,
                        quantity=qty,
                        is_bundle=is_b,
                        evidence_type=EvidenceType.OBSERVED_RETAIL_LISTING_PRICE,
                        price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE,
                        source_url=url,
                        raw_data=raw_d,
                    ))

            # Couch Blocker Observed Multi-Pack Bundles
            couch_bundles_data = [
                (8, 23.99, 3.00, "8-Pack Sectional Front Barrier ($23.99)", "https://www.amazon.com/dp/B0FDKNNCWH"),
                (16, 34.98, 2.19, "16-Pack Whole-Home Sofa & Bed Perimeter Bundle ($34.98)", "https://www.amazon.com/dp/B0DBQ3LLSF"),
            ]
            for qty, b_price, u_price, claim, b_url in couch_bundles_data:
                bo_check = await session.execute(
                    select(BundleOffer).where(
                        BundleOffer.product_id == couch_blocker.id,
                        BundleOffer.quantity == qty,
                        BundleOffer.bundle_price_usd == b_price,
                    )
                )
                if not bo_check.scalar_one_or_none():
                    session.add(BundleOffer(
                        product_id=couch_blocker.id,
                        quantity=qty,
                        bundle_price_usd=b_price,
                        unit_price_usd=u_price,
                        bundle_mechanism=BundleMechanism.COMPLETE_COVERAGE,
                        bundle_status="offered",
                        discount_claim=claim,
                        source_url=b_url,
                        evidence_type=EvidenceType.OBSERVED_RETAIL_LISTING_PRICE,
                        price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE,
                    ))

            # Couch Blocker Evidence Link
            el_couch_check = await session.execute(
                select(EvidenceLink).where(
                    EvidenceLink.entity_type == "product",
                    EvidenceLink.entity_id == couch_blocker.id,
                    EvidenceLink.source_url == "https://www.amazon.com/dp/B0DBQ3LLSF",
                )
            )
            if not el_couch_check.scalar_one_or_none():
                session.add(EvidenceLink(
                    entity_type="product",
                    entity_id=couch_blocker.id,
                    evidence_type=EvidenceType.OBSERVED_FACT,
                    source_type=DataSourceType.AMAZON,
                    source_url="https://www.amazon.com/dp/B0DBQ3LLSF",
                    description="Amazon US listing benchmark: $34.98 for 16-pack clear acrylic blocker with traceless tape.",
                ))

            await session.commit()
            print("Idempotent Ingestion of New Research Runs completed successfully.")

        except Exception as e:
            await session.rollback()
            print(f"ERROR during new research ingestion, rolled back: {e}")
            raise

        # 4. Rescore all products with BalancedScoringEngine
        print("\nRescoring all products with BalancedScoringEngine...")
        scoring_engine = BalancedScoringEngine(session)
        scores = await scoring_engine.score_all_products()
        await session.commit()
        print(f"Rescored {len(scores)} products with BalancedScoringEngine.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(ingest_new_research())
