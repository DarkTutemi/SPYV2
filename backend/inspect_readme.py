import urllib.request
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.core.config import get_settings

token = get_settings().apify_api_token
build_id = "RbzHZOgC2D5vvhph0"
url = f"https://api.apify.com/v2/acts/automation-lab~facebook-ads-library/builds/{build_id}"
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})

with urllib.request.urlopen(req, timeout=10) as resp:
    res = json.loads(resp.read().decode("utf-8"))
    readme = res.get("data", {}).get("readme", "")
    with open("automation_lab_readme.md", "w", encoding="utf-8") as f:
        f.write(readme)
    print("Saved automation_lab_readme.md, length:", len(readme))

# Search for "id" in readme
import re
lines = readme.splitlines()
matches = [line for line in lines if any(w in line.lower() for w in ["ad id", "archive id", "exact id", "adarchiveid", "page_id", "adslibraryurls"])]
print(f"Found {len(matches)} relevant lines in readme:")
for m in matches[:15]:
    print("  ", m)

