import json
from pathlib import Path

def inspect_tiktok():
    p = Path("backend/pilot_raw_tiktok_creative_center.json")
    if not p.exists(): return
    with open(p, encoding="utf-8") as f:
        items = json.load(f)
    print("=== TIKTOK CREATIVE CENTER (Count:", len(items), ") ===")
    for i, it in enumerate(items[:10]):
        print(f"[{i+1}] Title: {it.get('title')} | Brand: {it.get('brandName')} | Likes: {it.get('likes')} | Industry: {it.get('industry')}")
        print(f"    Search Query: {it.get('search')} | Video URL: {it.get('videoUrl')}")

def inspect_amazon():
    p = Path("backend/pilot_raw_amazon_us.json")
    if not p.exists(): return
    with open(p, encoding="utf-8") as f:
        items = json.load(f)
    print("\n=== AMAZON US (Count:", len(items), ") ===")
    for i, it in enumerate(items[:15]):
        print(f"[{i+1}] Title: {it.get('title')[:60]}... | Price: ${it.get('price')} | Stars: {it.get('stars')} | ASIN: {it.get('asin')}")
        print(f"    URL: {it.get('url')}")

def inspect_trends():
    p = Path("backend/pilot_raw_google_trends.json")
    if not p.exists(): return
    with open(p, encoding="utf-8") as f:
        items = json.load(f)
    print("\n=== GOOGLE TRENDS (Count:", len(items), ") ===")
    for i, it in enumerate(items):
        term = it.get("searchTerm") or it.get("keyword") or it.get("query")
        avg_interest = it.get("interestOverTime")
        print(f"[{i+1}] Term: {term} | Keys: {list(it.keys())}")

def inspect_shopify():
    p = Path("backend/pilot_raw_shopify_catalog.json")
    if not p.exists(): return
    with open(p, encoding="utf-8") as f:
        items = json.load(f)
    print("\n=== SHOPIFY CATALOG (Count:", len(items), ") ===")
    for i, it in enumerate(items[:15]):
        variants = it.get("variants") or []
        prices = [v.get("price") for v in variants if v.get("price")]
        print(f"[{i+1}] Title: {it.get('title')} | Vendor: {it.get('vendor')} | Prices: {prices[:3]} | Variants: {len(variants)}")
        print(f"    URL: {it.get('url')}")

if __name__ == "__main__":
    inspect_tiktok()
    inspect_amazon()
    inspect_trends()
    inspect_shopify()

