import json

with open("new_research_raw_trends.json", encoding="utf-8") as f:
    trends = json.load(f)

print(f"=== NEW RESEARCH GOOGLE TRENDS RESULTS ({len(trends)} queries) ===")
for i, item in enumerate(trends, 1):
    q = item.get("searchTerm") or item.get("query")
    timeline = item.get("interestOverTime_timelineData") or []
    vals = [p.get("value", [0])[0] if isinstance(p.get("value"), list) else p.get("value", 0) for p in timeline]
    avg_interest = round(sum(vals) / len(vals), 1) if vals else 0.0
    rising = [r.get("query") for r in (item.get("relatedQueries_rising") or [])[:3]]
    top_queries = [r.get("query") for r in (item.get("relatedQueries_top") or [])[:3]]
    print(f"{i:2d}. Query: '{q}' | 90d Avg: {avg_interest}/100")
    print(f"    Rising: {rising}")
    print(f"    Top: {top_queries}")

with open("new_research_raw_amazon.json", encoding="utf-8") as f:
    amazon = json.load(f)

print(f"\n=== NEW RESEARCH AMAZON US RESULTS ({len(amazon)} items) ===")
for i, item in enumerate(amazon, 1):
    title = item.get("title", "")
    price = item.get("price") or item.get("prices") or item.get("priceValue")
    asin = item.get("asin", "")
    stars = item.get("stars") or item.get("rating")
    revs = item.get("reviewsCount") or item.get("ratingsTotal")
    url = item.get("url")
    print(f"{i:2d}. [{stars}* | {revs} revs] ${price} | ASIN: {asin} | {title[:60]}")

