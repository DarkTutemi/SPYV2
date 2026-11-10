import json
from collections import defaultdict

def analyze_all():
    # 1. Amazon items
    with open("backend/pilot_raw_amazon_us.json", encoding="utf-8") as f:
        amazon_items = json.load(f)

    # 2. Shopify items
    with open("backend/pilot_raw_shopify_catalog.json", encoding="utf-8") as f:
        shopify_items = json.load(f)

    # 3. Google Trends items
    with open("backend/pilot_raw_google_trends.json", encoding="utf-8") as f:
        trends_items = json.load(f)

    # 4. TikTok items
    with open("backend/pilot_raw_tiktok_creative_center.json", encoding="utf-8") as f:
        tiktok_items = json.load(f)

    print("=== DATA SUMMARY ===")
    print(f"Amazon items: {len(amazon_items)}")
    print(f"Shopify items: {len(shopify_items)}")
    print(f"Trends items: {len(trends_items)}")
    print(f"TikTok items: {len(tiktok_items)}")

    print("\n--- ALL AMAZON PRODUCTS ---")
    for i, it in enumerate(amazon_items):
        t = it.get("title", "")
        p = it.get("price")
        stars = it.get("stars")
        asin = it.get("asin")
        print(f"[{i+1}] {t[:70]} | ${p} | {stars}* | ASIN: {asin}")

    print("\n--- ALL SHOPIFY PRODUCTS ---")
    for i, it in enumerate(shopify_items):
        t = it.get("title")
        if not t: continue
        v = it.get("vendor")
        variants = it.get("variants") or []
        prices = [var.get("price") for var in variants if var.get("price")]
        print(f"[{i+1}] {t} | Vendor: {v} | Prices: {prices[:4]} | URL: {it.get('url')}")

    print("\n--- GOOGLE TRENDS AVERAGES ---")
    for it in trends_items:
        term = it.get("searchTerm") or it.get("query")
        avg = it.get("interestOverTime_averages") or it.get("averages")
        timeline = it.get("interestOverTime_timelineData") or []
        print(f"Term: {term} | Averages: {avg} | Timeline points: {len(timeline)}")

    print("\n--- TIKTOK ADS WITH CONTENT ---")
    for it in tiktok_items:
        if it.get("title") or it.get("brandName"):
            print(f"Title: {it.get('title')} | Brand: {it.get('brandName')} | Likes: {it.get('likes')} | Industry: {it.get('industry')} | Search: {it.get('search')}")

if __name__ == "__main__":
    analyze_all()

