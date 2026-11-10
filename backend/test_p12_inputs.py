import json
import os
from pathlib import Path

# Load reconciled Apify live data
with open("backend/apify_reconciliation_live.json", encoding="utf-8") as f:
    apify_data = json.load(f)

# Load verified commercial offers
with open("backend/verified_commercial_offers.json", encoding="utf-8") as f:
    offers_data = json.load(f)

# Load baseline records
with open("backend/t0_longitudinal_baseline.json", encoding="utf-8") as f:
    baseline_data = json.load(f)

# Load promising audit
with open("backend/promising_audit_results.json", encoding="utf-8") as f:
    promising_audit = json.load(f)

# Classify bundle necessity for 25 surviving candidates (19 High-Confidence + 6 Plausible)
surviving = [x for x in promising_audit if x["classification"] in ("HIGH_CONFIDENCE_PROMISING", "PLAUSIBLE_BUT_UNVERIFIED")]

print(f"Loaded: {len(apify_data)} runs, {len(offers_data)} offers, {len(baseline_data)} baseline ads, {len(surviving)} surviving candidates.")

