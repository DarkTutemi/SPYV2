import sqlite3
import json
from pathlib import Path

db_path = Path(__file__).resolve().parent.parent / "data" / "winhunter.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

print("================ SWIFTLIFTY AUDIT ================")
c.execute("""
    SELECT a.id, a.external_id, a.title, a.body, a.landing_page_url, adv.name, adv.facebook_page_id, adv.domain
    FROM advertisements a
    JOIN advertisers adv ON a.advertiser_id = adv.id
    WHERE adv.domain LIKE '%swiftlifty%' OR adv.name LIKE '%Swiftlifty%'
""")
swift_ads = [dict(r) for r in c.fetchall()]
print(f"Swiftlifty ads count: {len(swift_ads)}")
for a in swift_ads:
    print(f"  Ad ID: {a['external_id']} | Page ID: {a['facebook_page_id']} | Title: {a['title']}")
    print(f"  Landing: {a['landing_page_url']}")
    print(f"  Body (100): {a['body'][:100] if a['body'] else 'None'}\n")

print("================ GRIDSPARKL AUDIT (Spin Mop vs Rug Gripper) ================")
c.execute("""
    SELECT a.id, a.external_id, a.title, a.body, a.landing_page_url, adv.name, adv.facebook_page_id, adv.domain
    FROM advertisements a
    JOIN advertisers adv ON a.advertiser_id = adv.id
    WHERE adv.domain LIKE '%gridsparkl%' OR adv.name LIKE '%Gridsparkl%'
""")
grid_ads = [dict(r) for r in c.fetchall()]
print(f"Gridsparkl ads count: {len(grid_ads)}")
for a in grid_ads:
    if 'mop' in (a['title'] or '').lower() or 'mop' in (a['landing_page_url'] or '').lower() or 'rug' in (a['title'] or '').lower() or 'rug' in (a['landing_page_url'] or '').lower():
        print(f"  Ad ID: {a['external_id']} | Page ID: {a['facebook_page_id']} | Title: {a['title']}")
        print(f"  Landing: {a['landing_page_url']}")
        print(f"  Body (100): {a['body'][:100] if a['body'] else 'None'}\n")

print("================ PAWNDIFY AUDIT ================")
c.execute("""
    SELECT a.id, a.external_id, a.title, a.body, a.landing_page_url, adv.name, adv.facebook_page_id, adv.domain
    FROM advertisements a
    JOIN advertisers adv ON a.advertiser_id = adv.id
    WHERE adv.domain LIKE '%pawndify%' OR adv.name LIKE '%Pawndify%' OR a.landing_page_url LIKE '%pawndify%'
""")
pawn_ads = [dict(r) for r in c.fetchall()]
print(f"Pawndify ads count: {len(pawn_ads)}")
for a in pawn_ads:
    print(f"  Ad ID: {a['external_id']} | Page ID: {a['facebook_page_id']} | Title: {a['title']}")
    print(f"  Landing: {a['landing_page_url']}")
    print(f"  Body (100): {a['body'][:100] if a['body'] else 'None'}\n")

conn.close()

