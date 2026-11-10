import json

with open("backend/multisource_schemas.json", encoding="utf-8") as f:
    data = json.load(f)

for k, v in data.items():
    print("=" * 40)
    print("ACTOR:", k)
    print("TITLE:", v.get("title"))
    s = v.get("input_schema") or {}
    print("REQUIRED:", s.get("required", []))
    props = s.get("properties", {})
    for p_name, p in props.items():
        desc = p.get("description", "")[:60]
        print(f"  {p_name} ({p.get('type')}, default={p.get('default')}): {desc}")

