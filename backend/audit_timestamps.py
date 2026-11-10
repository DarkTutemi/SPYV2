import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

db_path = Path(__file__).resolve().parent.parent / "data" / "winhunter.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.execute("SELECT id, collection_run_id, external_id, created_at FROM source_records WHERE is_synthetic = 0")
records = [dict(r) for r in c.fetchall()]

ict_tz = timezone(timedelta(hours=7))

p7_run_id = "0046dfa9-cc96-4b1c-aa7d-213a5de2c9ae"

p7_times = []
p10_times = []

for r in records:
    cat = r['created_at']
    dt_utc = datetime.fromisoformat(cat.replace('Z', '+00:00')) if 'T' in cat else datetime.fromisoformat(cat).replace(tzinfo=timezone.utc)
    dt_ict = dt_utc.astimezone(ict_tz)
    
    if r['collection_run_id'] == p7_run_id:
        p7_times.append((dt_utc, dt_ict))
    else:
        p10_times.append((dt_utc, dt_ict))

print("=== PHASE 7 SOURCE RECORDS TIMESTAMPS ===")
p7_utc_min = min(t[0] for t in p7_times)
p7_utc_max = max(t[0] for t in p7_times)
p7_ict_min = min(t[1] for t in p7_times)
p7_ict_max = max(t[1] for t in p7_times)
print(f"Phase 7 ({len(p7_times)} records):")
print(f"  UTC:   {p7_utc_min.strftime('%Y-%m-%d %H:%M:%S %Z')} to {p7_utc_max.strftime('%Y-%m-%d %H:%M:%S %Z')}")
print(f"  ICT:   {p7_ict_min.strftime('%Y-%m-%d %H:%M:%S %Z')} to {p7_ict_max.strftime('%Y-%m-%d %H:%M:%S %Z')}")

print("\n=== PHASE 10 SOURCE RECORDS TIMESTAMPS ===")
p10_utc_min = min(t[0] for t in p10_times)
p10_utc_max = max(t[0] for t in p10_times)
p10_ict_min = min(t[1] for t in p10_times)
p10_ict_max = max(t[1] for t in p10_times)
print(f"Phase 10 ({len(p10_times)} records):")
print(f"  UTC:   {p10_utc_min.strftime('%Y-%m-%d %H:%M:%S %Z')} to {p10_utc_max.strftime('%Y-%m-%d %H:%M:%S %Z')}")
print(f"  ICT:   {p10_ict_min.strftime('%Y-%m-%d %H:%M:%S %Z')} to {p10_ict_max.strftime('%Y-%m-%d %H:%M:%S %Z')}")

print("\n=== DATE ALLOCATION COMPARISON ===")
print("In UTC:")
print(f"  Phase 7: Baseline date = {p7_utc_min.strftime('%Y-%m-%d')} UTC -> T+14 = {(p7_utc_min + timedelta(days=14)).strftime('%Y-%m-%d')} UTC, T+30 = {(p7_utc_min + timedelta(days=30)).strftime('%Y-%m-%d')} UTC")
print(f"  Phase 10: Baseline date = {p10_utc_min.strftime('%Y-%m-%d')} UTC -> T+14 = {(p10_utc_min + timedelta(days=14)).strftime('%Y-%m-%d')} UTC, T+30 = {(p10_utc_min + timedelta(days=30)).strftime('%Y-%m-%d')} UTC")

print("In Local Time (ICT / UTC+7):")
print(f"  Phase 7 (20 ads): Baseline date = {p7_ict_min.strftime('%Y-%m-%d')} ICT (November 9) -> T+14 = {(p7_ict_min + timedelta(days=14)).strftime('%Y-%m-%d')} ICT (November 23), T+30 = {(p7_ict_min + timedelta(days=30)).strftime('%Y-%m-%d')} ICT (December 9)")
print(f"  Phase 10 (125 ads): Baseline date = {p10_ict_min.strftime('%Y-%m-%d')} ICT (November 10!) -> T+14 = {(p10_ict_min + timedelta(days=14)).strftime('%Y-%m-%d')} ICT (November 24!), T+30 = {(p10_ict_min + timedelta(days=30)).strftime('%Y-%m-%d')} ICT (December 10!)")

conn.close()

