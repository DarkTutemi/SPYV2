import sqlite3

conn = sqlite3.connect("../data/winhunter.db")
cur = conn.cursor()

print("=== DATA SOURCES ===")
for r in cur.execute("SELECT id, name, source_type FROM data_sources"):
    print(" ", r)

print("\n=== COLLECTION JOBS ===")
for r in cur.execute("SELECT id, name, job_type FROM collection_jobs"):
    print(" ", r)

print("\n=== COLLECTION RUNS (FIRST 5) ===")
for r in cur.execute("SELECT id, job_id, status FROM collection_runs LIMIT 5"):
    print(" ", r)

conn.close()

