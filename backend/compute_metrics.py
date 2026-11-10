import json
from collections import defaultdict

with open("backend/product_hierarchy.json", encoding="utf-8") as f:
    products = json.load(f)

with open("backend/promising_audit_results.json", encoding="utf-8") as f:
    promising_audit = {x["id"]: x for x in json.load(f)}

# Let's map products to strategies and calculate metrics
# We know:
# Total billed costs:
# Pain-First: $0.0370 (Tasks 1-6)
# Bundle-First: $0.0460 (Tasks 7-12)
# Advertiser-First: $0.0170 (Tasks 13-14)
# Total: $0.1000

# Let's map which product belongs to which strategy based on raw record attribution
# We can read backend/data_inventory.json and source records
import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.database import async_session_factory
from app.models.models import Advertisement, SourceRecord

async def run_metrics():
    async with async_session_factory() as db:
        recs = (await db.execute(select(SourceRecord).where(SourceRecord.is_synthetic == False))).scalars().all()
        ads = (await db.execute(select(Advertisement).where(Advertisement.is_synthetic == False))).scalars().all()
        
        ad_to_prod = {a.external_id: a.product_id for a in ads if a.product_id}
        prod_strats = defaultdict(set)
        for r in recs:
            strat = (r.raw_data or {}).get("_us_win_hunter_attribution", {}).get("discovery_strategy")
            pid = ad_to_prod.get(r.external_id)
            if pid and strat:
                prod_strats[pid].add(strat)

        p_dict = {p["product_id"]: p for p in products}

        strategy_stats = {}
        costs = {
            "PAIN_FIRST": 0.0370,
            "BUNDLE_FIRST": 0.0460,
            "ADVERTISER_FIRST": 0.0170,
        }

        for strat, cost in costs.items():
            strat_pids = [pid for pid, strats in prod_strats.items() if strat in strats]
            strat_prods = [p_dict[pid] for pid in strat_pids if pid in p_dict]
            
            total_prods = len(strat_prods)
            physical_prods = [p for p in strat_prods if p["is_physical"]]
            solutions = set(p["solution"] for p in physical_prods)
            
            # Promising candidates
            verified_promising = [p for p in strat_prods if promising_audit.get(p["product_id"], {}).get("classification") in ("HIGH_CONFIDENCE_PROMISING", "PLAUSIBLE_BUT_UNVERIFIED")]
            false_positives = [p for p in strat_prods if not p["is_physical"] or promising_audit.get(p["product_id"], {}).get("classification") == "FALSE_POSITIVE"]
            
            # Previously known
            prev_known = [p for p in strat_prods if "mop" in p["physical_type"].lower() and "swiftlifty" in p["brand"].lower()]
            
            fp_rate = (len(false_positives) / total_prods * 100) if total_prods else 0.0
            prev_rate = (len(prev_known) / total_prods * 100) if total_prods else 0.0
            
            cost_per_phys = (cost / len(physical_prods)) if physical_prods else 0.0
            cost_per_sol = (cost / len(solutions)) if solutions else 0.0
            cost_per_prom = (cost / len(verified_promising)) if verified_promising else 0.0

            strategy_stats[strat] = {
                "billed_cost": cost,
                "total_products": total_prods,
                "physical_products": len(physical_prods),
                "unique_solutions": len(solutions),
                "verified_promising": len(verified_promising),
                "false_positives": len(false_positives),
                "false_positive_rate": round(fp_rate, 1),
                "previously_known_count": len(prev_known),
                "previously_known_rate": round(prev_rate, 1),
                "cost_per_physical_product": round(cost_per_phys, 4),
                "cost_per_solution": round(cost_per_sol, 4),
                "cost_per_verified_promising": round(cost_per_prom, 4),
            }

        print("=== STRATEGY EFFICIENCY METRICS ===")
        print(json.dumps(strategy_stats, indent=2))

if __name__ == "__main__":
    from sqlalchemy import select
    asyncio.run(run_metrics())

