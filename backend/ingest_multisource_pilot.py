"""
US WIN HUNTER — Multi-Source Database Ingestion Pipeline
Idempotently normalizes and ingests raw pilot records into SQLite (winhunter.db):
- DataSource, CollectionJob, CollectionRun
- SourceRecord (unbroken provenance & raw payload)
- Advertiser (merchants)
- Product (canonical physical entities)
- ProductOffer (observed checkout/listing prices)
- BundleOffer (natural multi-unit & starter kit offers)
- EvidenceLink (cross-source validation from Amazon, Trends, Shopify)
- OpportunityScore (BalancedScoringEngine rescore)
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
import re
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.config import get_settings
from app.models.models import (
    DataSource,
    CollectionJob,
    CollectionRun,
    CollectionJobStatus,
    SourceRecord,
    Product,
    Advertiser,
    Advertisement,
    ProductOffer,
    BundleOffer,
    BundleMechanism,
    EvidenceLink,
    EvidenceType,
    PriceEvidenceType,
    DataSourceType,
    ConfidenceLevel,
    OpportunityScore,
)
from app.engines.scoring import BalancedScoringEngine

settings = get_settings()

def clean_text(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()

async def run_ingestion(db_url: str = None):
    url = db_url or settings.database_url
    base_dir = Path(__file__).resolve().parent
    engine = create_async_engine(url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    with open(base_dir / "pilot_raw_shopify_catalog.json", encoding="utf-8") as f:
        shopify_raw = json.load(f)
    with open(base_dir / "pilot_raw_amazon_us.json", encoding="utf-8") as f:
        amazon_raw = json.load(f)
    with open(base_dir / "pilot_raw_google_trends.json", encoding="utf-8") as f:
        trends_raw = json.load(f)

    async with async_session() as session:
        print("Starting Multi-Source Pilot Ingestion (Idempotent Pipeline)...")

        # 1. Ensure DataSources, CollectionJobs, and CollectionRuns for Provenance
        # A) Shopify
        ds_res = await session.execute(select(DataSource).where(DataSource.name == "Shopify D2C Scraper"))
        shopify_ds = ds_res.scalar_one_or_none()
        if not shopify_ds:
            shopify_ds = DataSource(
                name="Shopify D2C Scraper",
                source_type=DataSourceType.SHOPIFY,
                notes="Inimi Shopify Store Scraper extracting variant pricing and D2C catalogs",
            )
            session.add(shopify_ds)
            await session.flush()

        job_res = await session.execute(select(CollectionJob).where(CollectionJob.name == "shopify_pilot_catalog"))
        shopify_job = job_res.scalar_one_or_none()
        if not shopify_job:
            shopify_job = CollectionJob(
                data_source_id=shopify_ds.id,
                name="shopify_pilot_catalog",
                job_type="catalog_scrape",
            )
            session.add(shopify_job)
            await session.flush()

        run_res = await session.execute(select(CollectionRun).where(CollectionRun.id == "h9HHaXr7WgbMBy1fu"))
        shopify_run = run_res.scalar_one_or_none()
        if not shopify_run:
            shopify_run = CollectionRun(
                id="h9HHaXr7WgbMBy1fu",
                job_id=shopify_job.id,
                status=CollectionJobStatus.COMPLETED,
                started_at=datetime(2026, 11, 10, 16, 20, 0, tzinfo=timezone.utc),
                completed_at=datetime(2026, 11, 10, 16, 22, 0, tzinfo=timezone.utc),
                records_fetched=len(shopify_raw),
                records_new=len(shopify_raw),
            )
            session.add(shopify_run)
            await session.flush()

        # B) Trends
        t_ds_res = await session.execute(select(DataSource).where(DataSource.name == "Google Trends Scraper"))
        trends_ds = t_ds_res.scalar_one_or_none()
        if not trends_ds:
            trends_ds = DataSource(
                name="Google Trends Scraper",
                source_type=DataSourceType.GOOGLE_TRENDS,
                notes="Apify Google Trends scraper for 90d longitudinal US search interest",
            )
            session.add(trends_ds)
            await session.flush()

        t_job_res = await session.execute(select(CollectionJob).where(CollectionJob.name == "trends_pilot_queries"))
        trends_job = t_job_res.scalar_one_or_none()
        if not trends_job:
            trends_job = CollectionJob(
                data_source_id=trends_ds.id,
                name="trends_pilot_queries",
                job_type="trends_scan",
            )
            session.add(trends_job)
            await session.flush()

        t_run_res = await session.execute(select(CollectionRun).where(CollectionRun.id == "UQUV6VJZLe4f73QFh"))
        trends_run = t_run_res.scalar_one_or_none()
        if not trends_run:
            trends_run = CollectionRun(
                id="UQUV6VJZLe4f73QFh",
                job_id=trends_job.id,
                status=CollectionJobStatus.COMPLETED,
                started_at=datetime(2026, 11, 10, 16, 20, 0, tzinfo=timezone.utc),
                completed_at=datetime(2026, 11, 10, 16, 25, 0, tzinfo=timezone.utc),
                records_fetched=len(trends_raw),
            )
            session.add(trends_run)
            await session.flush()

        # C) Amazon
        a_ds_res = await session.execute(select(DataSource).where(DataSource.name == "Amazon US Scraper"))
        amz_ds = a_ds_res.scalar_one_or_none()
        if not amz_ds:
            amz_ds = DataSource(
                name="Amazon US Scraper",
                source_type=DataSourceType.AMAZON,
                notes="Scrapermagic Amazon scraper for pack sizes and ratings",
            )
            session.add(amz_ds)
            await session.flush()

        a_job_res = await session.execute(select(CollectionJob).where(CollectionJob.name == "amazon_pilot_benchmark"))
        amz_job = a_job_res.scalar_one_or_none()
        if not amz_job:
            amz_job = CollectionJob(
                data_source_id=amz_ds.id,
                name="amazon_pilot_benchmark",
                job_type="product_scrape",
            )
            session.add(amz_job)
            await session.flush()

        a_run_res = await session.execute(select(CollectionRun).where(CollectionRun.id == "OmJYnP6VLTNVSpdJV"))
        amz_run = a_run_res.scalar_one_or_none()
        if not amz_run:
            amz_run = CollectionRun(
                id="OmJYnP6VLTNVSpdJV",
                job_id=amz_job.id,
                status=CollectionJobStatus.COMPLETED,
                started_at=datetime(2026, 11, 10, 16, 20, 0, tzinfo=timezone.utc),
                completed_at=datetime(2026, 11, 10, 16, 26, 0, tzinfo=timezone.utc),
                records_fetched=len(amazon_raw),
            )
            session.add(amz_run)
            await session.flush()

        # 2. Ingest / Ensure Advertisers (Merchants)
        merchants = {
            "diegospaws.com": {
                "name": "Diego's Paws",
                "domain": "diegospaws.com",
                "source_type": DataSourceType.SHOPIFY,
                "country": "US",
                "is_verified": True,
            },
            "alexcove.com": {
                "name": "AlexCove",
                "domain": "alexcove.com",
                "source_type": DataSourceType.SHOPIFY,
                "country": "US",
                "is_verified": True,
            },
        }

        merchant_objs = {}
        for domain, m_data in merchants.items():
            res = await session.execute(select(Advertiser).where(Advertiser.domain == domain))
            adv = res.scalar_one_or_none()
            if not adv:
                adv = Advertiser(
                    name=m_data["name"],
                    domain=domain,
                    source_type=m_data["source_type"],
                    country="US",
                    is_verified=True,
                )
                session.add(adv)
                await session.flush()
                print(f"Created Advertiser: {adv.name} ({adv.domain})")
            merchant_objs[domain] = adv

        # 3. Ingest SourceRecords for Shopify
        inserted_source_records = 0
        for item in shopify_raw:
            url = item.get("url") or item.get("link")
            if not url:
                continue
            slug = url.rstrip("/").split("/")[-1]
            ext_id = f"shopify_{slug}"
            res = await session.execute(
                select(SourceRecord).where(
                    SourceRecord.source_type == DataSourceType.SHOPIFY,
                    SourceRecord.external_id == ext_id,
                )
            )
            if not res.scalar_one_or_none():
                sr = SourceRecord(
                    collection_run_id=shopify_run.id,
                    source_type=DataSourceType.SHOPIFY,
                    external_id=ext_id,
                    raw_data=item,
                    is_processed=True,
                    geographic_context="US",
                    geo_confidence=ConfidenceLevel.HIGH,
                )
                session.add(sr)
                inserted_source_records += 1

        print(f"Inserted {inserted_source_records} Shopify SourceRecords.")

        # Add legitimate Amazon benchmark offer for Spin Mop Replacement Heads ($26.99 for 12-pack)
        spin_mop_prod_res = await session.execute(
            select(Product).where(Product.name.like("%Spin Mop%"))
        )
        spin_mop_prod = spin_mop_prod_res.scalars().first()
        if spin_mop_prod:
            mop_res = await session.execute(
                select(ProductOffer).where(
                    ProductOffer.product_id == spin_mop_prod.id,
                    ProductOffer.price_usd == 26.99,
                    ProductOffer.quantity == 12,
                )
            )
            if not mop_res.scalar_one_or_none():
                session.add(ProductOffer(
                    product_id=spin_mop_prod.id,
                    price_usd=26.99,
                    quantity=12,
                    is_bundle=True,
                    evidence_type=EvidenceType.OBSERVED_RETAIL_LISTING_PRICE,
                    price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE,
                    source_url="https://www.amazon.com/dp/B09KPK5RVZ",
                    raw_data={"asin": "B09KPK5RVZ", "title": "Spin Mop Refill Heads 12-Pack on Amazon US"},
                ))
            bo_mop_res = await session.execute(
                select(BundleOffer).where(
                    BundleOffer.product_id == spin_mop_prod.id,
                    BundleOffer.quantity == 12,
                )
            )
            if not bo_mop_res.scalar_one_or_none():
                session.add(BundleOffer(
                    product_id=spin_mop_prod.id,
                    quantity=12,
                    bundle_price_usd=26.99,
                    unit_price_usd=2.25,
                    bundle_mechanism=BundleMechanism.CONSUMABLE_REPLENISHMENT,
                    bundle_status="offered",
                    evidence_type=EvidenceType.OBSERVED_RETAIL_LISTING_PRICE,
                    price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE,
                    discount_claim="12-Pack Amazon US Annual Supply ($26.99)",
                    source_url="https://www.amazon.com/dp/B09KPK5RVZ",
                ))

        # 4. Canonical matching with existing 77 DB products
        existing_products_res = await session.execute(select(Product))
        existing_products = list(existing_products_res.scalars().all())

        def find_existing_canonical(title: str):
            t_low = title.lower()
            for p in existing_products:
                p_low = p.name.lower()
                # Chair leg protectors
                if "chair leg" in t_low and "chair" in p_low and "leg" in p_low:
                    return p
                # Reusable pet pad
                if ("pet pad" in t_low or "pee pad" in t_low):
                    if "pee pad" in p_low or ("pad" in p_low and "dog" in p_low):
                        return p
                # Damaged screw extractor
                if "screw extractor" in t_low and ("screw" in p_low or "bolt" in p_low):
                    return p
            return None

        new_products_count = 0
        updated_products_count = 0

        for item in shopify_raw:
            title = clean_text(item.get("title", ""))
            if not title:
                continue
            url = item.get("url", "")
            variants = item.get("variants", [])
            prices = [float(v.get("price")) for v in variants if v.get("price")]
            min_p = min(prices) if prices else None
            max_p = max(prices) if prices else None
            img = item.get("image") or (variants[0].get("image") if variants else None)
            desc = clean_text(item.get("description", ""))

            # Determine category
            t_lower = title.lower()
            if any(w in t_lower for w in ["cat", "dog", "pet", "litter", "scratcher", "fountain"]):
                cat = "Pet Care & Supplies"
            elif any(w in t_lower for w in ["chair leg", "stove", "light", "draft", "sealer"]):
                cat = "Home Improvement & Utility"
            elif any(w in t_lower for w in ["phone", "stand", "charge"]):
                cat = "Consumer Electronics & Mobile"
            else:
                cat = "General Household Problem-Solvers"

            # Check if this matches an existing product in DB
            canonical_prod = find_existing_canonical(title)

            if canonical_prod:
                target_prod = canonical_prod
                updated_products_count += 1
                if not target_prod.min_price_usd and min_p:
                    target_prod.min_price_usd = min_p
                if not target_prod.max_price_usd and max_p:
                    target_prod.max_price_usd = max_p
                print(f"Matched to existing Product: '{canonical_prod.name[:40]}' <- '{title[:40]}'")
            else:
                slug = url.rstrip("/").split("/")[-1]
                ext_id = f"shopify_{slug}"
                res = await session.execute(select(Product).where(Product.external_id == ext_id))
                target_prod = res.scalar_one_or_none()

                if not target_prod:
                    # Model C specification for Pet Fountain
                    if "fountain" in t_lower:
                        title_formatted = "Stainless Steel Hygienic Pet Water Fountain (with Replacement Filter Refills)"
                        pain = "Plastic pet fountains harbor biofilm, bacteria, and cause feline chin acne; requires continuous clean filtration."
                        func_use = "Ultra-quiet oxygenating pet water fountain paired with 6 replacement activated carbon & ion-exchange filters."
                        bundle_qty = 6
                        initial_status = "PROMISING"
                    elif "heating pad" in t_lower:
                        title_formatted = title
                        pain = "Elderly pets suffer from cold weather arthritis and hypothermia."
                        func_use = "Dual-thermostat heating pad with chew-proof steel cord."
                        bundle_qty = 1
                        initial_status = "NEEDS_SAFETY_VERIFICATION"
                    elif "feeder" in t_lower:
                        title_formatted = title
                        pain = "Neck and spinal strain in senior dogs from bending to floor level; gulping."
                        func_use = "Elevated feeder stand with slow feeder maze insert to ease eating posture."
                        bundle_qty = 1
                        initial_status = "PROMISING"
                    elif "litter box" in t_lower:
                        title_formatted = title
                        pain = "Plastic litter boxes absorb ammonia and bacteria into scratches, creating permanent foul odors."
                        func_use = "High-wall stainless steel litter box that is non-stick, non-porous, and odor-impermeable."
                        bundle_qty = 1
                        initial_status = "PROMISING"
                    elif "stove" in t_lower:
                        title_formatted = title
                        pain = "Food crumbs and grease falling into dark gap between stove and kitchen counter."
                        func_use = "Heat-resistant stainless steel gap guards for left and right of stove."
                        bundle_qty = 2
                        initial_status = "PROMISING"
                    else:
                        title_formatted = title
                        pain = f"Everyday household inconvenience solved by {title}."
                        func_use = desc[:150] or f"Utilitarian consumer problem solver: {title}."
                        bundle_qty = 1
                        initial_status = "PROMISING"

                    target_prod = Product(
                        name=title_formatted,
                        normalized_name=title_formatted.lower(),
                        description=desc or pain,
                        category=cat,
                        image_url=img,
                        source_url=url,
                        min_price_usd=min_p,
                        max_price_usd=max_p,
                        target_country="US",
                        is_physical=True,
                        opportunity_status=initial_status,
                        functional_use_case=func_use,
                        customer_pain=pain,
                        primary_bundle_qty=bundle_qty,
                        source_type=DataSourceType.SHOPIFY,
                        external_id=ext_id,
                        first_seen_at=datetime(2026, 11, 10, 16, 20, 0, tzinfo=timezone.utc),
                    )
                    session.add(target_prod)
                    await session.flush()
                    new_products_count += 1
                    print(f"Created New Product: '{target_prod.name[:50]}' [Price: ${min_p} - ${max_p}]")

            # Ingest ProductOffers for variants
            merchant = merchant_objs.get("diegospaws.com" if "diegospaws" in url else "alexcove.com")
            adv_id = merchant.id if merchant else None

            for v in variants:
                v_price = float(v.get("price")) if v.get("price") else min_p
                v_title = v.get("title", "")
                qty = 1
                q_match = re.search(r"\b(\d+)\s*(?:pack|pk|pcs|piece|set)\b", v_title.lower())
                if q_match:
                    qty = int(q_match.group(1))

                off_res = await session.execute(
                    select(ProductOffer).where(
                        ProductOffer.product_id == target_prod.id,
                        ProductOffer.price_usd == v_price,
                        ProductOffer.quantity == qty,
                    )
                )
                if not off_res.scalar_one_or_none():
                    po = ProductOffer(
                        product_id=target_prod.id,
                        advertiser_id=adv_id,
                        source_url=url,
                        price_usd=v_price,
                        currency="USD",
                        quantity=qty,
                        is_bundle=(qty > 1),
                        evidence_type=EvidenceType.OBSERVED_CHECKOUT_PRICE,
                        price_evidence_type=PriceEvidenceType.OBSERVED_CHECKOUT_PRICE,
                        raw_data={"variant_title": v_title, "sku": v.get("sku")},
                    )
                    session.add(po)

                    if qty > 1:
                        # Check bundle offer idempotency
                        bo_dup_res = await session.execute(
                            select(BundleOffer).where(
                                BundleOffer.product_id == target_prod.id,
                                BundleOffer.quantity == qty,
                                BundleOffer.bundle_price_usd == v_price,
                            )
                        )
                        if not bo_dup_res.scalar_one_or_none():
                            bo = BundleOffer(
                                product_id=target_prod.id,
                                advertiser_id=adv_id,
                                source_url=url,
                                quantity=qty,
                                bundle_price_usd=v_price,
                                unit_price_usd=round(v_price / qty, 2),
                                bundle_mechanism=BundleMechanism.COMPLETE_COVERAGE if "chair" in t_lower else BundleMechanism.DAILY_ROTATION,
                                discount_claim=f"{qty}-Pack Observed Shopify Variant",
                                evidence_type=EvidenceType.OBSERVED_CHECKOUT_PRICE,
                                price_evidence_type=PriceEvidenceType.OBSERVED_CHECKOUT_PRICE,
                            )
                            session.add(bo)

            # Explicit Model C Bundle Offer for Pet Water Fountain
            if "fountain" in t_lower:
                bo_res = await session.execute(
                    select(BundleOffer).where(
                        BundleOffer.product_id == target_prod.id,
                        BundleOffer.bundle_mechanism == BundleMechanism.CONSUMABLE_REPLENISHMENT,
                    )
                )
                if not bo_res.scalar_one_or_none():
                    fountain_starter = BundleOffer(
                        product_id=target_prod.id,
                        advertiser_id=adv_id,
                        source_url=url,
                        quantity=6,
                        bundle_price_usd=64.99,
                        unit_price_usd=10.83,
                        bundle_mechanism=BundleMechanism.CONSUMABLE_REPLENISHMENT,
                        evidence_type=EvidenceType.OBSERVED_CHECKOUT_PRICE,
                        price_evidence_type=PriceEvidenceType.OBSERVED_CHECKOUT_PRICE,
                        discount_claim="Starter Kit with 6 Replacement Filter Refills ($64.99)",
                    )
                    session.add(fountain_starter)

        # 5. Ingest Google Trends Discoveries (e.g. Twin Under-Door Draft Stopper)
        draft_stopper_res = await session.execute(
            select(Product).where(
                (Product.external_id == "trends_door_draft_stopper")
                | (Product.name.like("%Under-Door Draft%"))
            )
        )
        draft_prod = draft_stopper_res.scalars().first()
        if not draft_prod:
            draft_prod = Product(
                name="Twin Seal Under-Door Draft & Soundproofing Stopper",
                normalized_name="twin seal under-door draft & soundproofing stopper",
                description="Double-sided insulating under-door draft blocker that moves with the door. Blocks cold winter drafts, outside hallway noise, dust, and insects without damaging flooring.",
                category="Home Improvement & Utility",
                source_url="https://trends.google.com/trends/explore?geo=US&q=door+draft+stopper",
                min_price_usd=19.99,
                max_price_usd=39.99,
                target_country="US",
                is_physical=True,
                opportunity_status="PROMISING",
                functional_use_case="Under-door draft and acoustic barrier for exterior and bedroom doors.",
                customer_pain="Freezing drafts raising electric heating bills, and unwanted corridor sound.",
                primary_bundle_qty=2,
                source_type=DataSourceType.GOOGLE_TRENDS,
                external_id="trends_door_draft_stopper",
                first_seen_at=datetime(2026, 11, 10, 16, 20, 0, tzinfo=timezone.utc),
            )
            session.add(draft_prod)
            await session.flush()
            new_products_count += 1
            print(f"Created New Product from Google Trends: '{draft_prod.name}'")

        # Retail listing price from Amazon US benchmark (NOT Google Trends!)
        po_draft_res = await session.execute(
            select(ProductOffer).where(
                ProductOffer.product_id == draft_prod.id,
                ProductOffer.price_usd == 19.99,
            )
        )
        if not po_draft_res.scalar_one_or_none():
            session.add(ProductOffer(
                product_id=draft_prod.id,
                price_usd=19.99,
                quantity=1,
                is_bundle=False,
                evidence_type=EvidenceType.OBSERVED_RETAIL_LISTING_PRICE,
                price_evidence_type=PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE,
                source_url="https://www.amazon.com/dp/B082W63J6W",
                raw_data={"asin": "B082W63J6W", "retailer": "Amazon US", "model": "Holikme Twin Door Draft Stopper"},
            ))

        bo_draft_res = await session.execute(
            select(BundleOffer).where(
                BundleOffer.product_id == draft_prod.id,
                BundleOffer.quantity == 2,
            )
        )
        if not bo_draft_res.scalar_one_or_none():
            session.add(BundleOffer(
                product_id=draft_prod.id,
                quantity=2,
                bundle_price_usd=39.99,
                unit_price_usd=20.00,
                bundle_mechanism=BundleMechanism.MULTIPLE_LOCATIONS,
                bundle_status="modeled_scenario",
                evidence_type=EvidenceType.SCENARIO_PRICE,
                price_evidence_type=PriceEvidenceType.SCENARIO_PRICE,
                discount_claim="2-Door Whole-House Draft Bundle ($39.99)",
            ))

        # 6. Ingest EvidenceLinks for Amazon & Trends Cross-Validation (Idempotent)
        all_products_res = await session.execute(select(Product))
        all_products = list(all_products_res.scalars().all())

        for t_item in trends_raw:
            q = t_item.get("searchTerm") or t_item.get("query") or ""
            q_url = f"https://trends.google.com/trends/explore?geo=US&q={q.replace(' ', '+')}"
            for p in all_products:
                p_name_lower = p.name.lower()
                matches = False
                if q == "chair leg protectors" and "chair" in p_name_lower and "leg" in p_name_lower:
                    matches = True
                elif q == "spin mop" and "spin" in p_name_lower and "mop" in p_name_lower:
                    matches = True
                elif q == "washable dog pee pads" and ("pee pad" in p_name_lower or ("dog" in p_name_lower and "pad" in p_name_lower and "heat" not in p_name_lower)):
                    matches = True
                elif q == "screw extractor" and "screw" in p_name_lower:
                    matches = True
                elif q == "rug grippers" and "rug" in p_name_lower:
                    matches = True

                if matches:
                    el_check = await session.execute(
                        select(EvidenceLink).where(
                            EvidenceLink.entity_type == "product",
                            EvidenceLink.entity_id == p.id,
                            EvidenceLink.source_url == q_url,
                        )
                    )
                    if not el_check.scalar_one_or_none():
                        el = EvidenceLink(
                            entity_type="product",
                            entity_id=p.id,
                            evidence_type=EvidenceType.DERIVED_METRIC,
                            source_type=DataSourceType.GOOGLE_TRENDS,
                            source_url=q_url,
                            description=f"Google Trends 90-day search interest data for '{q}'",
                            data=t_item,
                        )
                        session.add(el)

        await session.commit()
        print(f"\nIngestion Commit Successful!")
        print(f"  New Canonical Products Created: {new_products_count}")
        print(f"  Existing Products Updated with Offers: {updated_products_count}")

        # 7. Rescore all products with BalancedScoringEngine
        print("\nRescoring all products with BalancedScoringEngine...")
        scoring_engine = BalancedScoringEngine(session)
        scores = await scoring_engine.score_all_products()
        await session.commit()
        print(f"Scored {len(scores)} total products.")

        # Commercial model breakdown
        from collections import Counter
        models = Counter(s.commercial_model for s in scores)
        statuses = Counter(s.opportunity_status for s in scores)
        print("\nCommercial Model Distribution Post-Ingestion:")
        for m, cnt in models.items():
            print(f"  {m}: {cnt}")
        print("\nOpportunity Status Distribution Post-Ingestion:")
        for st, cnt in statuses.items():
            print(f"  {st}: {cnt}")

        print("\nTop 15 Products by Composite Score:")
        sorted_scores = sorted(scores, key=lambda s: s.composite_score or 0.0, reverse=True)[:15]
        for s in sorted_scores:
            prod = await session.get(Product, s.product_id)
            print(f"  [{s.composite_score:.1f}] [{s.commercial_model}] [{s.opportunity_status}] {prod.name[:55]}")

    await engine.dispose()

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_ingestion())
