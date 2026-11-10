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

async def audit():
    async with async_session_factory() as db:
        # 1. Fetch runs
        runs = (await db.execute(select(CollectionRun).order_by(CollectionRun.created_at.desc()).limit(30))).scalars().all()
        p10_runs = [r for r in runs if r.errors and "apify_run_id" in r.errors]
        print(f"=== PHASE 10 RUNS ({len(p10_runs)}) ===")
        total_p10_cost = 0.0
        for r in reversed(p10_runs):
            err = r.errors or {}
            c = float(err.get("actual_cost_usd", 0.0))
            total_p10_cost += c
            print(f"Task {err.get('task_id')}: {err.get('strategy')} | '{err.get('query')}' | Run: {err.get('apify_run_id')} | Dataset: {err.get('dataset_id')} | Fetched: {r.records_fetched} | Cost: ${c:.4f}")
        print(f"Total P10 Reported Cost: ${total_p10_cost:.4f}")

        # 2. Fetch all non-synthetic products
        prods = (await db.execute(select(Product).where(Product.is_synthetic == False))).scalars().all()
        print(f"\n=== NON-SYNTHETIC PRODUCTS: {len(prods)} ===")

        # 3. Fetch all ads and build product-ad mappings
        ads = (await db.execute(select(Advertisement).where(Advertisement.is_synthetic == False))).scalars().all()
        advs = {a.id: a for a in (await db.execute(select(Advertiser))).scalars().all()}
        scores = {s.product_id: s for s in (await db.execute(select(OpportunityScore))).scalars().all()}
        bundles = defaultdict(list)
        for b in (await db.execute(select(BundleOffer))).scalars().all():
            bundles[b.product_id].append(b)

        p_ads = defaultdict(list)
        for a in ads:
            if a.product_id:
                p_ads[a.product_id].append(a)

        # 4. Check Phase 7 product vs Phase 10 products
        # Phase 7 was washable microfiber mop pads
        # Let's inspect creation timestamps or source records
        print("\n=== PRODUCT DETAILS ===")
        promising_count = 0
        qualified_count = 0
        for p in prods:
            sc = scores.get(p.id)
            status = p.opportunity_status
            if status == "PROMISING":
                promising_count += 1
            elif status == "QUALIFIED_OPPORTUNITY":
                qualified_count += 1
            ad_list = p_ads.get(p.id, [])
            adv_names = [advs[a.advertiser_id].name for a in ad_list if a.advertiser_id in advs]
            landing_urls = [a.landing_page_url for a in ad_list if a.landing_page_url]
            score_val = sc.composite_score if sc else 0.0
            print(f"[{status}] (Score: {score_val:.1f}) ID: {p.id[:8]} | Name: {p.name[:50]} | Cat: {p.category} | Advs: {adv_names[:2]} | Url: {landing_urls[:1]}")

        print(f"\nSummary Status: PROMISING={promising_count}, QUALIFIED={qualified_count}, Total={len(prods)}")

if __name__ == "__main__":
    asyncio.run(audit())

