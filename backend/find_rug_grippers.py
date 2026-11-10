import sqlite3
from pathlib import Path

db_path = Path(__file__).resolve().parent.parent / "data" / "winhunter.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

print("--- SEARCH FOR RUG GRIPPERS IN ADVERTISEMENTS ---")
c.execute("SELECT id, external_id, title, body, landing_page_url, advertiser_id FROM advertisements WHERE title LIKE '%rug%' OR body LIKE '%rug%' OR landing_page_url LIKE '%rug%'")
rows = c.fetchall()
print(f"Found {len(rows)} ads matching 'rug':")
for r in rows:
    c.execute("SELECT name, facebook_page_id, domain FROM advertisers WHERE id = ?", (r['advertiser_id'],))
    adv = c.fetchone()
    print(f"Ad external_id: {r['external_id']} | Advertiser: {adv['name'] if adv else 'Unknown'} | Domain: {adv['domain'] if adv else 'Unknown'}")
    print(f"  Title: {r['title']}")
    print(f"  Landing: {r['landing_page_url']}")

print("\n--- SEARCH FOR GRIDSPARKL ADS ---")
c.execute("SELECT a.id, a.external_id, a.title, a.landing_page_url, adv.name, adv.facebook_page_id, adv.domain FROM advertisements a JOIN advertisers adv ON a.advertiser_id = adv.id WHERE adv.domain LIKE '%gridsparkl%' OR adv.name LIKE '%Gridsparkl%'")
rows = c.fetchall()
print(f"Found {len(rows)} ads for Gridsparkl:")
for r in rows:
    print(f"Ad external_id: {r['external_id']} | Title: {r['title']} | Landing: {r['landing_page_url']}")

conn.close()

