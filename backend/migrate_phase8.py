import sqlite3
import os

db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "winhunter.db"))
print(f"Opening DB at: {db_path}")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

def get_columns(table):
    cursor.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cursor.fetchall()]

# 1. products
prod_cols = get_columns("products")
print("Existing products columns:", prod_cols)
if "opportunity_status" not in prod_cols:
    cursor.execute("ALTER TABLE products ADD COLUMN opportunity_status VARCHAR(50) DEFAULT 'NEW_DISCOVERY'")
    print("Added products.opportunity_status")
if "primary_bundle_qty" not in prod_cols:
    cursor.execute("ALTER TABLE products ADD COLUMN primary_bundle_qty INTEGER NULL")
    print("Added products.primary_bundle_qty")

# 2. opportunity_scores
opp_cols = get_columns("opportunity_scores")
print("Existing opportunity_scores columns:", opp_cols)
col_defs = [
    ("discovery_signal_score", "FLOAT DEFAULT 0.0"),
    ("functional_benefit_score", "FLOAT DEFAULT 0.0"),
    ("observed_momentum", "FLOAT NULL"),
    ("opportunity_status", "VARCHAR(50) DEFAULT 'NEW_DISCOVERY'"),
    ("status_reason", "TEXT NULL"),
    ("natural_bundle_quantity", "INTEGER NULL"),
    ("independent_advertisers_count", "INTEGER DEFAULT 1"),
]
for col_name, col_type in col_defs:
    if col_name not in opp_cols:
        cursor.execute(f"ALTER TABLE opportunity_scores ADD COLUMN {col_name} {col_type}")
        print(f"Added opportunity_scores.{col_name}")

# 3. bundle_offers
bundle_cols = get_columns("bundle_offers")
print("Existing bundle_offers columns:", bundle_cols)

conn.commit()
conn.close()
print("Migration completed successfully!")

