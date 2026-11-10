import urllib.request
import urllib.error
import ssl
import json
import re
from datetime import datetime, timezone

stores = [
    {
        "product": "Reusable dog pee pads",
        "brand": "Diego's Paws",
        "url": "https://diegospaws.com/products/reusable-waterproof-absorbent-pet-pad",
        "reported_price": "$39.90 bundle (Buy 2 Get 1 Free) / $29.99 single",
        "ad_id": "1654383812796911"
    },
    {
        "product": "Men's leakproof boxers",
        "brand": "Menvault",
        "url": "https://menvault.com/pages/7-reasons-why-menvault-boxers",
        "reported_price": "$69.00 (3-pack bundle)",
        "ad_id": "1135373669505006"
    },
    {
        "product": "Spin mop heads",
        "brand": "Swiftlifty",
        "url": "https://www.swiftlifty.com/products/last-day-49-off-2026-upgraded-spin-mop-heads-with-scrubbing-pad-2",
        "reported_price": "$39.99 (5-pack) / $24.99 (3-pack)",
        "ad_id": "1822961982334971"
    },
    {
        "product": "Chair leg protectors",
        "brand": "AlexCove",
        "url": "https://alexcove.com/products/clearguard-chair-leg-protectors",
        "reported_price": "$39.99 (32-pack) / $29.99 (24-pack) / $19.99 (16-pack)",
        "ad_id": "1441655818106115"
    },
    {
        "product": "Car detailing towels",
        "brand": "Novtris / Cresomall",
        "url": "https://www.novtris.com/funnel/news-professional-synthetic-clay-towel-for-advanced-auto-detailing-m",
        "url_alt": "https://www.cresomall.com/products/microfiber-car-drying-tow",
        "reported_price": "$39.99 (6-pack detailing set)",
        "ad_id": "1385909230286911"
    },
    {
        "product": "Rug grippers",
        "brand": "Gridsparkl",
        "url": "https://gridsparkl.com/products/rubber-anti-curling-non-slip-skid-pads-8pc-set",
        "reported_price": "$20.79 (8-piece set)",
        "ad_id": "1102527249449007 (User listed: 1691452315890995)"
    }
]

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
ctx = ssl.create_default_context()

landing_results = []

for s in stores:
    url = s["url"]
    print(f"\nChecking Landing URL for {s['brand']}: {url}")
    req = urllib.request.Request(url, headers=headers)
    obs_time = datetime.now(timezone.utc).isoformat()
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            code = resp.getcode()
            html = resp.read().decode("utf-8", errors="replace")
            print(f"  HTTP: {code}, Length: {len(html)}")
            
            # Look for JSON-LD or meta tags or shopify product json
            price_meta = re.findall(r'<meta\s+property=["\']og:price:amount["\']\s+content=["\']([\d\.]+)["\']', html, re.I)
            if not price_meta:
                price_meta = re.findall(r'"price":\s*"?([\d\.]+)"?', html)
            
            # Look for bundle prices mentioned in text
            print(f"  Extracted raw price matches: {price_meta[:5] if price_meta else 'None'}")
            
            landing_results.append({
                "brand": s["brand"],
                "product": s["product"],
                "url": url,
                "http_status": code,
                "timestamp": obs_time,
                "prices_found": price_meta[:5],
                "reported_price": s["reported_price"],
                "ad_id": s["ad_id"]
            })
    except urllib.error.HTTPError as e:
        print(f"  HTTP Error: {e.code} - {e.reason}")
        landing_results.append({
            "brand": s["brand"],
            "product": s["product"],
            "url": url,
            "http_status": e.code,
            "timestamp": obs_time,
            "error": str(e),
            "reported_price": s["reported_price"],
            "ad_id": s["ad_id"]
        })
    except Exception as e:
        print(f"  Error: {e}")
        landing_results.append({
            "brand": s["brand"],
            "product": s["product"],
            "url": url,
            "http_status": None,
            "timestamp": obs_time,
            "error": str(e),
            "reported_price": s["reported_price"],
            "ad_id": s["ad_id"]
        })

with open("fresh_landing_audit.json", "w", encoding="utf-8") as f:
    json.dump(landing_results, f, indent=2)

