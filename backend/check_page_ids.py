import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.database import async_session_factory
from app.models.models import Advertiser, Advertisement
from sqlalchemy import select

async def main():
    async with async_session_factory() as db:
        res = await db.execute(select(Advertiser))
        advs = res.scalars().all()
        print(f"Total advertisers: {len(advs)}")
        for a in advs:
            print(f"ID: {a.id} | Name: {a.name} | Domain: {a.domain} | PageID: {a.facebook_page_id} | ExtID: {a.external_id}")
            
        ads_res = await db.execute(select(Advertisement).where(Advertisement.is_synthetic == False))
        ads = ads_res.scalars().all()
        print(f"\nAuthentic ads count: {len(ads)}")
        page_ids = set()
        for ad in ads:
            if ad.raw_data and isinstance(ad.raw_data, dict):
                pid = ad.raw_data.get("pageId")
                pname = ad.raw_data.get("pageName")
                page_ids.add((pid, pname))
        print("Page IDs found in authentic ad raw_data:")
        for pid, pname in page_ids:
            print(f"  Page ID: {pid} | Page Name: {pname}")

if __name__ == "__main__":
    asyncio.run(main())

