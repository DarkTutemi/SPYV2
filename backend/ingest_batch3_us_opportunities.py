"""
US WIN HUNTER — Reproducible Batch 3 Commercial Validation & Opportunity Ingestion

Ingests the three Batch 3 US dropshipping candidates backed by verified public
captures in docs/run_reports/sanitized_acquisition_manifest.json while strictly
separating:
  1. Observed competitor retail price (and corded vs cordless category benchmarks)
  2. Proposed selling price (unverified strategy target)
  3. Actual verified price for an equivalent sourcing product (when observed)
  4. Supplier FOB quote (UNKNOWN unless confirmed quote exists)
  5. Landed US cost (UNKNOWN)
  6. Customer AOV (UNKNOWN)

Never presents a competitor's retail price or corded category benchmark as the
generic candidate's own observed price, and preserves $0.00 Apify spend & 0
invented demand metrics.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.engines.scoring import ScoringEngine  # noqa: E402
from app.models.models import (  # noqa: E402
    CollectionJob,
    CollectionRun,
    ConfidenceLevel,
    DataSource,
    DataSourceType,
    EvidenceType,
    OpportunityScore,
    PriceEvidenceType,
    Product,
    ProductOffer,
    SourceRecord,
)
from app.services.evidence_verification import (  # noqa: E402
    EvidenceVerificationOutcome,
    generate_capture_signature,
    inspect_artifact_content,
    verify_commercial_evidence_db,
)
from ingest_batch2_dtc_evidence import (  # noqa: E402
    DATA_SOURCE_ID,
    MANIFEST_PATH,
    snapshot_counts,
)

DEFAULT_DB_PATH = REPO_ROOT / "data" / "winhunter.db"
BATCH3_KEY = "2026-11-12_us_dropship_opportunities_batch3"
BATCH3_V2_KEY = "2026-11-12_us_dropship_opportunities_batch3_v2"
BATCH3_KEYS = (BATCH3_KEY, BATCH3_V2_KEY)
COLLECTION_JOB_ID = "job_us_opportunities_batch3_20261112"
COLLECTION_RUN_ID = "run_us_opportunities_batch3_20261112"

# Map (manufacturer, product_identity) -> stable SourceRecord ID across Batch 3 + Batch 3 v2 addendum
SOURCE_RECORD_MAP: Dict[tuple[str, str], str] = {
    # Batch 3 initial captures
    ("ruffrover_dtc", "48906329850134"): "srec_b3_ruffrover_20261112",
    ("doglemi_oem", "Pet-Car-Seat-Cover"): "srec_b3_doglemi_supplier_20261112",
    ("aquasana_dtc", "100236241"): "srec_b3_aquasana_hero_20261112",
    ("aquasana_dtc", "100236244"): "srec_b3_aquasana_refill_20261112",
    ("ningboware_oem", "ZH2087T"): "srec_b3_ningboware_supplier_20261112",
    ("xpower_dtc", "A-2"): "srec_b3_xpower_a2_20261112",
    ("honkcare_oem", "HONK_JETFAN"): "srec_b3_honkcare_supplier_20261112",
    # Batch 3 deep commercial validation addendum (batch3_v2)
    ("doglemi_oem", "PD50128"): "srec_b3v2_doglemi_pd50128_20261112",
    ("doglemi_alibaba", "1601611347051"): "srec_b3v2_alibaba_pd50128l_20261112",
    ("zhonghe_oem_detail", "ZH2087T"): "srec_b3v2_zhonghe_zh2087t_20261112",
    ("zhonghe_cartridge", "activated-carbon-filter"): "srec_b3v2_zhonghe_cartridge_20261112",
    ("aquabliss_dtc", "AB-US-SF100-GDB"): "srec_b3v2_aquabliss_sf100_20261112",
    ("weddell_dtc", "weddell-duo-shower-filter"): "srec_b3v2_weddell_duo_20261112",
    ("honkcare_dtc", "29347"): "srec_b3v2_honkcare_jetfan_29347_20261112",
    ("honkcare_dtc", "29334"): "srec_b3v2_honkcare_turbo_29334_20261112",
    ("fanttik_dtc", "fanttik-b10-pro"): "srec_b3v2_fanttik_b10pro_20261112",
}

OPPORTUNITIES: List[Dict[str, Any]] = [
    {
        "external_id": "48906329850134",
        "primary_url": "https://ruffrover.com/",
        "supplier_key": ("doglemi_oem", "PD50128"),
        "candidate_min_price_usd": None,
        "candidate_max_price_usd": None,
        "name": "Hard-Bottom Waterproof Dog Car Seat Extender",
        "normalized_name": "hard-bottom waterproof dog car seat extender",
        "category": "Pet Travel & Automotive",
        "commercial_model": "MODEL_A_SINGLE_PRODUCT",
        "functional_use_case": (
            "Rigid folding hard-bottom backseat extender and waterproof Oxford protector bridging "
            "the rear footwell gap so medium/large dogs travel without sliding or scratching leather."
        ),
        "customer_pain": (
            "Dogs slump into the rear footwell on sudden stops, soil/scratch upholstery, and snap "
            "thin cloth hammocks; DTC rivals sell at $159.95 USD with heavy boxed shipping constraints."
        ),
        "offers": [
            {
                "offer_id": "off_b3_ruffrover_extender_20261112",
                "manifest_key": ("ruffrover_dtc", "48906329850134"),
                "price_evidence_type": PriceEvidenceType.DTC_MANUFACTURER_OBSERVED_PRICE,
                "evidence_type": EvidenceType.DTC_MANUFACTURER_OBSERVED_PRICE,
                "offer_role": "competitor_retail_benchmark",
                "price_semantic": "OBSERVED_COMPETITOR_RETAIL_PRICE",
                "is_competitor_benchmark": True,
                "notes": (
                    "Observed competitor retail benchmark only (Ruff Rover 2.0 at $159.95 USD); "
                    "NOT a verified offer or price for the generic Doglemi PD50128 candidate."
                ),
            }
        ],
        "commercial_notes": {
            "observed_competitor_retail_prices": [
                "RuffRover 2.0 (https://ruffrover.com/): $159.95 USD In Stock (captured Shopify JSON-LD)",
                "Dog-Go (https://dog-go.co/): AUD $199.00 listed in AUD storefront currency (~$130-$140 USD eq., uncaptured checkout USD)",
                "FunnyFuzzy / URPOWER: cited via web search ($99-$135.99 USD DTC / $34-$55 USD Amazon) — direct pages rate-limited or not captured",
            ],
            "proposed_selling_price_usd": "$79.99-$99.99 USD strategic target ONLY (requires 3PL margin modeling; 1-pc air shipping unviable)",
            "equivalent_sourcing_verified_retail_price_usd": None,
            "supplier_model_match": "Guangzhou Dolemi Pet Products Co., Ltd. Model PD50128 (unfolded 138x162.5 cm, polyester) / Alibaba sibling PD50128-L (78x48x14 cm carton, 3.58 kg gross weight)",
            "supplier_wholesale_reference_listing": "Alibaba ID 1601611347051 (DogLemi Pet Products Limited HK): MOQ 50-1,999 pcs (VND 610,070 IP locale ref) / >=2,000 pcs (VND 572,056), 35-day lead time; reference listing only, NOT confirmed FOB or landed US COGS",
            "supplier_fob_quote_usd": "UNKNOWN_RFQ_REQUIRED (MOQ 50+ units; no 1-piece dropship pricing)",
            "landed_us_cost_usd": "UNKNOWN (3.58 kg gross / ~12.4 kg volumetric 78x48x14 cm parcel makes single-unit China air dropship margin-destructive)",
            "customer_aov_usd": "UNKNOWN",
            "demand_evidence_status": "UNKNOWN_DEMAND_EVIDENCE (0 captured local Meta DB ads; Meta Ad Library automated HTTP 403; active Shopify/TikTok presence noted via search without spend/impression data)",
            "shipping_and_return_risk": "HIGH_VOLUMETRIC_WEIGHT (3.58 kg physical / 78x48x14 cm package; air parcel shipping & US returns unsustainable without US 3PL stocking + 50-unit factory MOQ)",
            "commercial_decision": "REJECT_FOR_PURE_1PC_DROPSHIPPING_UNLESS_3PL_FOB_QUOTED",
        },
    },
    {
        "external_id": "100236241",
        "primary_url": "https://www.aquasana.com/shower-head-water-filters/chrome-shower-wand-100236241.html",
        "supplier_key": ("zhonghe_oem_detail", "ZH2087T"),
        "candidate_min_price_usd": None,
        "candidate_max_price_usd": None,
        "name": "Multi-Stage High-Pressure Filtered Showerhead (+ Quarterly Refill System)",
        "normalized_name": "multi-stage high-pressure filtered showerhead quarterly refill system",
        "category": "Bath & Home Wellness",
        "commercial_model": "MODEL_B_NATURAL_MULTI_UNIT",
        "functional_use_case": (
            "High-pressure handheld filtered showerhead with replaceable internal handle-chamber "
            "cartridge (PP cotton / mineral beads / activated carbon) targeting chlorine odor & dryness."
        ),
        "customer_pain": (
            "Hard-water skin/hair dryness, chlorine smell, weak apartment shower pressure, and "
            "competing ABS filters cracking/leaking at swivel joints or lacking genuine replacement refills."
        ),
        "offers": [
            {
                "offer_id": "off_b3_aquasana_shower_20261112",
                "manifest_key": ("aquasana_dtc", "100236241"),
                "price_evidence_type": PriceEvidenceType.OEM_LIST_PRICE,
                "evidence_type": EvidenceType.OEM_LIST_PRICE,
                "offer_role": "competitor_retail_benchmark",
                "price_semantic": "OBSERVED_COMPETITOR_RETAIL_PRICE",
                "is_competitor_benchmark": True,
                "notes": (
                    "Observed competitor retail benchmark only (Aquasana 100236241 at $99.99 USD); "
                    "NOT an offer or price for ZHONGHE ZH2087T, and Aquasana cartridges do NOT fit ZH2087T."
                ),
            },
            {
                "offer_id": "off_b3_aquabliss_sf100_20261112",
                "manifest_key": ("aquabliss_dtc", "AB-US-SF100-GDB"),
                "price_evidence_type": PriceEvidenceType.DTC_MANUFACTURER_OBSERVED_PRICE,
                "evidence_type": EvidenceType.DTC_MANUFACTURER_OBSERVED_PRICE,
                "offer_role": "competitor_retail_benchmark",
                "price_semantic": "OBSERVED_COMPETITOR_RETAIL_PRICE",
                "is_competitor_benchmark": True,
                "notes": "Independent 2nd US DTC competitor benchmark (AquaBliss SF100 AB-US-SF100-GDB $64.99 USD In Stock).",
            },
            {
                "offer_id": "off_b3_weddell_duo_20261112",
                "manifest_key": ("weddell_dtc", "weddell-duo-shower-filter"),
                "price_evidence_type": PriceEvidenceType.DTC_MANUFACTURER_OBSERVED_PRICE,
                "evidence_type": EvidenceType.DTC_MANUFACTURER_OBSERVED_PRICE,
                "offer_role": "competitor_retail_benchmark",
                "price_semantic": "OBSERVED_COMPETITOR_RETAIL_PRICE",
                "is_competitor_benchmark": True,
                "notes": "Independent 3rd US DTC competitor benchmark (Weddell Duo Shower Filter $79.99 USD; twin refills $24.99).",
            },
        ],
        "commercial_notes": {
            "observed_competitor_retail_prices": [
                "Aquasana 100236241 (https://www.aquasana.com/...): $99.99 USD In Stock (refill 100236244 $62.99 USD — NOT compatible with ZH2087T)",
                "AquaBliss SF100 (https://aquabliss.com/): $64.99 USD In Stock (SKU AB-US-SF100-GDB, captured JSON-LD)",
                "Weddell Duo (https://weddellwater.com/): $79.99-$89.99 USD hardware / $24.99-$29.99 USD twin replacement cartridges (captured)",
            ],
            "proposed_selling_price_usd": "$49.99-$64.99 USD Hero + $24.99-$29.99 USD 2-pack cartridge target ONLY (NOT observed price)",
            "equivalent_sourcing_verified_retail_price_usd": None,
            "supplier_model_match": "Cixi Zhonghe Sanitary Ware Factory (ZHONGHE / ningboware.com) Model ZH2087T transparent light-blue handheld filter showerhead + proprietary handle-chamber cartridge catalog (activated-carbon-filter, mineral-stone-beads-filter, pp-filter)",
            "cartridge_compatibility_warning": "Aquasana 100236244 cartridges are NOT interchangeable with ZH2087T; must source exact inner-handle-diameter cartridges matched to ZH2087T from ZHONGHE.",
            "supplier_fob_quote_usd": "UNKNOWN_RFQ_REQUIRED (MOQ 500-2,000 units: 500 standard catalog, 1,000 logo/color, 2,000 custom packaging; NO 1-piece fulfillment on ningboware.com)",
            "landed_us_cost_usd": "UNKNOWN",
            "customer_aov_usd": "UNKNOWN",
            "demand_evidence_status": "UNKNOWN_DEMAND_EVIDENCE (0 captured local Meta DB ads; Meta Ad Library automated HTTP 403; multiple active US DTC competitors Aquasana/AquaBliss/Weddell/Hello Klean/Jolie verified online)",
            "shipping_and_return_risk": "CARTRIDGE_LOCKIN_AND_HIGH_MOQ_500_2000 (low 0.5-0.8 kg parcel weight without batteries, but requires 500-unit MOQ + NSF-177/chlorine testing validation & washer/leak QC)",
            "commercial_decision": "RESEARCH_MORE_PENDING_FOB_MOQ_AND_NSF_MEDIA_VERIFY",
        },
    },
    {
        "external_id": "A-2",
        "primary_url": "https://xpower.com/shop/a-2-airrow-pro-multipurpose-powered-air-duster/",
        "supplier_key": ("honkcare_dtc", "29347"),
        "candidate_min_price_usd": 51.99,
        "candidate_max_price_usd": 51.99,
        "name": "Brushless High-Speed Electric Air Duster (Canned Air Replacement)",
        "normalized_name": "brushless high-speed electric air duster canned air replacement",
        "category": "Home Tech & Auto Detailing",
        "commercial_model": "MODEL_A_SINGLE_PRODUCT",
        "functional_use_case": (
            "Cordless rechargeable brushless high-speed jet-fan air duster (110k-130k RPM class) "
            "replacing disposable aerosol cans for keyboards, PCs, cameras, and auto interiors."
        ),
        "customer_pain": (
            "Expensive freezing canned air (UN1950 aerosol) runs out mid-clean; corded workshop "
            "blowers (e.g. XPOWER A-2 10-ft cord) restrict portable car/desk mobility."
        ),
        "offers": [
            {
                "offer_id": "off_b3_honkcare_jetfan_20261112",
                "manifest_key": ("honkcare_dtc", "29347"),
                "price_evidence_type": PriceEvidenceType.OEM_LIST_PRICE,
                "evidence_type": EvidenceType.OEM_LIST_PRICE,
                "offer_role": "equivalent_sourcing_retail_listing",
                "price_semantic": "EQUIVALENT_SOURCING_RETAIL_LISTING",
                "is_competitor_benchmark": False,
                "notes": (
                    "Verified equivalent OEM-direct 1-unit listing from manufacturer storefront Shenzhen Honk Electronic "
                    "(HonkCare Jet Fan 29347, 7,500mAh, 130k RPM, $51.99 USD In Stock, 7-13d US shipping); "
                    "distinct from factory B2B FOB quote and landed US cost."
                ),
            },
            {
                "offer_id": "off_b3_fanttik_b10_pro_20261112",
                "manifest_key": ("fanttik_dtc", "fanttik-b10-pro"),
                "price_evidence_type": PriceEvidenceType.DTC_MANUFACTURER_OBSERVED_PRICE,
                "evidence_type": EvidenceType.DTC_MANUFACTURER_OBSERVED_PRICE,
                "offer_role": "competitor_retail_benchmark",
                "price_semantic": "OBSERVED_COMPETITOR_RETAIL_PRICE",
                "is_competitor_benchmark": True,
                "notes": (
                    "Observed cordless US DTC competitor benchmark (Fanttik B10 Pro at $49.99 USD sale / $89.99 original; "
                    "17.76 Wh / 110,000 RPM)."
                ),
            },
            {
                "offer_id": "off_b3_xpower_duster_20261112",
                "manifest_key": ("xpower_dtc", "A-2"),
                "price_evidence_type": PriceEvidenceType.OEM_LIST_PRICE,
                "evidence_type": EvidenceType.OEM_LIST_PRICE,
                "offer_role": "category_benchmark_corded",
                "price_semantic": "CATEGORY_BENCHMARK_CORDED",
                "is_competitor_benchmark": True,
                "notes": (
                    "Strictly reclassified as CORDED category benchmark ONLY: XPOWER A-2 Airrow Pro ($65.00 USD In Stock) "
                    "is 120V/60Hz 500W with a 10-ft power cord (NOT cordless)."
                ),
            },
        ],
        "commercial_notes": {
            "observed_competitor_retail_prices": [
                "Fanttik B10 Pro (https://fanttik.com/): $49.99 USD sale / $89.99 regular (cordless, 17.76 Wh / 110k RPM, captured)",
                "Wolfbox MF100/MF200 (https://wolfbox.com/): $55-$89.99 USD cordless range via search & product JSON (MF100 22.2 Wh / 150k RPM; single-item URL HTTP 429 on bulk scrape)",
                "XPOWER A-2 Airrow Pro (https://xpower.com/...): $65.00 USD In Stock [RECLASSIFIED: 120V/500W/10-ft CORDED category benchmark ONLY, NOT cordless competitor]",
            ],
            "proposed_selling_price_usd": "$54.99-$69.99 USD differentiated kit target (pressured if direct OEM storefront sells similar unit at $37.99-$51.99!)",
            "equivalent_sourcing_verified_retail_price_usd": "$51.99 USD (HonkCare Jet Fan 29347 7,500mAh / 130k RPM, 1-unit free worldwide >$60) / $37.99 USD (HonkCare Turbo Fan 29334 5,000mAh / 110k RPM)",
            "supplier_model_match": "Shenzhen Honk Electronic Co., Ltd. (honkcare.com / honktech.com) Jet Fan 29347 (7,500mAh, 130,000 RPM) & Turbo Fan 29334 (5,000mAh, 110,000 RPM)",
            "supplier_fob_quote_usd": "UNKNOWN_RFQ_REQUIRED (direct retail $37.99-$51.99 on honkcare.com does not expose B2B OEM MOQ FOB tier price)",
            "landed_us_cost_usd": "UNKNOWN (UN3481 lithium-battery <100Wh air surcharge + MSDS/PI967 packaging unquoted)",
            "customer_aov_usd": "UNKNOWN",
            "demand_evidence_status": "UNKNOWN_DEMAND_EVIDENCE (0 captured local Meta DB ads; Meta Ad Library automated HTTP 403; compressed-air replacement brands Wolfbox/Fanttik active on Amazon/TikTok/DTC)",
            "shipping_and_return_risk": "UN3481_LITHIUM_AND_OEM_UNDERCUT_RISK (17.76-28.8 Wh Li-ion requires UN38.3/MSDS/PI967 air-line compliance; factory direct retail $37.99-$51.99 compresses generic dropship price umbrella against Fanttik $49.99)",
            "commercial_decision": "RESEARCH_MORE_OR_REJECT_UNLESS_B2B_FOB_BELOW_14_USD_SECURED",
        },
    },
]


async def _ensure_batch3_run(session: AsyncSession, record_count: int) -> None:
    ds_obj = await session.get(DataSource, DATA_SOURCE_ID)
    if not ds_obj:
        session.add(
            DataSource(
                id=DATA_SOURCE_ID,
                name="Public DTC & OEM Catalog Collector",
                source_type=DataSourceType.OTHER,
                geographic_coverage="US",
                is_active=True,
                notes="Direct $0.00 public HTTP acquisition of official OEM/DTC & supplier pages.",
            )
        )
        await session.flush()

    job_obj = await session.get(CollectionJob, COLLECTION_JOB_ID)
    if not job_obj:
        session.add(
            CollectionJob(
                id=COLLECTION_JOB_ID,
                data_source_id=DATA_SOURCE_ID,
                name="Batch 3 Genuine US Dropshipping Opportunities Discovery",
                job_type="us_opportunity_discovery",
                is_active=True,
                config={"paid_apify": False, "estimated_spend_usd": 0.0},
            )
        )
        await session.flush()

    run_obj = await session.get(CollectionRun, COLLECTION_RUN_ID)
    notes = (
        "Genuine $0.00 Batch 3 + v2 commercial validation captures: separated competitor "
        "benchmarks, corded category benchmarks (XPOWER A-2), equivalent OEM direct retail "
        "(HonkCare 29347), and identifiable factory records (Doglemi PD50128/PD50128-L, ZHONGHE ZH2087T)."
    )
    if not run_obj:
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        session.add(
            CollectionRun(
                id=COLLECTION_RUN_ID,
                job_id=COLLECTION_JOB_ID,
                status="COMPLETED",
                started_at=now_naive,
                completed_at=now_naive,
                records_fetched=record_count,
                records_new=record_count,
                records_updated=0,
                records_duplicate=0,
                errors=0,
                coverage_notes=notes,
            )
        )
    else:
        run_obj.records_fetched = record_count
        run_obj.coverage_notes = notes
    await session.flush()


async def ingest_batch3_opportunities(
    session: AsyncSession,
    manifest_path: Path = MANIFEST_PATH,
    repo_root: Path = REPO_ROOT,
    score_date: str = "2026-11-12",
) -> Dict[str, Any]:
    """Verify and idempotently ingest Batch 3 captures, semantic offers, products & scores."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    batch_items = [
        item
        for item in manifest.get("dtc_manufacturer_evidence", [])
        if item.get("discovery_batch") in BATCH3_KEYS
    ]
    by_key: Dict[tuple[str, str], Dict[str, Any]] = {
        (item["manufacturer"], item["product_identity"]): item for item in batch_items
    }
    if len(by_key) < len(SOURCE_RECORD_MAP):
        missing = set(SOURCE_RECORD_MAP) - set(by_key)
        raise RuntimeError(f"Missing Batch 3 manifest items: {sorted(missing)}")

    # Validate every priced manifest artifact via inspect_artifact_content before writing DB
    for opp in OPPORTUNITIES:
        for off_cfg in opp["offers"]:
            m_key = off_cfg["manifest_key"]
            item = by_key[m_key]
            passed, reason, _ = inspect_artifact_content(
                artifact_path=repo_root / item["artifact_path"],
                expected_digest=item["artifact_sha256"],
                expected_identity=m_key[1],
                expected_price=float(item["extracted_price_usd"]),
                expected_currency=item["currency"],
                source_url=item["url"],
                expected_timestamp=item["capture_timestamp"],
                repo_root=repo_root,
            )
            if not passed:
                raise RuntimeError(f"Batch 3 artifact validation failed for {m_key}: {reason}")

    counts_before = await snapshot_counts(session)
    await _ensure_batch3_run(session, len(by_key))

    # Upsert all verified SourceRecords mapped from manifest
    signatures: Dict[tuple[str, str], str] = {}
    for m_key, srec_id in SOURCE_RECORD_MAP.items():
        item = by_key[m_key]
        sku = m_key[1]
        price_val = item["extracted_price_usd"]
        sig_price = float(price_val) if isinstance(price_val, (int, float)) else 0.0
        sig = generate_capture_signature(COLLECTION_RUN_ID, sku, sig_price, item["capture_timestamp"])
        signatures[m_key] = sig

        srec_raw = {
            "acquisition_method": item.get("acquisition_method", "direct_http_public_request_with_sanitized_boundary"),
            "capture_role": item.get("capture_role"),
            "provider": "authorized_http_collector",
            "retailer": item["manufacturer"],
            "url": item["url"],
            "source_url": item["url"],
            "external_id": sku,
            "product_identity": sku,
            "observed_title": item["title"],
            "observed_price": price_val,
            "currency": item["currency"],
            "availability": item["actual_availability"],
            "raw_schema_availability": item.get("raw_schema_availability"),
            "source_timestamp": item["capture_timestamp"],
            "raw_http_status": int(item["http_status"]),
            "retrieval_status": item["outcome"],
            "artifact_path": item["artifact_path"],
            "artifact_sha256": item["artifact_sha256"],
            "original_response_sha256": item["original_response_sha256"],
            "capture_signature": sig,
            "paid_apify_used": False,
            "estimated_spend_usd": 0.0,
        }
        srec = await session.get(SourceRecord, srec_id)
        if not srec:
            session.add(
                SourceRecord(
                    id=srec_id,
                    collection_run_id=COLLECTION_RUN_ID,
                    source_type=DataSourceType.OTHER,
                    external_id=sku,
                    raw_data=srec_raw,
                    geographic_context="US",
                    geo_confidence=ConfidenceLevel.HIGH,
                    is_processed=True,
                    is_duplicate=False,
                    is_synthetic=False,
                )
            )
        else:
            srec.collection_run_id = COLLECTION_RUN_ID
            srec.raw_data = srec_raw
    await session.flush()

    dedup_stats = {"products_created": 0, "products_reused": 0, "offers_created": 0, "offers_updated": 0}
    records_out: List[Dict[str, Any]] = []

    for opp in OPPORTUNITIES:
        sku = opp["external_id"]
        sup_key = opp["supplier_key"]
        sup_item = by_key[sup_key]

        existing_prod = (
            await session.execute(
                select(Product).where(
                    (Product.normalized_name == opp["normalized_name"])
                    | (Product.external_id == sku)
                )
            )
        ).scalars().first()

        raw_prod = {
            "discovery_origin": "us_dropship_competitor_and_supplier_discovery",
            "discovery_batch": BATCH3_V2_KEY,
            "competitor_benchmark_sku": sku,
            "commercial_model": opp["commercial_model"],
            "supplier_source_record_id": SOURCE_RECORD_MAP[sup_key],
            "supplier_url": sup_item["url"],
            **opp["commercial_notes"],
        }

        if not existing_prod:
            prod_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"batch3:{opp['primary_url']}:{sku}"))
            existing_prod = Product(
                id=prod_id,
                name=opp["name"],
                normalized_name=opp["normalized_name"],
                description=opp["functional_use_case"],
                category=opp["category"],
                source_url=opp["primary_url"],
                min_price_usd=opp["candidate_min_price_usd"],
                max_price_usd=opp["candidate_max_price_usd"],
                target_country="US",
                us_relevance_confidence=ConfidenceLevel.HIGH,
                is_physical=True,
                is_synthetic=False,
                opportunity_status="PARTIALLY_VALIDATED",
                functional_use_case=opp["functional_use_case"],
                customer_pain=opp["customer_pain"],
                primary_bundle_qty=1,
                source_type=DataSourceType.MANUAL_IMPORT,
                external_id=sku,
                raw_data=raw_prod,
            )
            session.add(existing_prod)
            dedup_stats["products_created"] += 1
        else:
            existing_prod.source_type = DataSourceType.MANUAL_IMPORT
            existing_prod.opportunity_status = "PARTIALLY_VALIDATED"
            existing_prod.min_price_usd = opp["candidate_min_price_usd"]
            existing_prod.max_price_usd = opp["candidate_max_price_usd"]
            existing_prod.raw_data = raw_prod
            dedup_stats["products_reused"] += 1
        await session.flush()

        offer_summaries: List[Dict[str, Any]] = []
        for off_cfg in opp["offers"]:
            m_key = off_cfg["manifest_key"]
            item = by_key[m_key]
            srec_id = SOURCE_RECORD_MAP[m_key]
            price_val = float(item["extracted_price_usd"])
            offer_raw = {
                "source_record_id": srec_id,
                "collection_run_id": COLLECTION_RUN_ID,
                "artifact_path": item["artifact_path"],
                "artifact_sha256": item["artifact_sha256"],
                "capture_signature": signatures[m_key],
                "availability": item["actual_availability"],
                "raw_schema_availability": item.get("raw_schema_availability"),
                "retailer": item["manufacturer"],
                "offer_role": off_cfg["offer_role"],
                "price_semantic": off_cfg["price_semantic"],
                "is_competitor_benchmark": off_cfg["is_competitor_benchmark"],
                "notes": off_cfg["notes"],
            }
            observed_naive = datetime.fromisoformat(item["capture_timestamp"]).replace(tzinfo=None)
            offer = await session.get(ProductOffer, off_cfg["offer_id"])
            if not offer:
                offer = ProductOffer(
                    id=off_cfg["offer_id"],
                    product_id=existing_prod.id,
                    source_url=item["url"],
                    price_usd=price_val,
                    currency=item["currency"],
                    quantity=1,
                    is_bundle=False,
                    observed_at=observed_naive,
                    evidence_type=off_cfg["evidence_type"],
                    price_evidence_type=off_cfg["price_evidence_type"],
                    raw_data=offer_raw,
                )
                session.add(offer)
                dedup_stats["offers_created"] += 1
            else:
                offer.product_id = existing_prod.id
                offer.source_url = item["url"]
                offer.price_usd = price_val
                offer.observed_at = observed_naive
                offer.evidence_type = off_cfg["evidence_type"]
                offer.price_evidence_type = off_cfg["price_evidence_type"]
                offer.raw_data = offer_raw
                dedup_stats["offers_updated"] += 1
            await session.flush()

            v_res = await verify_commercial_evidence_db(
                session,
                url=item["url"],
                price_evidence_type=off_cfg["price_evidence_type"].value,
                source_record_id=srec_id,
                expected_asin=m_key[1],
                observed_price=price_val,
                currency=item["currency"],
                retailer_name=item["manufacturer"],
                product_identity=m_key[1],
                observed_at=item["capture_timestamp"],
            )
            if v_res.outcome != EvidenceVerificationOutcome.VERIFIED:
                raise RuntimeError(f"Batch 3 DB provenance gate rejected {m_key}: {v_res.verification_notes}")

            offer_summaries.append(
                {
                    "offer_id": off_cfg["offer_id"],
                    "source_record_id": srec_id,
                    "sku": m_key[1],
                    "retailer": item["manufacturer"],
                    "offer_role": off_cfg["offer_role"],
                    "price_semantic": off_cfg["price_semantic"],
                    "is_competitor_benchmark": off_cfg["is_competitor_benchmark"],
                    "price_usd": price_val,
                    "declared_availability": item["actual_availability"],
                    "verification_outcome": v_res.outcome.value,
                }
            )

        primary_off = offer_summaries[0]
        records_out.append(
            {
                "product_id": existing_prod.id,
                "name": existing_prod.name,
                "category": existing_prod.category,
                "commercial_model": opp["commercial_model"],
                "collection_run_id": COLLECTION_RUN_ID,
                "source_record_id": primary_off["source_record_id"],
                "supplier_source_record_id": SOURCE_RECORD_MAP[sup_key],
                "supplier_url": sup_item["url"],
                "offer_id": primary_off["offer_id"],
                "sku": primary_off["sku"],
                "price_usd": primary_off["price_usd"],
                "verification_outcome": primary_off["verification_outcome"],
                "offers": offer_summaries,
            }
        )

    await session.commit()

    scorer = ScoringEngine(session, mode="balanced")
    for rec in records_out:
        await scorer.score_product_balanced(rec["product_id"], score_date=score_date)
    await session.commit()

    for rec in records_out:
        score_row = (
            await session.execute(
                select(OpportunityScore)
                .where(OpportunityScore.product_id == rec["product_id"])
                .order_by(OpportunityScore.score_date.desc(), OpportunityScore.created_at.desc())
            )
        ).scalars().first()
        prod_row = await session.get(Product, rec["product_id"])
        rec["opportunity_status"] = prod_row.opportunity_status if prod_row else None
        rec["opportunity_score_id"] = score_row.id if score_row else None
        rec["observed_single_price_usd"] = score_row.observed_single_price_usd if score_row else None
        rec["customer_aov_usd"] = score_row.customer_aov_usd if score_row else None
        rec["evidence_confidence"] = score_row.evidence_confidence if score_row else None
        rec["core_opportunity_score"] = score_row.core_opportunity_score if score_row else None
        rec["composite_score"] = score_row.composite_score if score_row else None
        rec["bundle_potential"] = score_row.bundle_potential if score_row else None
        rec["pricing_evidence_component"] = (
            (score_row.confidence_components or {}).get("pricing_evidence") if score_row else None
        )

    counts_after = await snapshot_counts(session)
    return {
        "batch_key": BATCH3_V2_KEY,
        "counts_before": counts_before,
        "counts_after": counts_after,
        "dedup_stats": dedup_stats,
        "records": records_out,
    }


async def run_cli(db_path: Path, score_date: str, create_backup: bool) -> Dict[str, Any]:
    resolved_db = db_path.resolve()
    if not resolved_db.exists():
        raise FileNotFoundError(f"Database not found: {resolved_db}")

    backup_path = None
    if create_backup:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = resolved_db.parent / f"{resolved_db.stem}_pre_batch3_cli_{ts}.db"
        shutil.copy2(resolved_db, backup_path)

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{resolved_db.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_maker() as session:
            result = await ingest_batch3_opportunities(session, score_date=score_date)
    finally:
        await engine.dispose()

    result["database_path"] = str(resolved_db)
    result["backup_path"] = str(backup_path) if backup_path else None
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Idempotent Batch 3 US dropshipping opportunities commercial validation ingestion."
    )
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to SQLite database.")
    parser.add_argument("--score-date", default="2026-11-12", help="ISO score_date.")
    parser.add_argument("--no-backup", action="store_true", help="Skip pre-run DB backup.")
    args = parser.parse_args()

    out = asyncio.run(run_cli(Path(args.db), args.score_date, create_backup=not args.no_backup))
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
