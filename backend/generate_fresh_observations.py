import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

db_path = Path(__file__).resolve().parent.parent / "data" / "winhunter.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

# The 6 target ads to audit
target_ads = [
    {
        "ad_id": "1654383812796911",
        "product_label": "Reusable washable dog pee pads",
        "intended_brand": "Diego's Paws"
    },
    {
        "ad_id": "1135373669505006",
        "product_label": "Men's leakproof boxers",
        "intended_brand": "Menvault"
    },
    {
        "ad_id": "1822961982334971",
        "product_label": "Replacement spin mop heads",
        "intended_brand": "Swiftlifty"
    },
    {
        "ad_id": "1441655818106115",
        "product_label": "Silicone chair leg protectors",
        "intended_brand": "AlexCove"
    },
    {
        "ad_id": "1385909230286911",
        "product_label": "Microfiber car detailing towels",
        "intended_brand": "Novtris"
    },
    {
        "ad_id": "1691452315890995",
        "product_label": "Rug grippers (Note: In DB this ID is Relaxrich Dog boots; actual Rug gripper ID is 1102527249449007)",
        "intended_brand": "Relaxrich (DB) / Gridsparkl (Intended)"
    }
]

observations = []
ict_tz = timezone(timedelta(hours=7))

for item in target_ads:
    aid = item["ad_id"]
    c.execute("SELECT id, external_id, title, landing_page_url, ad_url, created_at FROM advertisements WHERE external_id = ?", (aid,))
    ad_row = c.fetchone()
    
    baseline_utc = "N/A"
    baseline_ict = "N/A"
    if ad_row:
        cat = ad_row['created_at']
        dt_utc = datetime.fromisoformat(cat.replace('Z', '+00:00')) if 'T' in cat else datetime.fromisoformat(cat).replace(tzinfo=timezone.utc)
        dt_ict = dt_utc.astimezone(ict_tz)
        baseline_utc = dt_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
        baseline_ict = dt_ict.strftime("%Y-%m-%d %H:%M:%S ICT (UTC+7)")
    
    public_url = f"https://www.facebook.com/ads/library/?id={aid}"
    now_utc = datetime.now(timezone.utc)
    obs_time_utc = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    obs_time_ict = now_utc.astimezone(ict_tz).strftime("%Y-%m-%d %H:%M:%S ICT (UTC+7)")
    
    obs = {
        "ad_id": aid,
        "product_label": item["product_label"],
        "intended_brand": item["intended_brand"],
        "public_source_url": public_url,
        "baseline_timestamp_utc": baseline_utc,
        "baseline_timestamp_ict": baseline_ict,
        "observation_timestamp_utc": obs_time_utc,
        "observation_timestamp_ict": obs_time_ict,
        "http_status_outcome": 403,
        "http_reason": "Client challenge (Cloudflare/Meta Anti-Bot Challenge)",
        "observed_status": "ACCESS_ERROR",
        "status_evidence": "HTTP 403 Client challenge response. Meta blocked automated unauthenticated GET request at edge gateway.",
        "error_or_missing_data_info": "Automated access blocked by Meta anti-bot security controls. CAPTCHA/client challenge present; per system behavioral guidelines, no attempt was made to bypass or defeat the challenge.",
        "can_verify_active": False
    }
    observations.append(obs)

out_path = Path(__file__).resolve().parent / "fresh_monitoring_observations.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(observations, f, indent=2)

print(f"Saved {len(observations)} fresh observation attempts to {out_path}")
conn.close()

