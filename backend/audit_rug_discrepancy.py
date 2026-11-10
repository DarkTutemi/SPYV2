import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

db_path = Path(__file__).resolve().parent.parent / "data" / "winhunter.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

ids_to_check = ["1691452315890995", "1102527249449007"]

print("================ DEEP AUDIT: 1691452315890995 vs 1102527249449007 ================")

for target_id in ids_to_check:
    print(f"\n>>> CHECKING AD ID: {target_id}")
    
    # 1. Check advertisements table
    c.execute("SELECT * FROM advertisements WHERE external_id = ?", (target_id,))
    ad = c.fetchone()
    if ad:
        ad_dict = dict(ad)
        adv_id = ad_dict.get("advertiser_id")
        
        # Check advertiser
        adv_info = {}
        if adv_id:
            c.execute("SELECT * FROM advertisers WHERE id = ?", (adv_id,))
            adv_row = c.fetchone()
            if adv_row:
                adv_info = dict(adv_row)
        
        # Parse raw_data
        raw = json.loads(ad_dict["raw_data"]) if ad_dict.get("raw_data") else {}
        
        print("  [advertisements table]:")
        print(f"    DB ID: {ad_dict.get('id')}")
        print(f"    Title: {ad_dict.get('title')}")
        print(f"    Body: {ad_dict.get('body')[:150] if ad_dict.get('body') else 'None'}...")
        print(f"    Landing URL: {ad_dict.get('landing_page_url')}")
        print(f"    Created At (UTC): {ad_dict.get('created_at')}")
        print(f"    First Seen At: {ad_dict.get('first_seen_at')}")
        print(f"    Advertiser Name: {adv_info.get('name')}")
        print(f"    Facebook Page ID: {adv_info.get('facebook_page_id')}")
        print(f"    Advertiser Domain: {adv_info.get('domain')}")
        print(f"    Raw Page ID: {raw.get('pageId')}")
        print(f"    Raw Page Name: {raw.get('pageName')}")
        print(f"    Raw Publisher Platforms: {raw.get('publisherPlatforms')}")
    else:
        print("  Not found in advertisements table!")

    # 2. Check source_records table
    c.execute("SELECT * FROM source_records WHERE external_id = ?", (target_id,))
    sources = [dict(r) for r in c.fetchall()]
    print(f"  [source_records table]: {len(sources)} records found")
    for s in sources:
        c_run_id = s.get("collection_run_id")
        # Check collection_run
        c.execute("SELECT * FROM collection_runs WHERE id = ?", (c_run_id,))
        run_info = c.fetchone()
        run_job = run_info["job_id"] if run_info else "N/A"
        run_created = run_info["created_at"] if run_info else "N/A"
        print(f"    Source ID: {s.get('id')} | Run ID: {c_run_id} (Job: {run_job}, Created: {run_created})")
        print(f"    Is Duplicate: {s.get('is_duplicate')} | Created At: {s.get('created_at')}")

    # 3. Check advertisement_snapshots table
    if ad:
        c.execute("SELECT * FROM advertisement_snapshots WHERE advertisement_id = ?", (ad["id"],))
        snaps = [dict(r) for r in c.fetchall()]
        print(f"  [advertisement_snapshots table]: {len(snaps)} snapshots found")
        for sn in snaps:
            print(f"    Snapshot Date: {sn.get('snapshot_date')} | Run ID: {sn.get('collection_run_id')} | Created At: {sn.get('created_at')}")

conn.close()

