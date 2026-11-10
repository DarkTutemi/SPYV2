import sqlite3
import json
from pathlib import Path

db_path = Path(__file__).resolve().parent.parent / "data" / "winhunter.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

# Let's inspect source_records table if it exists
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print("Tables in DB:", tables)

# Check if there is a source_records or similar table
if 'source_records' in tables:
    c.execute("PRAGMA table_info(source_records)")
    print("source_records cols:", [r[1] for r in c.fetchall()])
    c.execute("SELECT count(*), is_duplicate, count(*) FROM source_records GROUP BY is_duplicate")
    print("source_records dupes:", c.fetchall())

# Check Phase 7 ads
phase7_run_id = "0046dfa9-cc96-4b1c-aa7d-213a5de2c9ae"
c.execute("SELECT id, external_id, title, advertiser_id FROM advertisements WHERE id IN (SELECT advertisement_id FROM advertisement_snapshots WHERE collection_run_id = ?)", (phase7_run_id,))
# wait, earlier we saw snapshots for phase 7 had collection_run_id = None!
# Let's find ads created at 15:08 UTC on 2026-11-09
c.execute("SELECT id, external_id, title, advertiser_id, created_at FROM advertisements WHERE created_at LIKE '2026-11-09 15:%'")
p7_ads = [dict(r) for r in c.fetchall()]
print(f"Phase 7 ads count: {len(p7_ads)}")
p7_ext_ids = {r['external_id'] for r in p7_ads}

# Check ads created in Task 7 (run 9cfcda2c) and Task 13 (run 0e502f33)
run7_id = "9cfcda2c-9dc8-4e69-a3fb-9ef2e56f5adc"
run13_id = "0e502f33-2b98-4e3c-a6a0-a25363d20714"

c.execute("SELECT a.external_id, a.title FROM advertisement_snapshots s JOIN advertisements a ON s.advertisement_id = a.id WHERE s.collection_run_id = ?", (run7_id,))
run7_snap_ads = [dict(r) for r in c.fetchall()]
print(f"Run 7 snap ads count: {len(run7_snap_ads)}")

c.execute("SELECT a.external_id, a.title FROM advertisement_snapshots s JOIN advertisements a ON s.advertisement_id = a.id WHERE s.collection_run_id = ?", (run13_id,))
run13_snap_ads = [dict(r) for r in c.fetchall()]
print(f"Run 13 snap ads count: {len(run13_snap_ads)}")

conn.close()

