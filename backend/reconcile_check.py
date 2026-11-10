import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import async_session_factory
from app.models.models import CollectionRun, CollectionJob, Product, Advertisement, Advertiser
from sqlalchemy import select

async def main():
    async with async_session_factory() as db:
        res = await db.execute(select(CollectionRun))
        runs = res.scalars().all()
        print(f"Total collection runs: {len(runs)}")
        for r in runs:
            print(f"Run ID: {r.id} | Provider Run ID: {r.provider_run_id} | Status: {r.status} | Ads: {r.records_collected} | Cost: ${r.actual_cost_usd} | Cap: ${r.budget_cap_usd}")
            if r.provider_run_id == "mgrbhLt82lm2ybAZn":
                print("Run Metadata:", json.dumps(r.run_metadata, indent=2))
        
        # Check advertisers
        adv_res = await db.execute(select(Advertiser))
        advertisers = adv_res.scalars().all()
        print(f"\nTotal advertisers in DB: {len(advertisers)}")
        for a in advertisers:
            print(f"- ID: {a.id[:8]} | Name: {a.name} | Domain: {a.domain} | Page ID: {getattr(a, 'page_id', None)} | Ext ID: {getattr(a, 'external_id', None)}")

        # Check ads
        ads_res = await db.execute(select(Advertisement).where(Advertisement.is_synthetic == False))
        ads = ads_res.scalars().all()
        print(f"\nTotal authentic ads in DB: {len(ads)}")
        for ad in ads:
            print(f"Ad: {ad.external_id} | Adv ID: {ad.advertiser_id[:8]} | Landing: {ad.landing_page_url} | Product ID: {ad.product_id[:8] if ad.product_id else 'None'}")

if __name__ == "__main__":
    asyncio.run(main())

