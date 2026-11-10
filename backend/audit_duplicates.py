import sqlite3
import json
from pathlib import Path

db_path = Path(__file__).resolve().parent.parent / "data" / "winhunter.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

# Check collection_runs details for Phase 10
c.execute("SELECT id, job_id, records_fetched, records_new, records_duplicate, coverage_notes FROM collection_runs WHERE started_at >= '2026-11-09 18:00:00'")
p10_runs = [dict(r) for r in c.fetchall()]
for r in p10_runs:
    print(f"Run {r['id'][:8]}: fetched={r['records_fetched']}, new={r['records_new']}, dup={r['records_duplicate']}, notes={r['coverage_notes']}")

# Look at apify_reconciliation_live.json
recon_file = Path(__file__).resolve().parent / "apify_reconciliation_live.json"
if recon_file.exists():
    with open(recon_file, "r", encoding="utf-8") as f:
        recon = json.load(f)
    print("\nReconciliation live runs:", len(recon))
    for r in recon:
        print(f"  Task: {r.get('task_name')}, RunID: {r.get('run_id')}, DatasetID: {r.get('dataset_id')}")

conn.close()

