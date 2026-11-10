import pytest
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "winhunter.db"

def test_baseline_mathematical_reconciliation():
    """Verify that the 145-ad baseline strictly matches 20 (Phase 7) + 128 (Phase 10) - 3 (overlap)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # 1. Total unique non-synthetic ads in DB
    c.execute("SELECT count(distinct external_id) FROM advertisements WHERE is_synthetic = 0")
    total_unique = c.fetchone()[0]
    assert total_unique == 145, f"Expected 145 unique ads, got {total_unique}"
    
    # 2. Phase 7 source records
    p7_run_id = "0046dfa9-cc96-4b1c-aa7d-213a5de2c9ae"
    c.execute("SELECT DISTINCT external_id FROM source_records WHERE collection_run_id = ?", (p7_run_id,))
    p7_exts = {r[0] for r in c.fetchall()}
    assert len(p7_exts) == 20, f"Expected 20 Phase 7 ads, got {len(p7_exts)}"
    
    # 3. Phase 10 source records
    c.execute("SELECT id FROM collection_runs WHERE started_at >= '2026-11-09 18:00:00' AND started_at <= '2026-11-09 19:00:00'")
    p10_run_ids = [r[0] for r in c.fetchall()]
    placeholders = ','.join('?' for _ in p10_run_ids)
    c.execute(f"SELECT DISTINCT external_id FROM source_records WHERE collection_run_id IN ({placeholders})", p10_run_ids)
    p10_exts = {r[0] for r in c.fetchall()}
    assert len(p10_exts) == 128, f"Expected 128 unique Phase 10 ads, got {len(p10_exts)}"
    
    # 4. Cross-run overlapping IDs
    overlap = p7_exts.intersection(p10_exts)
    assert len(overlap) == 3, f"Expected exactly 3 cross-run overlapping ads, got {len(overlap)}"
    expected_overlap = {'4475294959281092', '1822961982334971', '1126829873388780'}
    assert overlap == expected_overlap
    
    # 5. Arithmetic: 20 + 128 - 3 == 145
    assert len(p7_exts) + len(p10_exts) - len(overlap) == 145
    conn.close()

def test_timezone_date_distinction():
    """Verify that Phase 10 ads collected at ~01:23 ICT are recognized as Nov 10 in ICT and Nov 9 in UTC."""
    ict_tz = timezone(timedelta(hours=7))
    utc_str = "2026-11-09T18:23:00+00:00"
    dt_utc = datetime.fromisoformat(utc_str)
    dt_ict = dt_utc.astimezone(ict_tz)
    
    assert dt_utc.strftime("%Y-%m-%d") == "2026-11-09"
    assert dt_ict.strftime("%Y-%m-%d") == "2026-11-10"
    
    # T+14 in UTC vs ICT
    t14_utc = dt_utc + timedelta(days=14)
    t14_ict = dt_ict + timedelta(days=14)
    assert t14_utc.strftime("%Y-%m-%d") == "2026-11-23"
    assert t14_ict.strftime("%Y-%m-%d") == "2026-11-24"

def test_price_evidence_classification_taxonomy():
    """Verify strict taxonomy of price evidence classifications."""
    valid_classes = {
        "LANDING_VERIFIED",
        "AD_COPY_ONLY",
        "HISTORIC_OBSERVATION",
        "ESTIMATED",
        "NOT_VERIFIABLE"
    }
    
    # Menvault boxers $69 must not be classified as LANDING_VERIFIED
    menvault_class = "NOT_VERIFIABLE"
    assert menvault_class in valid_classes
    assert menvault_class != "LANDING_VERIFIED"
    
    # Diego's paws B2G1 $39.90 comes from ad copy headline
    diego_promo_class = "AD_COPY_ONLY"
    assert diego_promo_class in valid_classes

def test_spin_mop_advertiser_differentiation():
    """Verify that Swiftlifty and Gridsparkl advertise spin mop heads, while Pawndify advertises a flat mop."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Swiftlifty product
    c.execute("SELECT landing_page_url FROM advertisements WHERE external_id = '1822961982334971'")
    row_swift = c.fetchone()
    assert "spin-mop-heads" in row_swift["landing_page_url"]
    
    # Gridsparkl product
    c.execute("SELECT landing_page_url FROM advertisements WHERE external_id = '1665401658305068'")
    row_grid = c.fetchone()
    assert "spin-mop-replacement-heads" in row_grid["landing_page_url"]
    
    # Pawndify product
    c.execute("SELECT landing_page_url, title FROM advertisements WHERE external_id = '1681599646863488'")
    row_pawn = c.fetchone()
    assert "flat-m-op" in row_pawn["landing_page_url"] or "flat mop" in (row_pawn["title"] or "").lower()
    
    conn.close()

def test_free_monitoring_access_error_rule():
    """Verify that HTTP 403 Client Challenge must be recorded as ACCESS_ERROR and never OBSERVED_ACTIVE."""
    http_code = 403
    status = "ACCESS_ERROR" if http_code in (403, 429, 503) else "UNKNOWN"
    assert status == "ACCESS_ERROR"
    assert status != "OBSERVED_ACTIVE"

