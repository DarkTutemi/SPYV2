import json
from pathlib import Path

offers_path = Path(__file__).resolve().parent / "verified_commercial_offers.json"
with open(offers_path, "r", encoding="utf-8") as f:
    offers = json.load(f)

for i, o in enumerate(offers):
    print(f"[{i+1}] {o.get('product_name')} | Brand: {o.get('brand')} | URL: {o.get('url')}")
    print(f"    HTTP: {o.get('http_status')} | Price: {o.get('price_displayed')} {o.get('currency')} | Bundle: {o.get('bundle_quantity')} | Pieces: {o.get('pieces_included')}")
    print(f"    Reliability: {o.get('observation_reliability')} | Notes: {o.get('notes')}")
