import asyncio
import sqlite3
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.models.models import Product, OpportunityScore
from app.engines.scoring import BalancedScoringEngine
from app.core.config import get_settings

settings = get_settings()

async def main():
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with async_session() as session:
        scoring_engine = BalancedScoringEngine(session)
        scores = await scoring_engine.score_all_products()
        await session.commit()
        print(f"Scored {len(scores)} products with BalancedScoringEngine.")

        # Check distribution of commercial models
        from collections import Counter
        models = Counter(s.commercial_model for s in scores)
        statuses = Counter(s.opportunity_status for s in scores)
        print("\nCommercial Model Distribution:")
        for m, count in models.items():
            print(f"  {m}: {count}")

        print("\nOpportunity Status Distribution:")
        for st, count in statuses.items():
            print(f"  {st}: {count}")

        print("\nTop 10 Products by Composite Score:")
        sorted_scores = sorted(scores, key=lambda s: s.composite_score or 0.0, reverse=True)[:10]
        for s in sorted_scores:
            prod = await session.get(Product, s.product_id)
            print(f"  [{s.composite_score:.1f}] [{s.commercial_model}] [{s.opportunity_status}] {prod.name[:50]}")
            print(f"      Why High: {s.why_it_ranks_high}")
            print(f"      Why Fail: {s.why_it_might_fail}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())

