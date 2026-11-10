import sqlite3
from pathlib import Path

db_path = Path(__file__).resolve().parent.parent / "data" / "winhunter.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.execute("SELECT is_duplicate, count(*) FROM source_records GROUP BY is_duplicate")
for r in c.fetchall():
    print("is_duplicate:", r[0], "count:", r[1])

c.execute("SELECT id, collection_run_id, external_id, is_duplicate, duplicate_of_id FROM source_records WHERE is_duplicate = 1")
dups = [dict(r) for r in c.fetchall()]
print(f"Total duplicate source records: {len(dups)}")
for d in dups:
    # find what duplicate_of_id points to
    orig_run = "UNKNOWN"
    if d['duplicate_of_id']:
        c.execute("SELECT collection_run_id, external_id FROM source_records WHERE id = ?", (d['duplicate_of_id'],))
        orig = c.fetchone()
        if orig:
            orig_run = orig['collection_run_id']
    print(f"  Dup external_id: {d['external_id']}, run: {str(d['collection_run_id'])[:8]}, duplicate_of: {d['duplicate_of_id']}, orig_run: {str(orig_run)[:8]}")

# Let's inspect Phase 7 collection run ID vs Phase 10 collection run IDs in source_records
p7_run_id = "0046dfa9-cc96-4b1c-aa7d-213a5de2c9ae"
c.execute("SELECT count(*) FROM source_records WHERE collection_run_id = ?", (p7_run_id,))
print(f"Source records in Phase 7 run: {c.fetchone()[0]}")

c.execute("SELECT count(*), count(distinct external_id) FROM source_records WHERE collection_run_id != ? AND is_synthetic = 0", (p7_run_id,))
tot_p10, uniq_p10 = c.fetchone()
print(f"Source records in Phase 10 runs: total={tot_p10}, unique_ext_ids={uniq_p10}")

# Check overlap between Phase 7 and Phase 10 in source_records:
c.execute("SELECT DISTINCT external_id FROM source_records WHERE collection_run_id = ?", (p7_run_id,))
p7_exts = {r[0] for r in c.fetchall()}

c.execute("SELECT DISTINCT external_id FROM source_records WHERE collection_run_id != ? AND is_synthetic = 0", (p7_run_id,))
p10_exts = {r[0] for r in c.fetchall()}

overlap = p7_exts.intersection(p10_exts)
print(f"Overlapping external_ids between Phase 7 and Phase 10: {len(overlap)}")
for ext in overlap:
    c.execute("SELECT id, title FROM advertisements WHERE external_id = ?", (ext,))
    ad = c.fetchone()
    print(f"  Overlap ext_id {ext}: {ad['title'] if ad else 'N/A'}")

# Total unique source records across both
all_exts = p7_exts.union(p10_exts)
print(f"Total genuinely unique Meta archive IDs across all runs: {len(all_exts)}")

conn.close()

