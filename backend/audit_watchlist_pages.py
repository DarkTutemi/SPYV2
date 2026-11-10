import sqlite3
from pathlib import Path

db_path = Path(__file__).resolve().parent.parent / "data" / "winhunter.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

watchlist = [
    {"label": "Reusable washable dog pee pads", "target_ad_id": "1654383812796911", "seller": "Diego's Paws"},
    {"label": "Men's leakproof boxers", "target_ad_id": "1135373669505006", "seller": "Prostate Warriors (Menvault)"},
    {"label": "Replacement spin mop heads", "target_ad_id": "1822961982334971", "seller": "Swiftlifty"},
    {"label": "Silicone chair leg protectors", "target_ad_id": "1441655818106115", "seller": "AlexCove"},
    {"label": "Microfiber car detailing towels", "target_ad_id": "1385909230286911", "seller": "Tremendousup (Novtris)"},
    {"label": "Rubber anti-curling rug grippers", "target_ad_id": "1102527249449007", "seller": "Gridsparkl/er"}
]

print("=== WATCHLIST ADVERTISER PAGE AUDIT ===")
for item in watchlist:
    aid = item["target_ad_id"]
    c.execute("SELECT * FROM advertisements WHERE external_id = ?", (aid,))
    ad = c.fetchone()
    if ad:
        adv_id = ad["advertiser_id"]
        c.execute("SELECT * FROM advertisers WHERE id = ?", (adv_id,))
        adv = c.fetchone()
        
        # Also check raw_data of advertisement for pageId and pageName
        import json
        raw = json.loads(ad["raw_data"]) if ad["raw_data"] else {}
        page_id_raw = raw.get("pageId")
        page_name_raw = raw.get("pageName")
        
        print(f"\nProduct: {item['label']}")
        print(f"  Target Ad Archive ID: {aid}")
        print(f"  Advertiser DB Name: {adv['name'] if adv else 'N/A'}")
        print(f"  Facebook Page ID (in advertisers table): {adv['facebook_page_id'] if adv else 'N/A'}")
        print(f"  Facebook Page ID (in ad raw_data): {page_id_raw}")
        print(f"  Page Name (in raw_data): {page_name_raw}")
        print(f"  Advertiser Domain: {adv['domain'] if adv else 'N/A'}")
        
        # Check total ads from this page currently in DB
        c.execute("SELECT count(*) FROM advertisements WHERE advertiser_id = ?", (adv_id,))
        count_in_db = c.fetchone()[0]
        print(f"  Total ads in DB from this advertiser: {count_in_db}")
    else:
        print(f"Ad {aid} not found in DB!")

conn.close()

