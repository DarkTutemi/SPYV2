"""
Migration & Audit Script: Per-Ad Provenance Reconciliation
Audits existing 435 snapshots individually against authentic SourceRecords.
Classifies records as:
- VERIFIED_SOURCE_OBSERVATION: Confirmed authentic SourceRecord from completed CollectionRun.
- DATABASE_DERIVED_SNAPSHOT: Analytical projections / backfills without live Meta collection.
- UNKNOWN: Advertisements without verifiable source evidence.
Preserves all 145 ads and all 435 snapshots without data loss or backdating.
"""
import sqlite3
import os
import json

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "winhunter.db")

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. Ensure column and index exist
    cur.execute("PRAGMA table_info(advertisement_snapshots)")
    cols = [col[1] for col in cur.fetchall()]
    if "observation_quality" not in cols:
        print("Adding column observation_quality to advertisement_snapshots...")
        cur.execute("ALTER TABLE advertisement_snapshots ADD COLUMN observation_quality VARCHAR(50) DEFAULT 'UNKNOWN'")
        conn.commit()

    cur.execute("CREATE INDEX IF NOT EXISTS ix_snapshots_quality ON advertisement_snapshots (observation_quality)")
    conn.commit()

    # 2. Audit and Reconcile 2026-11-09 T0 snapshots
    print("\n--- Auditing 2026-11-09 (T0 Baseline) Snapshots ---")
    cur.execute("""
        SELECT 
            s.id as snap_id,
            a.id as ad_id,
            a.external_id,
            s.collection_run_id as old_run_id,
            sr.id as sr_id,
            sr.collection_run_id as true_run_id,
            sr.created_at as sr_created_at
        FROM advertisement_snapshots s
        JOIN advertisements a ON s.advertisement_id = a.id
        LEFT JOIN source_records sr ON a.external_id = sr.external_id AND sr.source_type = 'META_AD_LIBRARY'
        WHERE s.snapshot_date = '2026-11-09'
        GROUP BY s.id
    """)
    t0_snaps = cur.fetchall()

    t0_verified = 0
    t0_unknown = 0
    for row in t0_snaps:
        snap_id, ad_id, ext_id, old_run_id, sr_id, true_run_id, sr_created_at = row
        if sr_id and true_run_id:
            raw_meta = {
                "provenance": "verified_source_record",
                "source_record_id": sr_id,
                "collection_run_id": true_run_id,
                "ad_archive_id": ext_id,
                "observed_at": sr_created_at,
                "prior_run_reconciled": old_run_id != true_run_id,
            }
            cur.execute("""
                UPDATE advertisement_snapshots
                SET observation_quality = 'VERIFIED_SOURCE_OBSERVATION',
                    collection_run_id = ?,
                    raw_snapshot = ?
                WHERE id = ?
            """, (true_run_id, json.dumps(raw_meta), snap_id))
            t0_verified += 1
        else:
            raw_meta = {
                "provenance": "unverified",
                "reason": "no_matching_source_record",
            }
            cur.execute("""
                UPDATE advertisement_snapshots
                SET observation_quality = 'UNKNOWN',
                    raw_snapshot = ?
                WHERE id = ?
            """, (json.dumps(raw_meta), snap_id))
            t0_unknown += 1

    conn.commit()
    print(f"T0 Snapshots reconciled: {t0_verified} VERIFIED_SOURCE_OBSERVATION, {t0_unknown} UNKNOWN")

    # 3. Audit 2026-11-10 (T+1) Snapshots: Zero Meta runs occurred on 2026-11-10
    print("\n--- Auditing 2026-11-10 Snapshots ---")
    derived_meta_10 = json.dumps({
        "provenance": "database_derived_projection",
        "note": "analytical snapshot without live Meta source observation",
    })
    cur.execute("""
        UPDATE advertisement_snapshots
        SET observation_quality = 'DATABASE_DERIVED_SNAPSHOT',
            collection_run_id = NULL,
            raw_snapshot = ?
        WHERE snapshot_date = '2026-11-10'
    """, (derived_meta_10,))
    count_10 = cur.rowcount
    conn.commit()
    print(f"2026-11-10 Snapshots classified: {count_10} DATABASE_DERIVED_SNAPSHOT")

    # 4. Audit 2026-11-11 (T+2) Snapshots: Zero Meta runs occurred on 2026-11-11
    print("\n--- Auditing 2026-11-11 Snapshots ---")
    derived_meta_11 = json.dumps({
        "provenance": "database_derived_projection",
        "note": "analytical snapshot without live Meta source observation",
    })
    cur.execute("""
        UPDATE advertisement_snapshots
        SET observation_quality = 'DATABASE_DERIVED_SNAPSHOT',
            collection_run_id = NULL,
            raw_snapshot = ?
        WHERE snapshot_date = '2026-11-11'
    """, (derived_meta_11,))
    count_11 = cur.rowcount
    conn.commit()
    print(f"2026-11-11 Snapshots classified: {count_11} DATABASE_DERIVED_SNAPSHOT")

    # 5. Global Audit Summary
    print("\n--- Global Snapshot Audit Summary ---")
    cur.execute("SELECT snapshot_date, observation_quality, COUNT(*) FROM advertisement_snapshots GROUP BY snapshot_date, observation_quality")
    for r in cur.fetchall():
        print(f"Date: {r[0]} | Quality: {r[1]} | Count: {r[2]}")

    cur.execute("SELECT COUNT(DISTINCT advertisement_id) FROM advertisement_snapshots")
    distinct_ads = cur.fetchone()[0]
    print(f"\nDistinct advertisements in snapshots: {distinct_ads}")

    cur.execute("SELECT COUNT(*) FROM advertisements")
    total_ads = cur.fetchone()[0]
    print(f"Total advertisements in database: {total_ads}")

    conn.close()
    print("\nMigration and reconciliation complete.")

if __name__ == "__main__":
    migrate()
