"""
US WIN HUNTER — T+14 Longitudinal Monitoring Service

Enforces pre-flight contracts, financial spending caps, and operator authorization
for the scheduled T+14 monitoring check on November 24, 2026 (after 01:26 ICT).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Optional


ICT = timezone(timedelta(hours=7))

# Earliest permitted execution timestamp: November 24, 2026, 01:26:00 ICT
T14_EXECUTION_THRESHOLD_ICT = datetime(2026, 11, 24, 1, 26, 0, tzinfo=ICT)


@dataclass(frozen=True)
class TargetWatchlistAd:
    rank: int
    product_name: str
    target_ad_archive_id: str
    advertiser_name: str
    facebook_page_id: str
    store_domain: str
    baseline_observed_at_utc: str


# The 6 core watchlist targets established at baseline
WATCHLIST_TARGETS: list[TargetWatchlistAd] = [
    TargetWatchlistAd(
        rank=1,
        product_name="Reusable Washable Dog Pee Pads",
        target_ad_archive_id="1654383812796911",
        advertiser_name="Diego's Paws",
        facebook_page_id="1294258113779496",
        store_domain="diegospaws.com",
        baseline_observed_at_utc="2026-11-09T18:23:45+00:00",
    ),
    TargetWatchlistAd(
        rank=2,
        product_name="Men's Leakproof Incontinence Boxers",
        target_ad_archive_id="1135373669505006",
        advertiser_name="Prostate Warriors (Menvault)",
        facebook_page_id="122094798914008278",
        store_domain="menvault.com",
        baseline_observed_at_utc="2026-11-09T18:22:55+00:00",
    ),
    TargetWatchlistAd(
        rank=3,
        product_name="Replacement Spin Mop Heads",
        target_ad_archive_id="1822961982334971",
        advertiser_name="Swiftlifty",
        facebook_page_id="1427580890438766",
        store_domain="swiftlifty.com",
        baseline_observed_at_utc="2026-11-09T15:08:19+00:00",
    ),
    TargetWatchlistAd(
        rank=4,
        product_name="Silicone Chair Leg Protectors",
        target_ad_archive_id="1441655818106115",
        advertiser_name="AlexCove",
        facebook_page_id="1254199584442968",
        store_domain="alexcove.com",
        baseline_observed_at_utc="2026-11-09T18:24:22+00:00",
    ),
    TargetWatchlistAd(
        rank=5,
        product_name="Microfiber Car Detailing Towels",
        target_ad_archive_id="1385909230286911",
        advertiser_name="Tremendousup (Novtris)",
        facebook_page_id="889767694223771",
        store_domain="novtris.com",
        baseline_observed_at_utc="2026-11-09T18:23:27+00:00",
    ),
    TargetWatchlistAd(
        rank=6,
        product_name="Rubber Anti-Curling Rug Grippers",
        target_ad_archive_id="1102527249449007",
        advertiser_name="Gridsparkl/er",
        facebook_page_id="1238627265989998",
        store_domain="gridsparkl.com",
        baseline_observed_at_utc="2026-11-09T18:25:37+00:00",
    ),
]


class T14MonitoringService:
    """Manages pre-flight verification, input generation, cost capping, and result matching."""

    ACTOR_ID = "automation-lab/facebook-ads-library"
    PRICING_START_FEE_USD = 0.0050
    PRICING_PER_AD_FEE_USD = 0.000575  # FREE tier rate
    AUTHORIZED_SPENDING_CEILING_USD = 0.0800
    MAX_ADS_PER_PAGE = 20

    @classmethod
    def validate_page_inputs(cls) -> list[dict[str, str]]:
        """Validate that all 6 target Page IDs are non-empty numeric digits."""
        validated = []
        for target in WATCHLIST_TARGETS:
            pid = target.facebook_page_id.strip()
            if not pid or not pid.isdigit():
                raise ValueError(f"Invalid Facebook Page ID '{pid}' for {target.advertiser_name}")
            validated.append({
                "page_id": pid,
                "advertiser": target.advertiser_name,
                "target_ad_archive_id": target.target_ad_archive_id,
            })
        return validated

    @classmethod
    def calculate_expected_costs(cls) -> dict[str, Any]:
        """
        Calculate the exact worst-case and expected costs for 6 pages with max 20 ads per page.
        """
        page_count = len(WATCHLIST_TARGETS)
        max_ads = page_count * cls.MAX_ADS_PER_PAGE  # 120 ads
        ad_costs = max_ads * cls.PRICING_PER_AD_FEE_USD  # $0.06900
        total_worst_case = cls.PRICING_START_FEE_USD + ad_costs  # $0.07400

        return {
            "page_count": page_count,
            "max_ads_per_page": cls.MAX_ADS_PER_PAGE,
            "max_total_ads": max_ads,
            "start_fee_usd": cls.PRICING_START_FEE_USD,
            "per_ad_fee_usd": cls.PRICING_PER_AD_FEE_USD,
            "max_ad_charge_usd": round(ad_costs, 5),
            "total_expected_worst_case_usd": round(total_worst_case, 5),
            "authorized_ceiling_usd": cls.AUTHORIZED_SPENDING_CEILING_USD,
            "is_ceiling_adequate": total_worst_case <= cls.AUTHORIZED_SPENDING_CEILING_USD,
            "safety_margin_usd": round(cls.AUTHORIZED_SPENDING_CEILING_USD - total_worst_case, 5),
        }

    @classmethod
    def build_actor_input(cls) -> dict[str, Any]:
        """
        Build the canonical Apify actor input for the combined 1-run operation.
        Uses view_all_page_id URLs in pageUrls as documented and supported by the Actor.
        """
        page_urls = [
            f"https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=US&view_all_page_id={t.facebook_page_id}"
            for t in WATCHLIST_TARGETS
        ]

        return {
            "pageUrls": page_urls,
            "country": "US",
            "activeStatus": "all",
            "sortBy": "recent",
            "mediaType": "all",
            "maxAds": cls.MAX_ADS_PER_PAGE,
        }

    @classmethod
    def match_observation_results(
        cls,
        raw_ads: list[dict[str, Any]],
        run_id: str,
        observed_at: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """
        Match returned raw ads against the 6 target Ad Archive IDs with strict status classification:
        - OBSERVED_ACTIVE: Explicitly found with isActive=True
        - OBSERVED_INACTIVE: Explicitly found with isActive=False
        - UNKNOWN: Absent from the returned window
        """
        obs_dt = observed_at or datetime.now(timezone.utc)
        obs_iso = obs_dt.isoformat()

        # Build lookup table of returned ads by adArchiveId
        returned_map: dict[str, dict[str, Any]] = {}
        page_coverage: dict[str, int] = {t.facebook_page_id: 0 for t in WATCHLIST_TARGETS}

        for ad in raw_ads:
            arch_id = str(ad.get("adArchiveId") or ad.get("id") or "").strip()
            if arch_id:
                returned_map[arch_id] = ad

            # Track page coverage
            pid = str(ad.get("pageId") or "").strip()
            if pid in page_coverage:
                page_coverage[pid] += 1

        matches: list[dict[str, Any]] = []
        status_summary = {"OBSERVED_ACTIVE": 0, "OBSERVED_INACTIVE": 0, "UNKNOWN": 0}

        for target in WATCHLIST_TARGETS:
            tid = target.target_ad_archive_id
            if tid in returned_map:
                ad_data = returned_map[tid]
                is_active = ad_data.get("isActive")
                if is_active is True:
                    status = "OBSERVED_ACTIVE"
                    evidence = "Ad explicitly returned with isActive=true"
                elif is_active is False:
                    status = "OBSERVED_INACTIVE"
                    evidence = f"Ad explicitly returned with isActive=false, endDate={ad_data.get('endDate')}"
                else:
                    status = "UNKNOWN"
                    evidence = f"Ad returned but isActive field is inconclusive: {is_active}"
            else:
                status = "UNKNOWN"
                ads_for_page = page_coverage.get(target.facebook_page_id, 0)
                evidence = (
                    f"Target ad absent from retrieved batch ({ads_for_page} ads returned for Page). "
                    f"Inconclusive: May be truncated by maxAds={cls.MAX_ADS_PER_PAGE} or pagination order."
                )

            status_summary[status] = status_summary.get(status, 0) + 1

            matches.append({
                "rank": target.rank,
                "product_name": target.product_name,
                "advertiser_name": target.advertiser_name,
                "facebook_page_id": target.facebook_page_id,
                "target_ad_archive_id": tid,
                "observed_status": status,
                "status_evidence": evidence,
                "observation_timestamp_utc": obs_iso,
                "apify_run_id": run_id,
                "page_ads_retrieved": page_coverage.get(target.facebook_page_id, 0),
            })

        return {
            "observation_timestamp_utc": obs_iso,
            "apify_run_id": run_id,
            "total_ads_retrieved": len(raw_ads),
            "page_coverage": page_coverage,
            "status_summary": status_summary,
            "matches": matches,
            "accuracy_disclaimer": "Monitoring accuracy is limited to the top 20 recent ads per page. Absence does NOT prove ad cessation.",
        }

    @classmethod
    def check_execution_eligibility(
        cls,
        current_time: Optional[datetime] = None,
        operator_authorized: bool = False,
    ) -> tuple[bool, str]:
        """
        Check if execution is permitted based on date threshold and explicit operator approval.
        """
        now = current_time or datetime.now(timezone.utc)
        now_ict = now.astimezone(ICT)

        if now_ict < T14_EXECUTION_THRESHOLD_ICT:
            time_remaining = T14_EXECUTION_THRESHOLD_ICT - now_ict
            return False, f"BLOCKED: Execution time threshold (2026-11-24 01:26:00 ICT) not reached. Remaining: {time_remaining}."

        if not operator_authorized:
            return False, "BLOCKED: Operator authorization not granted. Explicit approval required."

        return True, "READY: Eligible for execution with operator authorization."

