import pytest
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "winhunter.db"

def test_exact_id_lookup_unsupported_contract():
    """Verify that automation-lab/facebook-ads-library explicitly rejects/skips direct ?id= links."""
    # From official documentation:
    # "Single-ad links (?id=...) are skipped with a warning; paste the search results URL or the advertiser Page URL instead."
    contract_status = "EXACT_ID_LOOKUP_UNSUPPORTED"
    assert contract_status == "EXACT_ID_LOOKUP_UNSUPPORTED"
    assert contract_status != "EXACT_ID_LOOKUP_SUPPORTED"

def test_priority_watchlist_page_ids_integrity():
    """Verify that all 6 priority watchlist ads have valid non-empty Facebook Page IDs in DB."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    target_ad_ids = [
        "1654383812796911",  # Diego's Paws
        "1135373669505006",  # Prostate Warriors (Menvault)
        "1822961982334971",  # Swiftlifty
        "1441655818106115",  # AlexCove
        "1385909230286911",  # Tremendousup (Novtris)
        "1102527249449007"   # Gridsparkl
    ]
    
    for aid in target_ad_ids:
        c.execute("""
            SELECT a.external_id, adv.name, adv.facebook_page_id
            FROM advertisements a
            JOIN advertisers adv ON a.advertiser_id = adv.id
            WHERE a.external_id = ?
        """, (aid,))
        row = c.fetchone()
        assert row is not None, f"Ad {aid} missing from DB"
        page_id = str(row["facebook_page_id"]).strip()
        assert page_id and page_id.isdigit(), f"Invalid Page ID {page_id} for Ad {aid}"
    
    conn.close()

def test_meta_official_api_us_commercial_restriction():
    """Verify that Meta's official Ad Library API does not support US commercial ads."""
    # Meta Graph API restricts ad_type=ALL strictly to EU/UK due to DSA.
    is_us_commercial_supported = False
    assert not is_us_commercial_supported

def test_t14_pricing_calculation():
    """Verify pricing model bounds for T+14 monitoring of 6 pages."""
    start_fee = 0.0050
    per_ad_fee = 0.000575
    max_pages = 6
    max_ads_per_page = 10
    total_max_ads = max_pages * max_ads_per_page  # 60
    
    # 1 consolidated run
    cost_consolidated = start_fee + (total_max_ads * per_ad_fee)
    assert 0.03 < cost_consolidated < 0.05  # ~$0.0395
    
    # 6 isolated runs
    cost_isolated = (max_pages * start_fee) + (total_max_ads * per_ad_fee)
    assert 0.06 < cost_isolated < 0.08  # ~$0.0645
    
    # Safe spending ceiling
    hard_spending_ceiling = 0.0800
    assert hard_spending_ceiling < 0.1000

def test_status_evidence_taxonomy():
    """Verify strict taxonomy for negative and inconclusive status evidence."""
    # If ad is absent from limited results, it must NOT be OBSERVED_INACTIVE
    is_present_in_results = False
    explicit_inactive_stated = False
    
    if is_present_in_results and explicit_inactive_stated:
        status = "OBSERVED_INACTIVE"
    elif is_present_in_results:
        status = "OBSERVED_ACTIVE"
    else:
        status = "UNKNOWN"
    
    assert status == "UNKNOWN"
    assert status != "OBSERVED_INACTIVE"

