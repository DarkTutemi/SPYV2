import urllib.request
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.core.config import get_settings

token = get_settings().apify_api_token
url = "https://api.apify.com/v2/acts/automation-lab~facebook-ads-library/builds?limit=1&desc=true"
req = urllib.request.Request(url, headers={
    "User-Agent": "Mozilla/5.0",
    "Authorization": f"Bearer {token}"
})

with urllib.request.urlopen(req, timeout=10) as resp:
    res = json.loads(resp.read().decode("utf-8"))
    items = res.get("data", {}).get("items", [])
    if items:
        build = items[0]
        print("build keys:", list(build.keys()))
        build_id = build['id']

# Query specific build:
url_b = f"https://api.apify.com/v2/acts/automation-lab~facebook-ads-library/builds/{build_id}"
req_b = urllib.request.Request(url_b, headers={"Authorization": f"Bearer {token}"})
with urllib.request.urlopen(req_b, timeout=10) as resp_b:
    res_b = json.loads(resp_b.read().decode("utf-8"))
    print("specific build keys:", list(res_b.get("data", {}).keys()))
    act_data = res_b.get("data", {})
    print("inputSchema:", bool(act_data.get("inputSchema")))
    if act_data.get("inputSchema"):
        print(act_data["inputSchema"])
