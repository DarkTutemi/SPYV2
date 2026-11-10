import sqlite3
from pathlib import Path

db_path = Path(__file__).resolve().parent.parent / "data" / "winhunter.db"
conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("DELETE FROM collection_runs WHERE job_id IN (SELECT id FROM collection_jobs WHERE name = 'test_t14_preflight_reservation')")
c.execute("DELETE FROM collection_jobs WHERE name = 'test_t14_preflight_reservation'")
conn.commit()
print("Cleaned up dummy reservation rows")
conn.close()

