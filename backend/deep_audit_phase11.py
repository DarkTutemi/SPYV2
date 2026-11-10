import asyncio
import os
import sys
import json
from collections import defaultdict
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.database import async_session_factory
from app.models.models import (
    Advertisement,
    Advertiser,
    BundleOffer,
    CollectionJob,
    CollectionRun,
    OpportunityScore,
    Product,
    SourceRecord,
)

async def deep_audit():
    async with async_session_factory() as db:
        # Load all objects
        prods = (await db.execute(select(Product).where(Product.is_synthetic == False))).scalars().all()
        ads = (await db.execute(select(Advertisement).where(Advertisement.is_synthetic == False))).scalars().all()
        advs = {a.id: a for a in (await db.execute(select(Advertiser))).scalars().all()}
        scores = {s.product_id: s for s in (await db.execute(select(OpportunityScore))).scalars().all()}
        runs = (await db.execute(select(CollectionRun).order_by(CollectionRun.created_at.desc()))).scalars().all()
        records = (await db.execute(select(SourceRecord).where(SourceRecord.is_synthetic == False))).scalars().all()
        bundle_offers = (await db.execute(select(BundleOffer))).scalars().all()

        print(f"Loaded: {len(prods)} products, {len(ads)} ads, {len(advs)} advertisers, {len(runs)} runs, {len(records)} source records.")

        # Map ads to products
        prod_ads = defaultdict(list)
        for a in ads:
            if a.product_id:
                prod_ads[a.product_id].append(a)

        # Inspect run IDs and which products they created/touched
        # Phase 7 run: mgrbhLt82lm2ybAZn
        p7_ext_ids = set()
        p10_ext_ids = set()
        task_runs = []
        for r in runs:
            err = r.errors or {}
            run_id = err.get("apify_run_id")
            if not run_id:
                continue
            if run_id == "mgrbhLt82lm2ybAZn":
                # Phase 7
                continue
            task_runs.append((err.get("task_id"), err.get("strategy"), err.get("query"), run_id, err.get("actual_cost_usd"), r.records_fetched))

        # Check source records attribution
        rec_by_run = defaultdict(list)
        for rec in records:
            ext_id = rec.external_id
            c_run_id = rec.collection_run_id
            rec_by_run[c_run_id].append(rec)

        # Output detailed inventory
        data_inventory = []
        for p in prods:
            p_ad_list = prod_ads.get(p.id, [])
            sc = scores.get(p.id)
            
            # Check which runs these ads came from
            ad_runs = []
            for a in p_ad_list:
                for r in runs:
                    # check if ad matches run records
                    pass
            
            primary_ad = p_ad_list[0] if p_ad_list else None
            adv = advs.get(primary_ad.advertiser_id) if primary_ad and primary_ad.advertiser_id else None
            
            data_inventory.append({
                "id": p.id,
                "name": p.name,
                "category": p.category,
                "opportunity_status": p.opportunity_status,
                "composite_score": sc.composite_score if sc else None,
                "evidence_confidence": sc.evidence_confidence if sc else None,
                "min_price_usd": p.min_price_usd,
                "max_price_usd": p.max_price_usd,
                "functional_use_case": p.functional_use_case,
                "customer_pain": p.customer_pain,
                "primary_bundle_qty": p.primary_bundle_qty,
                "ad_count": len(p_ad_list),
                "advertiser_name": adv.name if adv else "Unknown",
                "advertiser_domain": adv.domain if adv else None,
                "advertiser_page_id": adv.facebook_page_id if adv else None,
                "landing_page_url": primary_ad.landing_page_url if primary_ad else None,
                "ad_title": primary_ad.title if primary_ad else None,
                "ad_body": primary_ad.body if primary_ad else None,
                "ad_archive_id": primary_ad.external_id if primary_ad else None,
                "ad_url": primary_ad.ad_url if primary_ad else None,
                "created_at": str(p.created_at),
            })

        with open("backend/data_inventory.json", "w", encoding="utf-8") as f:
            json.dump(data_inventory, f, indent=2, ensure_ascii=False)
        print("Exported data_inventory.json with", len(data_inventory), "products.")

if __name__ == "__main__":
    asyncio.run(deep_audit())

