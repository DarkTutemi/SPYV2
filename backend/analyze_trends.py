import json

with open("backend/pilot_raw_google_trends.json", encoding="utf-8") as f:
    items = json.load(f)

print("=== GOOGLE TRENDS DEEP DIVE ===")
for it in items:
    term = it.get("searchTerm") or it.get("query")
    print(f"\nTerm: {term}")
    timeline = it.get("interestOverTime_timelineData") or []
    if timeline:
        values = [point.get("value", [0])[0] if isinstance(point.get("value"), list) else point.get("value", 0) for point in timeline]
        avg_val = sum(values) / len(values) if values else 0
        min_val = min(values) if values else 0
        max_val = max(values) if values else 0
        print(f"  Timeline: {len(timeline)} points | 90-day Avg: {avg_val:.1f} | Min: {min_val} | Max: {max_val}")
    subregions = it.get("interestBySubregion") or []
    if subregions:
        top_states = sorted(subregions, key=lambda x: x.get("value", [0])[0] if isinstance(x.get("value"), list) else x.get("value", 0), reverse=True)[:3]
        print(f"  Top States: {[s.get('geoName') for s in top_states]}")
    related = it.get("relatedQueries_rising") or it.get("relatedQueries_top") or []
    if related:
        print(f"  Related queries: {[r.get('query') for r in related[:3]]}")

