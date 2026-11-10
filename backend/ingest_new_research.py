"""
US WIN HUNTER — Ingest Newly Discovered Research Candidates
Ingests authentic records from:
- Google Trends (Run XxUAv1fy5qQ1yp3nR, 10 items)
- Amazon US (Run LlPmsdtloU2fWOHj1, 24 items)
Adds canonical products, offers, evidence links, and rescores with BalancedScoringEngine.
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
    DataSourceType,
    ConfidenceLevel,
)
from app.engines.scoring import BalancedScoringEngine

settings = get_settings()

async def ingest_new_research():
    base_dir = Path(__file__).resolve().parent
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    with open(base_dir / "new_research_manifest.json", encoding="utf-8") as f:
        manifest = json.load(f)
    with open(base_dir / "new_research_raw_trends.json", encoding="utf-8") as f:
        trends_raw = json.load(f)
    with open(base_dir / "new_research_raw_amazon.json", encoding="utf-8") as f:
        amazon_raw = json.load(f)

    async with async_session() as session:
        print("Ingesting New Research Runs into DB...")

        # 1. Collection Runs for Provenance
        # Google Trends
        trends_ds_res = await session.execute(select(DataSource).where(DataSource.name == "Google Trends Scraper"))
        trends_ds = trends_ds_res.scalar_one_or_none()
        trends_job_res = await session.execute(select(CollectionJob).where(CollectionJob.name == "trends_pilot_queries"))
        trends_job = trends_job_res.scalar_one_or_none()

        trends_run = CollectionRun(
            id="XxUAv1fy5qQ1yp3nR",
            job_id=trends_job.id if trends_job else "trends_pilot_queries",
            status=CollectionJobStatus.COMPLETED,
            started_at=datetime(2026, 11, 10, 18, 7, 7, tzinfo=timezone.utc),
            completed_at=datetime(2026, 11, 10, 18, 8, 20, tzinfo=timezone.utc),
            records_fetched=len(trends_raw),
            errors={"actual_cost_usd": 0.0541, "cost_status": "VERIFIED_BILLED"},
        )
        session.add(trends_run)

        # Amazon US
        amz_ds_res = await session.execute(select(DataSource).where(DataSource.name == "Amazon US Scraper"))
        amz_ds = amz_ds_res.scalar_one_or_none()
        amz_job_res = await session.execute(select(CollectionJob).where(CollectionJob.name == "amazon_pilot_benchmark"))
        amz_job = amz_job_res.scalar_one_or_none()

        amz_run = CollectionRun(
            id="LlPmsdtloU2fWOHj1",
            job_id=amz_job.id if amz_job else "amazon_pilot_benchmark",
            status=CollectionJobStatus.COMPLETED,
            started_at=datetime(2026, 11, 10, 18, 8, 21, tzinfo=timezone.utc),
            completed_at=datetime(2026, 11, 10, 18, 8, 45, tzinfo=timezone.utc),
            records_fetched=len(amazon_raw),
            errors={"actual_cost_usd": 0.0241, "cost_status": "VERIFIED_BILLED"},
        )
        session.add(amz_run)
        await session.flush()

        # 2. SourceRecords
        for i, item in enumerate(trends_raw):
            q = item.get("searchTerm") or item.get("query")
            session.add(SourceRecord(
                collection_run_id=trends_run.id,
                source_type=DataSourceType.GOOGLE_TRENDS,
                external_id=f"trends_new_{q.replace(' ', '_')}",
                raw_data=item,
                is_processed=True,
                geographic_context="US",
                geo_confidence=ConfidenceLevel.HIGH,
            ))

        for i, item in enumerate(amazon_raw):
            asin = item.get("asin")
            if asin:
                session.add(SourceRecord(
                    collection_run_id=amz_run.id,
                    source_type=DataSourceType.AMAZON,
                    external_id=f"amazon_asin_{asin}",
                    raw_data=item,
                    is_processed=True,
                    geographic_context="US",
                    geo_confidence=ConfidenceLevel.HIGH,
                ))

        # 3. Canonical New Products
        # Candidate 1: Automatic Electric Jar Opener for Seniors & Arthritis
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

        # Jar Opener Offers
        session.add(ProductOffer(
            product_id=jar_opener.id,
            price_usd=24.95,
            quantity=1,
            is_bundle=False,
            evidence_type=EvidenceType.OBSERVED_FACT,
            source_url="https://www.amazon.com/dp/B08779FHLS",
            raw_data={"asin": "B08779FHLS", "model": "Robotwist Automatic Jar Opener"},
        ))
        session.add(ProductOffer(
            product_id=jar_opener.id,
            price_usd=35.99,
            quantity=1,
            is_bundle=False,
            evidence_type=EvidenceType.OBSERVED_FACT,
            source_url="https://www.amazon.com/dp/B0HMWBGDBR",
            raw_data={"asin": "B0HMWBGDBR", "model": "USB-C Rechargeable Higher Torque Model"},
        ))
        session.add(BundleOffer(
            product_id=jar_opener.id,
            quantity=1,
            bundle_price_usd=39.99,
            unit_price_usd=39.99,
            bundle_mechanism=BundleMechanism.FREQUENT_USAGE,
            discount_claim="Complete Senior Kitchen Bundle (Jar Opener + Silicone Anti-Slip Base Mat + Bottle Gripper)",
        ))

        # Jar Opener Evidence Links
        session.add(EvidenceLink(
            entity_type="product",
            entity_id=jar_opener.id,
            evidence_type=EvidenceType.OBSERVED_FACT,
            source_type=DataSourceType.AMAZON,
            source_url="https://www.amazon.com/dp/B0D86Q1PZV",
            description="Amazon US listing benchmark: $31.99, 4.2 stars, active sales depth in kitchen gadgets.",
        ))

        # Candidate 2: Clear Under-Couch & Under-Bed Toy Blocker (Multi-Pack Gap Barrier)
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

        # Couch Blocker Offers
        session.add(ProductOffer(
            product_id=couch_blocker.id,
            price_usd=23.99,
            quantity=8,
            is_bundle=True,
            evidence_type=EvidenceType.OBSERVED_FACT,
            source_url="https://www.amazon.com/dp/B0FDKNNCWH",
            raw_data={"asin": "B0FDKNNCWH", "pack_size": "8-Pack Starter (128 Inches)"},
        ))
        session.add(ProductOffer(
            product_id=couch_blocker.id,
            price_usd=34.98,
            quantity=16,
            is_bundle=True,
            evidence_type=EvidenceType.OBSERVED_FACT,
            source_url="https://www.amazon.com/dp/B0DBQ3LLSF",
            raw_data={"asin": "B0DBQ3LLSF", "pack_size": "16-Pack Whole-Room Perimeter Set (252 Inches)"},
        ))
        session.add(BundleOffer(
            product_id=couch_blocker.id,
            quantity=8,
            bundle_price_usd=23.99,
            unit_price_usd=3.00,
            bundle_mechanism=BundleMechanism.COMPLETE_COVERAGE,
            discount_claim="8-Pack Sectional Front Barrier ($23.99)",
        ))
        session.add(BundleOffer(
            product_id=couch_blocker.id,
            quantity=16,
            bundle_price_usd=34.98,
            unit_price_usd=2.19,
            bundle_mechanism=BundleMechanism.COMPLETE_COVERAGE,
            discount_claim="16-Pack Whole-Home Sofa & Bed Perimeter Bundle ($34.98)",
        ))

        # Couch Blocker Evidence Link
        session.add(EvidenceLink(
            entity_type="product",
            entity_id=couch_blocker.id,
            evidence_type=EvidenceType.OBSERVED_FACT,
            source_type=DataSourceType.AMAZON,
            source_url="https://www.amazon.com/dp/B0DBQ3LLSF",
            description="Amazon US benchmark: 4.1 stars, multi-pack standard of 8 to 16 pieces, price $23.99 - $34.98.",
        ))

        await session.commit()
        print(f"Ingested 2 new canonical products into DB successfully!")

        # 4. Rescore all products
        print("\nRescoring all products with BalancedScoringEngine...")
        scoring_engine = BalancedScoringEngine(session)
        scores = await scoring_engine.score_all_products()
        await session.commit()
        print(f"Scored {len(scores)} total products.")

        # Commercial model breakdown
        from collections import Counter
        models = Counter(s.commercial_model for s in scores)
        statuses = Counter(s.opportunity_status for s in scores)
        print("\nCommercial Model Distribution Post-Research:")
        for m, cnt in models.items():
            print(f"  {m}: {cnt}")
        print("\nOpportunity Status Distribution Post-Research:")
        for st, cnt in statuses.items():
            print(f"  {st}: {cnt}")

        print("\nScores for Newly Discovered Products:")
        for s in scores:
            if s.product_id in (jar_opener.id, couch_blocker.id):
                p = await session.get(Product, s.product_id)
                print(f"  [{s.composite_score:.1f}] [{s.commercial_model}] [{s.opportunity_status}] {p.name[:60]}")
                print(f"      Core Opp: {s.core_opportunity_score} | Bundle Upside: {s.bundle_upside_score} | Conf: {s.evidence_confidence}")
                print(f"      Why High: {s.why_it_ranks_high}")

    await engine.dispose()

if __name__ == "__main__":
    import asyncio
    asyncio.run(ingest_new_research())

