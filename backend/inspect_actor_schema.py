import urllib.request
import json

url = "https://api.apify.com/v2/acts/automation-lab~facebook-ads-library/versions/0.1"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        print("Version 0.1 endpoint response keys:", list(res.keys()))
        data = res.get("data", {})
        print("data keys:", list(data.keys()))
        schema = data.get("inputSchema")
        if schema:
            if isinstance(schema, str):
                schema = json.loads(schema)
            print("Schema properties:", list(schema.get("properties", {}).keys()))
            for k, v in schema.get("properties", {}).items():
                print(f"  {k}: {v.get('type')} | title: {v.get('title')} | desc: {v.get('description')}")
        readme = data.get("readme")
        if readme:
            with open("actor_readme.md", "w", encoding="utf-8") as f:
                f.write(readme)
            print("Saved actor_readme.md, length:", len(readme))
except Exception as e:
    print("Error:", e)
