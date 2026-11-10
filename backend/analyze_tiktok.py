import json

with open("backend/pilot_raw_tiktok_creative_center.json", encoding="utf-8") as f:
    items = json.load(f)

print(f"Total TikTok items: {len(items)}")
for i, it in enumerate(items):
    print(f"\nItem #{i+1}:")
    for k in ["title", "brandName", "likes", "ctrTopPercent", "budget", "industry", "search", "url"]:
        print(f"  {k}: {it.get(k)}")

