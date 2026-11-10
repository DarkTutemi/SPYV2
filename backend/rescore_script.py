import asyncio
from app.core.database import async_session_factory
from app.models.models import Product, OpportunityScore, BundleOffer
from app.engines.bundle_engine import BundleIntelligenceEngine
from app.engines.scoring import ScoringEngine
from sqlalchemy import select, delete

async def main():
    async with async_session_factory() as db:
        # Clear previous modeled scenarios so they re-evaluate with updated tool detection
        await db.execute(delete(BundleOffer).where(BundleOffer.bundle_status == "modeled_scenario"))
        await db.commit()

        res = await db.execute(select(Product))
        products = res.scalars().all()
        print(f"Total products in DB: {len(products)}")
        
        bundle_engine = BundleIntelligenceEngine(db)
        scoring_engine = ScoringEngine(db)
        
        results = []
        for p in products:
            try:
                # Remove existing bundles for this product to allow clean re-analysis
                await db.execute(delete(BundleOffer).where(BundleOffer.product_id == p.id))
                await db.commit()
                await bundle_engine.analyze_product_bundles(p.id)
                score = await scoring_engine.score_product(p.id)
                results.append((p, score))
            except Exception as e:
                print(f"Error scoring product {p.id}: {e}")
        
        await db.commit()
        print("\n=== BATCH RESCORE COMMITTED TO DATABASE ===\n")
        print(f"{'Product ID':<8} | {'Product Name':<40} | {'Status':<22} | {'Composite':<9} | {'Bundle':<7} | {'Func':<6} | {'Disc':<6} | {'Conf':<6} | {'Momentum'}")
        print("-" * 125)
        for p, score in results:
            short_id = p.id[:8]
            name = (p.name[:38] + "..") if len(p.name) > 38 else p.name
            momentum_str = "Unobserved" if score.observed_momentum is None else f"{score.observed_momentum:.1f}"
            print(f"{short_id:<8} | {name:<40} | {score.opportunity_status:<22} | {score.composite_score:9.1f} | {score.bundle_potential:7.1f} | {score.functional_benefit_score:6.1f} | {score.discovery_signal_score:6.1f} | {score.evidence_confidence:6.1f} | {momentum_str}")

if __name__ == "__main__":
    asyncio.run(main())
