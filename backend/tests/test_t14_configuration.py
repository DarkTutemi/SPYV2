import pytest
from datetime import datetime, timezone, timedelta
from app.services.t14_monitoring import T14MonitoringService, WATCHLIST_TARGETS, ICT


def test_watchlist_targets_integrity():
    """Verify that all 6 watchlist targets have genuine ad IDs, page IDs, and names."""
    assert len(WATCHLIST_TARGETS) == 6
    page_ids = set()
    ad_ids = set()
    for t in WATCHLIST_TARGETS:
        assert t.target_ad_archive_id and t.target_ad_archive_id.isdigit()
        assert t.facebook_page_id and t.facebook_page_id.isdigit()
        assert t.advertiser_name
        assert t.store_domain
        page_ids.add(t.facebook_page_id)
        ad_ids.add(t.target_ad_archive_id)

    assert len(page_ids) == 6, "All 6 Facebook Page IDs must be distinct"
    assert len(ad_ids) == 6, "All 6 Target Ad Archive IDs must be distinct"


def test_page_inputs_validation():
    """Verify that validate_page_inputs successfully checks all 6 targets."""
    validated = T14MonitoringService.validate_page_inputs()
    assert len(validated) == 6
    for item in validated:
        assert item["page_id"].isdigit()


def test_pricing_calculation_and_ceiling():
    """Verify mathematical calculation of pricing and that ceiling is adequate."""
    calc = T14MonitoringService.calculate_expected_costs()
    assert calc["page_count"] == 6
    assert calc["max_total_ads"] == 120
    assert calc["start_fee_usd"] == 0.0050
    assert calc["per_ad_fee_usd"] == 0.000575
    assert calc["max_ad_charge_usd"] == 0.06900
    assert calc["total_expected_worst_case_usd"] == 0.07400
    assert calc["authorized_ceiling_usd"] == 0.0800
    assert calc["is_ceiling_adequate"] is True
    assert calc["safety_margin_usd"] == 0.00600


def test_actor_input_payload_structure():
    """Verify that the generated payload conforms exactly to Actor input specifications."""
    payload = T14MonitoringService.build_actor_input()
    assert "pageUrls" in payload
    assert len(payload["pageUrls"]) == 6
    assert payload["country"] == "US"
    assert payload["activeStatus"] == "all"
    assert payload["sortBy"] == "recent"
    assert payload["mediaType"] == "all"
    assert payload["maxAds"] == 20

    for url in payload["pageUrls"]:
        assert "facebook.com/ads/library" in url
        assert "view_all_page_id=" in url
        assert "active_status=all" in url


def test_match_observation_results_strict_taxonomy():
    """Verify that returned ads are matched strictly without substituting new ads."""
    mock_raw_ads = [
        # Target #1 Diego's Paws: ACTIVE
        {
            "adArchiveId": "1654383812796911",
            "pageId": "1294258113779496",
            "isActive": True,
            "title": "Diego Pee Pad Active",
        },
        # Target #3 Swiftlifty: INACTIVE
        {
            "adArchiveId": "1822961982334971",
            "pageId": "1427580890438766",
            "isActive": False,
            "endDate": "2026-11-20T00:00:00Z",
            "title": "Swiftlifty Spin Mop Inactive",
        },
        # A completely new ad from AlexCove (not target #4)
        {
            "adArchiveId": "9999999999999999",
            "pageId": "1254199584442968",
            "isActive": True,
            "title": "Brand New AlexCove Ad",
        },
    ]

    results = T14MonitoringService.match_observation_results(
        raw_ads=mock_raw_ads,
        run_id="mock_run_12345",
        observed_at=datetime(2026, 11, 24, 2, 0, 0, tzinfo=timezone.utc),
    )

    matches = {m["target_ad_archive_id"]: m for m in results["matches"]}

    # Target 1: OBSERVED_ACTIVE
    assert matches["1654383812796911"]["observed_status"] == "OBSERVED_ACTIVE"
    # Target 3: OBSERVED_INACTIVE
    assert matches["1822961982334971"]["observed_status"] == "OBSERVED_INACTIVE"
    # Target 4: UNKNOWN (even though AlexCove had a new ad in the batch)
    assert matches["1441655818106115"]["observed_status"] == "UNKNOWN"
    assert "absent" in matches["1441655818106115"]["status_evidence"].lower()

    # Remaining targets: UNKNOWN
    assert matches["1135373669505006"]["observed_status"] == "UNKNOWN"
    assert matches["1385909230286911"]["observed_status"] == "UNKNOWN"
    assert matches["1102527249449007"]["observed_status"] == "UNKNOWN"


def test_execution_eligibility_checks():
    """Verify that execution is blocked before date threshold and without operator authorization."""
    # Case 1: Before threshold (e.g. today Nov 10, 2026)
    today = datetime(2026, 11, 10, 18, 50, 0, tzinfo=ICT)
    eligible, msg = T14MonitoringService.check_execution_eligibility(current_time=today, operator_authorized=False)
    assert eligible is False
    assert "not reached" in msg

    # Case 2: On threshold date, but without operator authorization
    t14_time = datetime(2026, 11, 24, 2, 0, 0, tzinfo=ICT)
    eligible, msg = T14MonitoringService.check_execution_eligibility(current_time=t14_time, operator_authorized=False)
    assert eligible is False
    assert "Operator authorization not granted" in msg

    # Case 3: On threshold date with operator authorization
    eligible, msg = T14MonitoringService.check_execution_eligibility(current_time=t14_time, operator_authorized=True)
    assert eligible is True
    assert "READY" in msg

