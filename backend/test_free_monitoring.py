import urllib.request
import urllib.error
import ssl
import re
from datetime import datetime, timezone

ad_ids = [
    ("1654383812796911", "Reusable dog pee pads"),
    ("1135373669505006", "Men's leakproof boxers"),
    ("1822961982334971", "Spin mop heads"),
    ("1441655818106115", "Chair leg protectors"),
    ("1385909230286911", "Car detailing towels"),
    ("1691452315890995", "Rug grippers (DB: Dog boots)")
]

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1"
}

ctx = ssl.create_default_context()

results = []

for aid, label in ad_ids:
    url = f"https://www.facebook.com/ads/library/?id={aid}"
    obs_time = datetime.now(timezone.utc).isoformat()
    print(f"\nTesting Ad ID: {aid} ({label})")
    print(f"URL: {url}")
    
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            status_code = resp.getcode()
            final_url = resp.geturl()
            html = resp.read().decode("utf-8", errors="replace")
            print(f"  HTTP Status: {status_code}")
            print(f"  Final URL: {final_url}")
            print(f"  HTML length: {len(html)} bytes")
            
            # Check for bot challenge, login redirect, or page title
            title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE)
            title_text = title_match.group(1) if title_match else "No title"
            print(f"  Page title: {title_text}")
            
            # Check if Meta returns "Active" or "Inactive" in text or JSON
            has_active = bool(re.search(r'\b(Active|active)\b', html))
            has_inactive = bool(re.search(r'\b(Inactive|inactive)\b', html))
            has_login = "login" in final_url.lower() or "log in" in html.lower()
            has_checkpoint = "checkpoint" in final_url.lower() or "captcha" in html.lower()
            
            # Look for specific Meta ad library data markers
            has_ad_data = aid in html
            print(f"  Contains Ad ID in HTML: {has_ad_data}")
            print(f"  Contains 'Active': {has_active}, Contains 'Inactive': {has_inactive}")
            print(f"  Login redirect: {has_login}, Checkpoint/Captcha: {has_checkpoint}")
            
            results.append({
                "ad_id": aid,
                "label": label,
                "url": url,
                "observation_timestamp": obs_time,
                "http_status": status_code,
                "final_url": final_url,
                "html_len": len(html),
                "title": title_text,
                "has_ad_id": has_ad_data,
                "has_active": has_active,
                "has_inactive": has_inactive,
                "has_login": has_login,
                "has_checkpoint": has_checkpoint
            })
    except urllib.error.HTTPError as e:
        print(f"  HTTP Error: {e.code} - {e.reason}")
        results.append({
            "ad_id": aid,
            "label": label,
            "url": url,
            "observation_timestamp": obs_time,
            "http_status": e.code,
            "error": str(e)
        })
    except Exception as e:
        print(f"  Network / Other Error: {e}")
        results.append({
            "ad_id": aid,
            "label": label,
            "url": url,
            "observation_timestamp": obs_time,
            "http_status": None,
            "error": str(e)
        })

import json
with open("free_monitoring_test_raw.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)
print("\nResults saved to free_monitoring_test_raw.json")

