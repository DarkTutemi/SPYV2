import sqlite3
import json

conn = sqlite3.connect("../data/winhunter.db")
cur = conn.cursor()
cur.execute("SELECT name FROM products")
db_names = [r[0].lower() for r in cur.fetchall()]
conn.close()

with open("pilot_raw_shopify_catalog.json", "r", encoding="utf-8") as f:
    shopify_items = json.load(f)

print(f"Total existing products in winhunter.db: {len(db_names)}")
print(f"Total raw products in Shopify catalog: {len(shopify_items)}")

new_products = []
for it in shopify_items:
    title = it.get("title")
    if not title:
        continue
    title_lower = title.lower()
    match = any(title_lower in n or n in title_lower for n in db_names)
    if not match:
        variants = it.get("variants", [])
        prices = [v.get("price") for v in variants if v.get("price")]
        vendor = it.get("vendor")
        new_products.append({
            "title": title,
            "vendor": vendor,
            "prices": prices,
            "handle": it.get("handle"),
            "url": f"https://{vendor.lower().replace(' ', '')}.com/products/{it.get('handle')}" if vendor else ""
        })

print(f"\nGenuinely distinct Shopify products NOT in winhunter.db: {len(new_products)}")
for i, np in enumerate(new_products, 1):
    print(f"{i:2}. [{np['vendor']}] {np['title']} | Prices: {np['prices'][:3]}")

