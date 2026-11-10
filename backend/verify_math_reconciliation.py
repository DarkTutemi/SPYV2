import sqlite3
from pathlib import Path

db_path = Path(__file__).resolve().parent.parent / "data" / "winhunter.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

# Get all Phase 10 collection runs
c.execute("SELECT id FROM collection_runs WHERE started_at >= '2026-11-09 18:00:00'")
p10_run_ids = [r[0] for r in c.fetchall()]

# Get source records from Phase 10 runs
placeholders = ','.join('?' for _ in p10_run_ids)
c.execute(f"SELECT external_id, is_duplicate FROM source_records WHERE collection_run_id IN ({placeholders})", p10_run_ids)
p10_records = [dict(r) for r in c.fetchall()]

p10_total_fetched = len(p10_records)
p10_unique_exts = set(r['external_id'] for r in p10_records)

print(f"Phase 10 total source records fetched: {p10_total_fetched}")
print(f"Phase 10 unique external_ids fetched: {len(p10_unique_exts)}")

# Phase 7 collection run
p7_run_id = "0046dfa9-cc96-4b1c-aa7d-213a5de2c9ae"
c.execute("SELECT external_id FROM source_records WHERE collection_run_id = ?", (p7_run_id,))
p7_records = [dict(r) for r in c.fetchall()]
p7_total_fetched = len(p7_records)
p7_unique_exts = set(r['external_id'] for r in p7_records)

print(f"Phase 7 total source records fetched: {p7_total_fetched}")
print(f"Phase 7 unique external_ids fetched: {len(p7_unique_exts)}")

# Overlap between Phase 7 and Phase 10
cross_overlap = p7_unique_exts.intersection(p10_unique_exts)
print(f"Exact cross-run overlapping ad IDs: {len(cross_overlap)}")
print(f"Overlapping IDs: {cross_overlap}")

# Unique non-synthetic ads in advertisements table
c.execute("SELECT count(distinct external_id) FROM advertisements WHERE is_synthetic = 0")
print("Total non-synthetic distinct ads in advertisements table:", c.fetchone()[0])

# Verify arithmetic:
# If Phase 10 fetched 130 ads:
# Within Phase 10, how many unique ads?
# Let's see: 130 - 2 (the 2 ads that appeared in BOTH Task 7 and Task 13) = 128 unique ads in Phase 10!
# And of those 128 unique ads in Phase 10, 3 were already present in Phase 7 (the 3 cross-run overlapping ads)!
# So 128 - 3 = 125 newly introduced ads from Phase 10!
# 20 (Phase 7) + 125 (new Phase 10) = 145 unique ads in advertisements table!
print("\n--- MATHEMATICAL RECONCILIATION ---")
print(f"1. Original ads from first live run (Phase 7): {len(p7_unique_exts)}")
print(f"2. Unique ads fetched across 14 tasks in Phase 10: {len(p10_unique_exts)}")
print(f"3. Exactly cross-run overlapping ad IDs: {len(cross_overlap)} -> {cross_overlap}")
print(f"4. Newly added ads from Phase 10: {len(p10_unique_exts)} - {len(cross_overlap)} = {len(p10_unique_exts) - len(cross_overlap)}")
print(f"5. Total unique ads in DB: {len(p7_unique_exts)} + {len(p10_unique_exts) - len(cross_overlap)} = {len(p7_unique_exts) + len(p10_unique_exts) - len(cross_overlap)}")

conn.close()

