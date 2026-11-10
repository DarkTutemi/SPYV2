import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.database import async_session_factory
from sqlalchemy import select
from app.models.models import Product, OpportunityScore, Advertisement, SourceRecord

async def main():
    async with async_session_factory() as db:
        prods = (await db.execute(select(Product).where(Product.is_synthetic == False))).scalars().all()
        print(f"Total non-synthetic products: {len(prods)}")
        
        # Check products with ads having Phase 10 attribution
        exp_prods = []
        for p in prods:
            ads = (await db.execute(select(Advertisement).where(Advertisement.product_id == p.id))).scalars().all()
            for a in ads:
                if isinstance(a.raw_data, dict) and "_us_win_hunter_attribution" in a.raw_data:
                    attr = a.raw_data["_us_win_hunter_attribution"]
                    exp_prods.append((p, attr, a))
                    break
                    
        print(f"Products with Phase 10 attribution: {len(exp_prods)}")
        print("\nListing all discovered products:")
        for idx, (p, attr, a) in enumerate(exp_prods, 1):
            name = p.name[:60]
            cat = p.category
            strat = attr.get("discovery_strategy")
            query = attr.get("source_query")
            print(f"[{idx:2d}] [{strat[:4]}] [{query[:15]}] {name} (URL: {a.landing_page_url[:40] if a.landing_page_url else 'None'})")

if __name__ == "__main__":
    asyncio.run(main())

