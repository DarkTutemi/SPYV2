import asyncio
import os
import sys
import json
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.database import async_session_factory
from app.models.models import Advertisement, Advertiser, Product, SourceRecord

async def audit_top20_evidence():
    async with async_session_factory() as db:
        with open("backend/product_hierarchy.json", encoding="utf-8") as f:
            hierarchy = json.load(f)

        # Filter only genuine physical products
        phys_prods = [p for p in hierarchy if p["is_physical"]]
        # Sort by score desc
        phys_prods.sort(key=lambda x: x.get("score") or 0.0, reverse=True)
        top20 = phys_prods[:20]

        evidence_list = []
        for item in top20:
            pid = item["product_id"]
            p = await db.get(Product, pid)
            ads_stmt = select(Advertisement).where(Advertisement.product_id == pid)
            p_ads = list((await db.execute(ads_stmt)).scalars().all())
            ad = p_ads[0] if p_ads else None
            
            adv = await db.get(Advertiser, ad.advertiser_id) if ad and ad.advertiser_id else None
            
            # Fetch SourceRecord
            srec = None
            if ad:
                srec_stmt = select(SourceRecord).where(SourceRecord.external_id == ad.external_id)
                srec = (await db.execute(srec_stmt)).scalars().first()

            raw = srec.raw_data if srec else {}
            
            evidence_list.append({
                "product_id": pid,
                "product_name": p.name if p else item["name"],
                "solution": item["solution"],
                "physical_type": item["physical_type"],
                "score": item["score"],
                "ad_archive_id": ad.external_id if ad else None,
                "page_id": adv.facebook_page_id if adv else None,
                "advertiser_name": adv.name if adv else "Unknown",
                "landing_url": ad.landing_page_url if ad else None,
                "ad_url": ad.ad_url if ad else None,
                "ad_title": ad.title if ad else None,
                "ad_body": ad.body[:250] if ad and ad.body else None,
                "creative_url": ad.creative_url if ad else None,
                "creative_type": ad.creative_type if ad else None,
                "start_date": str(ad.advertiser_start_date) if ad and ad.advertiser_start_date else None,
                "first_seen": str(ad.first_seen_at) if ad and ad.first_seen_at else None,
                "country_evidence_tier": raw.get("_us_win_hunter_attribution", {}).get("country_evidence_tier", "SEARCH_FILTER_US"),
                "suspicious_flags": [],
            })

        # Check for suspicious networks / clone funnels
        domain_counts = {}
        page_counts = {}
        for ev in evidence_list:
            domain = ev["landing_url"].split("/")[2] if ev["landing_url"] and "//" in ev["landing_url"] else ""
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
            pid = ev["page_id"]
            if pid:
                page_counts[pid] = page_counts.get(pid, 0) + 1

        for ev in evidence_list:
            domain = ev["landing_url"].split("/")[2] if ev["landing_url"] and "//" in ev["landing_url"] else ""
            if domain_counts.get(domain, 0) > 2:
                ev["suspicious_flags"].append(f"Domain '{domain}' operates multiple products ({domain_counts[domain]})")
            if "smartcarting" in domain:
                ev["suspicious_flags"].append("Affiliate redirect / cloaking domain")
            if "pawndify" in domain or "novthra" in domain:
                ev["suspicious_flags"].append("Shopify / Shoplaza dropshipping multi-product store")

        with open("backend/top20_advertiser_evidence.json", "w", encoding="utf-8") as f:
            json.dump(evidence_list, f, indent=2, ensure_ascii=False)
        print("Exported top20_advertiser_evidence.json with 20 items.")

if __name__ == "__main__":
    asyncio.run(audit_top20_evidence())

