import sqlite3
from pathlib import Path

db_path = Path(__file__).resolve().parent.parent / "data" / "winhunter.db"
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("--- Snapshot collection_run_ids ---")
c.execute("SELECT collection_run_id, count(*) FROM advertisement_snapshots GROUP BY collection_run_id")
for row in c.fetchall():
    print(row)

print("--- How were the 20 original ads and 128 Phase 10 ads imported? ---")
# Let's inspect the raw_data or look at all advertisements
c.execute("SELECT id, external_id, title, created_at, raw_data FROM advertisements WHERE is_synthetic = 0 LIMIT 5")
for r in c.fetchall():
    raw = r[4]
    # check keys in raw
    import json
    parsed = json.loads(raw) if raw else {}
    print(f"Ad {r[0]} ext={r[1]} created={r[3]} raw_keys={list(parsed.keys())}")

conn.close()
