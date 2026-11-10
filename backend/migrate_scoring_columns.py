import sqlite3

conn = sqlite3.connect("../data/winhunter.db")
cur = conn.cursor()

# Get existing columns
cur.execute("PRAGMA table_info(opportunity_scores)")
existing = {r[1] for r in cur.fetchall()}

new_columns = [
    ("commercial_model", "VARCHAR(50) DEFAULT 'MODEL_A_SINGLE_PRODUCT'"),
    ("core_opportunity_score", "FLOAT DEFAULT 0.0"),
    ("bundle_upside_score", "FLOAT DEFAULT 0.0"),
    ("why_it_ranks_high", "TEXT"),
    ("why_it_might_fail", "TEXT"),
    ("what_evidence_supports_it", "TEXT"),
    ("what_remains_unknown", "TEXT"),
    ("next_validation_action", "TEXT"),
]

for col_name, col_type in new_columns:
    if col_name not in existing:
        cur.execute(f"ALTER TABLE opportunity_scores ADD COLUMN {col_name} {col_type}")
        print(f"Added column: {col_name}")
    else:
        print(f"Column already exists: {col_name}")

conn.commit()
conn.close()
print("Migration completed successfully.")

