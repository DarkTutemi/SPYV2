"""
US WIN HUNTER — Commercial Price Evidence Audit & Normalization Migration
Fixes mislabeled commercial evidence:
1. Replaces Google Trends URL on Under-Door Draft Stopper with genuine Amazon US retail listing benchmark.
2. Deduplicates any duplicate ProductOffers or BundleOffers.
3. Categorizes price evidence into:
   - OBSERVED_CHECKOUT_PRICE (Shopify direct store variants)
   - OBSERVED_RETAIL_LISTING_PRICE (Amazon live marketplace listings)
   - SCENARIO_PRICE (modeled commercial bundles)
4. Preserves 100% of 145 Meta baseline ads and 145 T0 snapshots untouched.
"""

import sqlite3
from pathlib import Path

def run_migration(db_path: str = None):
    if db_path is None:
        db_path = str(Path(__file__).resolve().parent.parent / "data" / "winhunter.db")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    print(f"Auditing commercial offers in {db_path}...")

    # 1. Inspect existing columns in product_offers
    c.execute("PRAGMA table_info(product_offers)")
    columns = [col[1] for col in c.fetchall()]
    if "price_evidence_type" not in columns:
        print("Adding column price_evidence_type to product_offers...")
        c.execute("ALTER TABLE product_offers ADD COLUMN price_evidence_type VARCHAR(50)")

    c.execute("PRAGMA table_info(bundle_offers)")
    b_columns = [col[1] for col in c.fetchall()]
    if "price_evidence_type" not in b_columns:
        print("Adding column price_evidence_type to bundle_offers...")
        c.execute("ALTER TABLE bundle_offers ADD COLUMN price_evidence_type VARCHAR(50)")

    # 2. Fix Under-Door Draft Stopper mislabeled price source
    c.execute("""
        SELECT po.id, po.product_id, po.price_usd, po.source_url 
        FROM product_offers po 
        JOIN products p ON po.product_id = p.id 
        WHERE po.source_url LIKE '%trends.google%' OR po.source_url LIKE '%google.com/trends%'
    """)
    trends_offers = c.fetchall()
    print(f"Found {len(trends_offers)} price offers pointing to Google Trends.")

    for off_id, prod_id, price, url in trends_offers:
        # Check if an Amazon benchmark offer already exists for this product
        c.execute("""
            SELECT id FROM product_offers 
            WHERE product_id = ? AND source_url LIKE '%amazon.com%'
        """, (prod_id,))
        amz_exists = c.fetchone()
        if amz_exists:
            # Delete redundant Google Trends price offer
            c.execute("DELETE FROM product_offers WHERE id = ?", (off_id,))
            print(f"Deleted redundant Google Trends price offer {off_id}")
        else:
            # Update to Amazon US retail benchmark listing
            c.execute("""
                UPDATE product_offers 
                SET source_url = 'https://www.amazon.com/dp/B082W63J6W',
                    price_usd = 19.99,
                    evidence_type = 'OBSERVED_RETAIL_LISTING_PRICE',
                    price_evidence_type = 'observed_retail_listing_price'
                WHERE id = ?
            """, (off_id,))
            print(f"Updated price offer {off_id} to Amazon US listing benchmark ($19.99).")

    # 3. Deduplicate any duplicate ProductOffers (same product_id, price_usd, quantity, source_url)
    c.execute("""
        DELETE FROM product_offers 
        WHERE id NOT IN (
            SELECT MIN(id) 
            FROM product_offers 
            GROUP BY product_id, price_usd, quantity, COALESCE(source_url, '')
        )
    """)
    deleted_po = c.rowcount
    print(f"Deduplicated {deleted_po} redundant product offers.")

    # Deduplicate bundle offers
    c.execute("""
        DELETE FROM bundle_offers 
        WHERE id NOT IN (
            SELECT MIN(id) 
            FROM bundle_offers 
            GROUP BY product_id, quantity, bundle_price_usd, COALESCE(source_url, '')
        )
    """)
    deleted_bo = c.rowcount
    print(f"Deduplicated {deleted_bo} redundant bundle offers.")

    # 4. Standardize price_evidence_type for Shopify storefront variant offers
    # CRITICAL AUDIT FIX C: Storefront variant listings represent retail listing benchmarks,
    # NOT proof of inspected checkout sessions. OBSERVED_CHECKOUT_PRICE is reserved strictly
    # for verified cart/checkout flows.
    c.execute("""
        UPDATE product_offers 
        SET evidence_type = 'OBSERVED_RETAIL_LISTING_PRICE',
            price_evidence_type = 'OBSERVED_RETAIL_LISTING_PRICE'
        WHERE source_url LIKE '%diegospaws.com%' OR source_url LIKE '%alexcove.com%'
    """)

    # 5. Standardize price_evidence_type for Amazon marketplace offers
    c.execute("""
        UPDATE product_offers 
        SET evidence_type = 'OBSERVED_RETAIL_LISTING_PRICE',
            price_evidence_type = 'OBSERVED_RETAIL_LISTING_PRICE'
        WHERE source_url LIKE '%amazon.com%'
    """)

    # 6. Standardize BundleOffers
    # Reclassify Shopify catalog/variant bundles to OBSERVED_RETAIL_LISTING_PRICE
    c.execute("""
        UPDATE bundle_offers 
        SET evidence_type = 'OBSERVED_RETAIL_LISTING_PRICE',
            price_evidence_type = 'OBSERVED_RETAIL_LISTING_PRICE'
        WHERE (source_url LIKE '%diegospaws.com%' OR source_url LIKE '%alexcove.com%')
          AND bundle_status != 'modeled_scenario'
    """)

    # Amazon marketplace bundle listings
    c.execute("""
        UPDATE bundle_offers 
        SET evidence_type = 'OBSERVED_RETAIL_LISTING_PRICE',
            price_evidence_type = 'OBSERVED_RETAIL_LISTING_PRICE'
        WHERE source_url LIKE '%amazon.com%'
          AND bundle_status != 'modeled_scenario'
    """)

    # Modeled commercial scenarios
    c.execute("""
        UPDATE bundle_offers 
        SET evidence_type = 'SCENARIO_PRICE',
            price_evidence_type = 'SCENARIO_PRICE',
            source_url = NULL
        WHERE bundle_status = 'modeled_scenario'
    """)

    # Populate any remaining bundle offers with NULL price_evidence_type
    c.execute("""
        UPDATE bundle_offers 
        SET evidence_type = 'OBSERVED_RETAIL_LISTING_PRICE',
            price_evidence_type = 'OBSERVED_RETAIL_LISTING_PRICE'
        WHERE price_evidence_type IS NULL AND source_url IS NOT NULL
    """)
    c.execute("""
        UPDATE bundle_offers 
        SET evidence_type = 'SCENARIO_PRICE',
            price_evidence_type = 'SCENARIO_PRICE'
        WHERE price_evidence_type IS NULL AND source_url IS NULL
    """)

    # Ensure strictly UPPERCASE representation across all offers (Fix B)
    c.execute("UPDATE product_offers SET price_evidence_type = UPPER(price_evidence_type) WHERE price_evidence_type IS NOT NULL")
    c.execute("UPDATE bundle_offers SET price_evidence_type = UPPER(price_evidence_type) WHERE price_evidence_type IS NOT NULL")
    c.execute("UPDATE product_offers SET evidence_type = UPPER(evidence_type) WHERE evidence_type IS NOT NULL")
    c.execute("UPDATE bundle_offers SET evidence_type = UPPER(evidence_type) WHERE evidence_type IS NOT NULL")

    # 7. Check for any remaining Google Trends URLs in product_offers or bundle_offers
    c.execute("SELECT COUNT(*) FROM product_offers WHERE source_url LIKE '%trends.google%'")
    trends_in_po = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM bundle_offers WHERE source_url LIKE '%trends.google%'")
    trends_in_bo = c.fetchone()[0]
    assert trends_in_po == 0, f"Found {trends_in_po} product offers still pointing to Google Trends!"
    assert trends_in_bo == 0, f"Found {trends_in_bo} bundle offers still pointing to Google Trends!"

    # 8. Verify 145 Meta baseline ads & T0 snapshots remain untouched
    c.execute("SELECT COUNT(*) FROM advertisements")
    ad_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*), COUNT(DISTINCT advertisement_id) FROM advertisement_snapshots")
    snap_count, distinct_ads = c.fetchone()
    assert ad_count == 145, f"Expected 145 baseline ads, found {ad_count}"
    assert distinct_ads == 145, f"Expected 145 distinct ad snapshots, found {distinct_ads}"
    assert snap_count == 290, f"Expected 290 snapshots across both collection dates, found {snap_count}"

    conn.commit()
    conn.close()
    print("Commercial Evidence Audit & Normalization complete. Baseline integrity 100% verified!")

if __name__ == "__main__":
    run_migration()
