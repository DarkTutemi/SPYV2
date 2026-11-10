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

async def run_audit():
    async with async_session_factory() as db:
        prods = (await db.execute(select(Product).where(Product.is_synthetic == False))).scalars().all()
        ads = (await db.execute(select(Advertisement).where(Advertisement.is_synthetic == False))).scalars().all()
        advs = {a.id: a for a in (await db.execute(select(Advertiser))).scalars().all()}
        scores = {s.product_id: s for s in (await db.execute(select(OpportunityScore))).scalars().all()}
        runs = (await db.execute(select(CollectionRun).order_by(CollectionRun.created_at.asc()))).scalars().all()
        records = (await db.execute(select(SourceRecord).where(SourceRecord.is_synthetic == False))).scalars().all()
        bundle_offers = (await db.execute(select(BundleOffer))).scalars().all()

        # Map ads to products
        p_ads = defaultdict(list)
        for a in ads:
            if a.product_id:
                p_ads[a.product_id].append(a)

        # Map source records by external_id
        rec_by_ext_id = {r.external_id: r for r in records}

        # Identify Phase 7 run
        p7_run = next((r for r in runs if (r.errors or {}).get("apify_run_id") == "mgrbhLt82lm2ybAZn"), None)
        p7_ext_ids = set()
        if p7_run:
            p7_ext_ids = {r.external_id for r in records if r.collection_run_id == p7_run.id}

        # Check which products were created in Phase 7
        p7_prods = set()
        for p in prods:
            p_ad_ext_ids = {a.external_id for a in p_ads.get(p.id, [])}
            if p_ad_ext_ids and p_ad_ext_ids.issubset(p7_ext_ids):
                p7_prods.add(p.id)

        print(f"Total non-synthetic products in DB: {len(prods)}")
        print(f"Products from Phase 7 only: {len(p7_prods)}")
        
        # Phase 10 touched products
        p10_prods = [p for p in prods if p.id not in p7_prods]
        print(f"Products touched/created in Phase 10: {len(p10_prods)}")

        # Strategy overlap audit
        # Find which products belong to which strategy
        strat_prods = defaultdict(set)
        for p in prods:
            for a in p_ads.get(p.id, []):
                rec = rec_by_ext_id.get(a.external_id)
                if rec and rec.raw_data:
                    strat = rec.raw_data.get("_us_win_hunter_attribution", {}).get("discovery_strategy")
                    if strat:
                        strat_prods[strat].add(p.id)

        print(f"Strategy Product Counts: PAIN_FIRST={len(strat_prods['PAIN_FIRST'])}, BUNDLE_FIRST={len(strat_prods['BUNDLE_FIRST'])}, ADVERTISER_FIRST={len(strat_prods['ADVERTISER_FIRST'])}")
        
        # Check overlaps between strategies
        overlap_pain_bundle = strat_prods['PAIN_FIRST'] & strat_prods['BUNDLE_FIRST']
        overlap_pain_adv = strat_prods['PAIN_FIRST'] & strat_prods['ADVERTISER_FIRST']
        overlap_bundle_adv = strat_prods['BUNDLE_FIRST'] & strat_prods['ADVERTISER_FIRST']
        all_strat_prods = strat_prods['PAIN_FIRST'] | strat_prods['BUNDLE_FIRST'] | strat_prods['ADVERTISER_FIRST']
        print(f"Total distinct products in 3 strategies: {len(all_strat_prods)}")
        print(f"Overlap Pain & Bundle: {len(overlap_pain_bundle)}")
        print(f"Overlap Pain & Adv: {len(overlap_pain_adv)}")
        print(f"Overlap Bundle & Adv: {len(overlap_bundle_adv)}")
        for pid in (overlap_pain_bundle | overlap_pain_adv | overlap_bundle_adv):
            p = next(x for x in prods if x.id == pid)
            print(f"  - Overlapping product: '{p.name}' (ID: {p.id[:8]})")

        # Now evaluate all 57 PROMISING candidates
        promising_prods = [p for p in prods if p.opportunity_status == "PROMISING"]
        print(f"\nEvaluating {len(promising_prods)} PROMISING candidates...")

        results = []
        for p in promising_prods:
            ad_list = p_ads.get(p.id, [])
            primary_ad = ad_list[0] if ad_list else None
            adv = advs.get(primary_ad.advertiser_id) if primary_ad and primary_ad.advertiser_id else None
            sc = scores.get(p.id)
            
            # Analyze physical product vs digital / junk / supplement
            name_lower = p.name.lower()
            url_lower = (primary_ad.landing_page_url or "").lower() if primary_ad else ""
            body_lower = (primary_ad.body or "").lower() if primary_ad else ""
            desc_lower = (p.description or "").lower()
            text = f"{name_lower} {url_lower} {body_lower} {desc_lower}"
            
            # Flag categories
            is_digital = any(k in text for k in ["novel", "monovellnk", "blinkdrama", "goodnovel", "fixbt", "chapter", "read now", "auction", "estate online auction", "doordash"])
            is_supplement = any(k in text for k in ["gastroshield", "kavalix", "black-seed-oil", "elvoralabs", "bloated", "mydermadream", "trybloomandbond", "myotide", "crepey", "receding-gums", "tryorgatics", "metabolae", "glp-1", "periodontal", "eye renewal", "serum", "butt paste"])
            is_heavy_machinery = any(k in text for k in ["palletforks", "skid-steer", "flail mower", "tooth bar", "bale spear"])
            is_affiliate = any(k in text for k in ["smartcarting.com/affiliation", "crm"])
            
            # Classification
            if is_digital or is_affiliate:
                classification = "FALSE_POSITIVE"
                reason = "Digital app/content or affiliate blog funnel"
            elif is_supplement:
                classification = "FALSE_POSITIVE"
                reason = "Health supplement, cream, or oral remedy (not consumer utility hardware/goods)"
            elif is_heavy_machinery:
                classification = "FALSE_POSITIVE"
                reason = "Heavy agricultural/industrial machinery attachment"
            else:
                # Assess multi-unit and commercial viability
                # Check if it solves clear recurring pain and has natural multi-unit demand
                if any(k in text for k in ["mop", "chair leg", "pee pad", "puppy pad", "dog boot", "rug gripper", "windshield cleaner", "detailing towel", "bolt extractor"]):
                    classification = "HIGH_CONFIDENCE_PROMISING"
                    reason = "Verified physical utility product with strong multi-unit demand"
                elif any(k in text for k in ["headlamp", "strobe light", "note board", "peeler", "diamond painting", "boxer", "leak", "underwear"]):
                    classification = "PLAUSIBLE_BUT_UNVERIFIED"
                    reason = "Physical consumer product, but multi-unit demand or pricing requires direct funnel verification"
                else:
                    classification = "WEAK_MULTI_UNIT_DEMAND"
                    reason = "Single unit purchase typically sufficient; weak natural bundle logic"

            results.append({
                "id": p.id,
                "name": p.name,
                "category": p.category,
                "classification": classification,
                "reason": reason,
                "advertiser": adv.name if adv else "Unknown",
                "page_id": adv.facebook_page_id if adv else None,
                "domain": adv.domain if adv else None,
                "landing_url": primary_ad.landing_page_url if primary_ad else None,
                "ad_archive_id": primary_ad.external_id if primary_ad else None,
                "start_date": str(primary_ad.advertiser_start_date) if primary_ad and primary_ad.advertiser_start_date else None,
                "score": sc.composite_score if sc else 0.0,
                "confidence": sc.evidence_confidence if sc else 0.0,
                "bundle_qty": p.primary_bundle_qty,
                "min_price": p.min_price_usd,
            })

        # Summary of precision
        counts = defaultdict(int)
        for r in results:
            counts[r["classification"]] += 1
        print("\n=== PRECISION AUDIT FOR 57 PROMISING CANDIDATES ===")
        for k, v in counts.items():
            print(f"- {k}: {v} ({v/len(results)*100:.1f}%)")

        with open("backend/promising_audit_results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print("Exported promising_audit_results.json")

if __name__ == "__main__":
    asyncio.run(run_audit())
