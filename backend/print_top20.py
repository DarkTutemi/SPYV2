import json

with open("backend/top20_advertiser_evidence.json", encoding="utf-8") as f:
    items = json.load(f)

for i, x in enumerate(items):
    score = x.get("score") or 0.0
    adv = x.get("advertiser_name") or "Unknown"
    pid = x.get("page_id") or "None"
    arc = x.get("ad_archive_id") or "None"
    url = x.get("landing_url") or "None"
    sol = x.get("solution") or "None"
    name = x.get("product_name") or "None"
    flags = x.get("suspicious_flags") or []
    print(f"{i+1:2d}. [{score:4.1f}] {name[:35]:35s} | {sol[:25]:25s} | Adv: {adv[:15]:15s} | Page: {pid:18s} | Arc: {arc:18s} | Flags: {len(flags)}")

