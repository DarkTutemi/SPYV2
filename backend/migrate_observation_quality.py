"""
Migration script: add observation_quality to advertisement_snapshots.
Classifies historical snapshots:
- collection_run_id IS NOT NULL -> GENUINE_SOURCE_OBSERVATION
- collection_run_id IS NULL -> DATABASE_DERIVED_SNAPSHOT
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "winhunter.db")

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. Check existing columns
    cur.execute("PRAGMA table_info(advertisement_snapshots)")
    cols = [col[1] for col in cur.fetchall()]
    
    if "observation_quality" not in cols:
        print("Adding column observation_quality to advertisement_snapshots...")
        cur.execute("ALTER TABLE advertisement_snapshots ADD COLUMN observation_quality VARCHAR(50) DEFAULT 'UNKNOWN'")
        conn.commit()
    else:
        print("Column observation_quality already exists.")

    # 2. Backfill existing rows
    cur.execute("""
        UPDATE advertisement_snapshots 
        SET observation_quality = 'GENUINE_SOURCE_OBSERVATION'
        WHERE collection_run_id IS NOT NULL
    """)
    cur.execute("""
        UPDATE advertisement_snapshots 
        SET observation_quality = 'DATABASE_DERIVED_SNAPSHOT'
        WHERE collection_run_id IS NULL
    """)
    conn.commit()

    # 3. Create index if not exists
    cur.execute("CREATE INDEX IF NOT EXISTS ix_snapshots_quality ON advertisement_snapshots (observation_quality)")
    conn.commit()

    # 4. Verify counts
    cur.execute("SELECT observation_quality, COUNT(*) FROM advertisement_snapshots GROUP BY observation_quality")
    quality_counts = cur.fetchall()
    print("Snapshot counts by observation quality:", quality_counts)

    cur.execute("SELECT COUNT(DISTINCT advertisement_id) FROM advertisement_snapshots")
    distinct_ads = cur.fetchone()[0]
    print(f"Distinct advertisements in snapshots: {distinct_ads}")

    cur.execute("SELECT COUNT(*) FROM advertisements")
    total_ads = cur.fetchone()[0]
    print(f"Total advertisements in database: {total_ads}")

    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
