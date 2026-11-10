import sqlite3
import os

db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "winhunter.db"))
print(f"Opening DB at: {db_path}")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

def get_columns(table):
    cursor.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cursor.fetchall()]

# 1. source_records
sr_cols = get_columns("source_records")
if "is_synthetic" not in sr_cols:
    cursor.execute("ALTER TABLE source_records ADD COLUMN is_synthetic BOOLEAN DEFAULT 0")
    print("Added source_records.is_synthetic")

# 2. advertisements
ad_cols = get_columns("advertisements")
if "is_synthetic" not in ad_cols:
    cursor.execute("ALTER TABLE advertisements ADD COLUMN is_synthetic BOOLEAN DEFAULT 0")
    print("Added advertisements.is_synthetic")

# 3. products
prod_cols = get_columns("products")
if "is_synthetic" not in prod_cols:
    cursor.execute("ALTER TABLE products ADD COLUMN is_synthetic BOOLEAN DEFAULT 0")
    print("Added products.is_synthetic")

# 4. opportunity_scores
opp_cols = get_columns("opportunity_scores")
col_defs = [
    ("observed_single_price_usd", "FLOAT NULL"),
    ("observed_bundle_price_usd", "FLOAT NULL"),
    ("estimated_bundle_scenario", "VARCHAR(150) NULL"),
    ("customer_aov_usd", "FLOAT NULL"),
    ("natural_quantity_rationale", "TEXT NULL"),
    ("ad_activity_observations", "JSON NULL"),
]
for col_name, col_type in col_defs:
    if col_name not in opp_cols:
        cursor.execute(f"ALTER TABLE opportunity_scores ADD COLUMN {col_name} {col_type}")
        print(f"Added opportunity_scores.{col_name}")

conn.commit()

# 5. Tag synthetic/demo records
cursor.execute("UPDATE products SET is_synthetic = 1 WHERE name LIKE 'DEMO %' OR id = 'bc7472c6-705b-41c3-97ff-26b858e86d5c'")
print(f"Flagged synthetic products: {cursor.rowcount} rows")

cursor.execute("""
UPDATE advertisements 
SET is_synthetic = 1 
WHERE product_id IN (SELECT id FROM products WHERE is_synthetic = 1)
   OR external_id LIKE 'demo_%' 
   OR external_id LIKE 'synth_%'
   OR external_id = 'real_meta_1001'
""")
print(f"Flagged synthetic advertisements: {cursor.rowcount} rows")

# 6. Deduplicate Swiftlifty & Gridsparkl Spin Mop Heads into canonical product
# Product 1: 0c32575b-2c3f-41e1-9aa0-42a4f0fca060 (Swiftlifty headline body)
# Product 2: cb979fff-f166-4a73-8a1c-2679158d789f (Gridsparkl)
cursor.execute("SELECT id FROM products WHERE id = '0c32575b-2c3f-41e1-9aa0-42a4f0fca060'")
has_dup = cursor.fetchone()

if has_dup:
    print("Deduplicating product 0c32575b into canonical cb979fff...")
    # Reassign ads
    cursor.execute("""
    UPDATE advertisements 
    SET product_id = 'cb979fff-f166-4a73-8a1c-2679158d789f' 
    WHERE product_id = '0c32575b-2c3f-41e1-9aa0-42a4f0fca060'
    """)
    print(f"Reassigned {cursor.rowcount} ads from 0c32575b to cb979fff")

    # Clean up scores and bundles for duplicate stub
    cursor.execute("DELETE FROM opportunity_scores WHERE product_id = '0c32575b-2c3f-41e1-9aa0-42a4f0fca060'")
    cursor.execute("DELETE FROM bundle_offers WHERE product_id = '0c32575b-2c3f-41e1-9aa0-42a4f0fca060'")
    cursor.execute("DELETE FROM product_daily_metrics WHERE product_id = '0c32575b-2c3f-41e1-9aa0-42a4f0fca060'")
    cursor.execute("DELETE FROM products WHERE id = '0c32575b-2c3f-41e1-9aa0-42a4f0fca060'")
    print("Deleted duplicate stub product 0c32575b")

    # Update canonical product title and metadata
    cursor.execute("""
    UPDATE products 
    SET name = '2026 Upgraded Spin Mop Replacement Heads with Scrubbing Pad',
        normalized_name = '2026 upgraded spin mop replacement heads with scrubbing pad',
        description = 'Microfiber replacement heads with scrubbing pads for spin mops. Fits standard 360 spin mop systems. Washable and reusable.',
        category = 'Home & Cleaning'
    WHERE id = 'cb979fff-f166-4a73-8a1c-2679158d789f'
    """)
    print("Updated canonical product metadata for cb979fff")

# Update category on remaining authentic products
cursor.execute("UPDATE products SET category = 'Home & Cleaning' WHERE category IS NULL AND is_synthetic = 0")

conn.commit()
conn.close()
print("Migration Phase 9 completed successfully!")

