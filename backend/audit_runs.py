import json
from pathlib import Path
import sqlite3

# Check data_inventory.json
inv_path = Path(__file__).resolve().parent / "data_inventory.json"
if inv_path.exists():
    with open(inv_path, "r", encoding="utf-8") as f:
        inv = json.load(f)
    print("data_inventory keys:", list(inv.keys()) if isinstance(inv, dict) else len(inv))
    if isinstance(inv, dict):
        for k, v in inv.items():
            if isinstance(v, list):
                print(f"  {k}: {len(v)} items")
            elif isinstance(v, dict):
                print(f"  {k}: dict with {len(v)} keys")
            else:
                print(f"  {k}: {v}")

# Also check collection_runs table details
db_path = Path(__file__).resolve().parent.parent / "data" / "winhunter.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.execute("SELECT * FROM collection_runs WHERE started_at >= '2026-11-09'")
runs = [dict(r) for r in c.fetchall()]
print(f"\nRuns since 2026-11-09: {len(runs)}")
total_fetched = sum(r['records_fetched'] for r in runs)
total_new = sum(r['records_new'] for r in runs)
total_dup = sum(r['records_duplicate'] for r in runs)
print(f"Total fetched: {total_fetched}, new: {total_new}, duplicate: {total_dup}")

# Check Phase 7 run vs Phase 10 runs
phase7_run = runs[0]
phase10_runs = runs[1:]
print(f"Phase 7 run: fetched={phase7_run['records_fetched']}, new={phase7_run['records_new']}")
p10_fetched = sum(r['records_fetched'] for r in phase10_runs)
p10_new = sum(r['records_new'] for r in phase10_runs)
p10_dup = sum(r['records_duplicate'] for r in phase10_runs)
print(f"Phase 10 runs: count={len(phase10_runs)}, fetched={p10_fetched}, new={p10_new}, duplicate={p10_dup}")

conn.close()

