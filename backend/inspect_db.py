import sqlite3

conn = sqlite3.connect("../data/winhunter.db")
cursor = conn.cursor()

print("=== ADS FOR 0c32575b (Swiftlifty) ===")
for r in cursor.execute("SELECT id, title, landing_page_url, ad_url, first_seen_at FROM advertisements WHERE product_id='0c32575b-2c3f-41e1-9aa0-42a4f0fca060'"):
    print(r)

print("\n=== ADS FOR cb979fff (Gridsparkl) ===")
for r in cursor.execute("SELECT id, title, landing_page_url, ad_url, first_seen_at FROM advertisements WHERE product_id='cb979fff-f166-4a73-8a1c-2679158d789f'"):
    print(r)

print("\n=== ADS FOR 21be4a4b (Pawndify Flat Mop) ===")
for r in cursor.execute("SELECT id, title, landing_page_url, ad_url FROM advertisements WHERE product_id='21be4a4b-59ae-4d97-a523-8413cb12cff1'"):
    print(r)

print("\n=== ADS FOR d93334eb (Mop Replacement Cloth) ===")
for r in cursor.execute("SELECT id, title, landing_page_url, ad_url FROM advertisements WHERE product_id='d93334eb-2cd4-43b3-848f-7ad052c0a9ae'"):
    print(r)
