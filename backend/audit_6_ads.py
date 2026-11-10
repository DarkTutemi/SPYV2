import sqlite3
from pathlib import Path

db_path = Path(__file__).resolve().parent.parent / "data" / "winhunter.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.execute("PRAGMA table_info(advertisers)")
adv_cols = [r[1] for r in c.fetchall()]
print("advertisers cols:", adv_cols)

ad_ids = [
    '1654383812796911', # Reusable dog pee pads (Diego's Paws)
    '1135373669505006', # Men's leakproof boxers (Menvault)
    '1822961982334971', # Spin mop heads (Swiftlifty)
    '1441655818106115', # Chair leg protectors (AlexCove)
    '1385909230286911', # Car detailing towels (Novtris)
    '1691452315890995'  # Rug grippers (Gridsparkl)
]

for aid in ad_ids:
    c.execute("SELECT * FROM advertisements WHERE external_id = ?", (aid,))
    row = c.fetchone()
    if row:
        adv_info = {}
        if row['advertiser_id']:
            c.execute("SELECT * FROM advertisers WHERE id = ?", (row['advertiser_id'],))
            adv = c.fetchone()
            if adv:
                adv_info = dict(adv)
        
        print(f"\n==========================================")
        print(f"Ad ID: {row['external_id']} | Advertiser: {adv_info.get('name')} (Domain: {adv_info.get('domain')})")
        print(f"Title: {row['title']}")
        print(f"Landing URL: {row['landing_page_url']}")
        print(f"Ad URL: {row['ad_url']}")
        print(f"Body: {row['body']}")
    else:
        print(f"Ad ID {aid} NOT FOUND in advertisements table!")

conn.close()
