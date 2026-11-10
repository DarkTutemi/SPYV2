import urllib.request
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.core.config import get_settings

settings = get_settings()
token = settings.apify_api_token
headers = {"User-Agent": "Mozilla/5.0", "Authorization": f"Bearer {token}"}

actor_slug = "offgrid-labs~reddit-scraper"
url = f"https://api.apify.com/v2/acts/{actor_slug}/builds?limit=1&desc=true"

try:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        builds = json.loads(resp.read().decode("utf-8")).get("data", {}).get("items", [])
        if builds:
            b_id = builds[0]["id"]
            url_b = f"https://api.apify.com/v2/acts/{actor_slug}/builds/{b_id}"
            req_b = urllib.request.Request(url_b, headers=headers)
            with urllib.request.urlopen(req_b, timeout=10) as resp_b:
                b_data = json.loads(resp_b.read().decode("utf-8")).get("data", {})
                schema = b_data.get("inputSchema")
                if isinstance(schema, str):
                    schema = json.loads(schema)
                required = schema.get("required", [])
                print("Required fields for reddit scraper:", required)
                props = schema.get("properties", {})
                for k in ["clientId", "clientSecret", "appName", "redditUsername", "searchQueries", "subreddits"]:
                    if k in props:
                        print(f"  {k}: desc={props[k].get('description')}")
except Exception as e:
    print("Error:", e)

