import json

with open("backend/promising_audit_results.json", encoding="utf-8") as f:
    items = json.load(f)

for cat in ["HIGH_CONFIDENCE_PROMISING", "PLAUSIBLE_BUT_UNVERIFIED", "WEAK_MULTI_UNIT_DEMAND", "FALSE_POSITIVE"]:
    sub = [x for x in items if x["classification"] == cat]
    print(f"\n==================== {cat} ({len(sub)}) ====================")
    for i, x in enumerate(sub):
        score = x.get("score") or 0.0
        adv = x.get("advertiser") or "Unknown"
        url = x.get("landing_url") or "None"
        print(f"{i+1:2d}. [{score:4.1f}] {x['name'][:50]:50s} | Adv: {adv[:20]:20s} | URL: {url[:45]}")

