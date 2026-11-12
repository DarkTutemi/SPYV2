"""
US WIN HUNTER — Reproducible Batch 3 Genuine US Dropshipping Opportunity Ingestion

Ingests three commercially credible US dropshipping opportunities backed by live public
retail competitor price captures and identifiable OEM/factory supplier records from
docs/run_reports/sanitized_acquisition_manifest.json without fabricating COGS, margins,
sales volumes, or Meta advertiser counts.
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
COLLECTION_JOB_ID = "job_us_opportunities_batch3_20261112"
COLLECTION_RUN_ID = "run_us_opportunities_batch3_20261112"

# Map manifest entries by product_identity -> SourceRecord ID & role
SOURCE_RECORD_IDS: Dict[str, str] = {
    "48906329850134": "srec_b3_ruffrover_20261112",
    "Pet-Car-Seat-Cover": "srec_b3_doglemi_supplier_20261112",
    "100236241": "srec_b3_aquasana_hero_20261112",
    "100236244": "srec_b3_aquasana_refill_20261112",
    "ZH2087T": "srec_b3_ningboware_supplier_20261112",
    "A-2": "srec_b3_xpower_a2_20261112",
    "HONK_JETFAN": "srec_b3_honkcare_supplier_20261112",
}

OPPORTUNITIES: List[Dict[str, Any]] = [
    {
        "external_id": "48906329850134",
        "offer_id": "off_b3_ruffrover_extender_20261112",
        "supplier_identity": "Pet-Car-Seat-Cover",
        "name": "Hard-Bottom Waterproof Dog Car Seat Extender",
        "normalized_name": "hard-bottom waterproof dog car seat extender",
        "category": "Pet Travel & Automotive",
        "commercial_model": "MODEL_A_SINGLE_PRODUCT",
        "price_evidence_type": PriceEvidenceType.DTC_MANUFACTURER_OBSERVED_PRICE,
        "evidence_type": EvidenceType.DTC_MANUFACTURER_OBSERVED_PRICE,
        "functional_use_case": (
            "Rigid folding hard-bottom backseat extender and waterproof Oxford protector bridging "
            "the rear footwell gap so medium/large dogs travel without sliding or scratching leather."
        ),
        "customer_pain": (
            "Dogs slump into the rear footwell on sudden stops, soil/scratch upholstery, and snap "
            "thin cloth hammocks; DTC rivals sell at $159.95-$199.00 with slow overseas shipping."
        ),
        "commercial_notes": {
            "proposed_us_dtc_target_aov_usd": "69.99-89.99 (strategic target, NOT observed price)",
            "observed_competitor_benchmarks": [
                "RuffRover 2.0 ($159.95 USD In Stock, captured)",
                "Dog-Go (dog-go.co $199.00 range, HTTP 200)",
                "Kurgo Rover Bridge ($69-$79.99 soft bridge)",
            ],
            "identifiable_supplier": "Guangzhou Dolemi Pet Products Co., Ltd. (https://www.doglemi.com/products/Pet-Car-Seat-Cover.htm)",
            "sourcing_cogs_status": "UNKNOWN_RFQ_REQUIRED (public page omits FOB unit price)",
            "demand_evidence_status": "UNKNOWN_DEMAND_EVIDENCE (0 captured local Meta DB ads; Meta Ad Library web HTTP 403)",
            "shipping_and_return_risk": "HIGH_VOLUMETRIC_WEIGHT (2.5-4.0 kg rigid panels raise air-parcel cost and make China returns unviable; prefer US 3PL for scaling).",
            "optional_natural_bundle": "Single extender + matching car door protectors / seatbelt tether.",
        },
    },
    {
        "external_id": "100236241",
        "offer_id": "off_b3_aquasana_shower_20261112",
        "supplier_identity": "ZH2087T",
        "refill_identity": "100236244",
        "name": "Multi-Stage High-Pressure Filtered Showerhead (+ Quarterly Refill System)",
        "normalized_name": "multi-stage high-pressure filtered showerhead quarterly refill system",
        "category": "Bath & Home Wellness",
        "commercial_model": "MODEL_B_NATURAL_MULTI_UNIT",
        "price_evidence_type": PriceEvidenceType.OEM_LIST_PRICE,
        "evidence_type": EvidenceType.OEM_LIST_PRICE,
        "functional_use_case": (
            "High-pressure handheld filtered showerhead with replaceable multi-stage KDF/carbon "
            "cartridge reducing chlorine odor, sediment, and mineral dryness with 60-90 day refills."
        ),
        "customer_pain": (
            "Hard-water skin/hair dryness, chlorine smell, weak apartment shower pressure, and "
            "competing ABS filters cracking/leaking at swivel joints or spraying carbon fines."
        ),
        "commercial_notes": {
            "proposed_us_dtc_target_aov_usd": "49.99-64.99 Hero + 19.99-29.99 2-pack refill (strategic target, NOT observed price)",
            "observed_competitor_benchmarks": [
                "Aquasana Chrome Handheld Shower Filter 100236241 ($99.99 USD In Stock, captured)",
                "Aquasana Replacement Cartridge 100236244 ($62.99 USD In Stock, captured)",
                "SparkPod (sparkpod.com $59.95-$73.95 hero / $22.95-$27.95 cartridge)",
                "AquaBliss (aquabliss.com $64.99 SF100/SF400)",
            ],
            "identifiable_supplier": "ZHONGHE / Ningboware OEM Shower Head Manufacturer (https://www.ningboware.com/, models ZH2087T, ZH2092T-1B, ZH2256C)",
            "sourcing_cogs_status": "UNKNOWN_RFQ_REQUIRED (Ningbo OEM requires RFQ; Made-in-China HTTP 403)",
            "demand_evidence_status": "UNKNOWN_DEMAND_EVIDENCE (0 captured local Meta DB ads; Meta Ad Library web HTTP 403)",
            "shipping_and_return_risk": "LOW_PARCEL_WEIGHT (0.5-0.8 kg, no batteries; include brass swivel nut/silicone washers + PTFE tape + 60s flush card to cut leak returns).",
            "optional_natural_bundle": "Hero showerhead + 2-pack 90-day replacement filter refills (natural consumable LTV).",
        },
    },
    {
        "external_id": "A-2",
        "offer_id": "off_b3_xpower_duster_20261112",
        "supplier_identity": "HONK_JETFAN",
        "name": "Brushless High-Speed Electric Air Duster (Canned Air Replacement)",
        "normalized_name": "brushless high-speed electric air duster canned air replacement",
        "category": "Home Tech & Auto Detailing",
        "commercial_model": "MODEL_A_SINGLE_PRODUCT",
        "price_evidence_type": PriceEvidenceType.OEM_LIST_PRICE,
        "evidence_type": EvidenceType.OEM_LIST_PRICE,
        "functional_use_case": (
            "Reusable high-velocity electric jet-fan air duster with precision nozzle attachments "
            "replacing disposable aerosol cans for PCs, keyboards, car vents, cameras, and tracks."
        ),
        "customer_pain": (
            "Expensive freezing canned air running out mid-clean; corded workshop blowers restrict "
            "car interior/desk reach."
        ),
        "commercial_notes": {
            "proposed_us_dtc_target_aov_usd": "44.99-69.99 cordless brushless kit (strategic target, NOT observed price)",
            "observed_competitor_benchmarks": [
                "XPOWER A-2 Airrow Pro ($65.00 USD In Stock, captured)",
                "Shenzhen HonkCare Storefront (honkcare.com $60-$99 listed on homepage, HTTP 200)",
                "Wolfbox MF100/MF200 ($45-$80 retail range via search)",
                "Fanttik B10 Pro (fanttik.com HTTP 200)",
            ],
            "identifiable_supplier": "Shenzhen Honk Electronic Co., Ltd. (https://honkcare.com/)",
            "sourcing_cogs_status": "UNKNOWN_RFQ_REQUIRED (direct factory storefront without B2B MOQ tier table)",
            "demand_evidence_status": "UNKNOWN_DEMAND_EVIDENCE (0 captured local Meta DB ads; Meta Ad Library web HTTP 403)",
            "shipping_and_return_risk": "LITHIUM_BATTERY_SHIPPING (requires MSDS battery-compliant air line & motor thermal QA to limit defect returns).",
            "optional_natural_bundle": "Single blower + magnetic micro-nozzle & soft brush detailing kit.",
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
                coverage_notes=(
                    "Genuine $0.00 Batch 3 US dropshipping opportunity captures: competitor retail "
                    "benchmarks (RuffRover, Aquasana, XPOWER) paired with identifiable OEM suppliers."
                ),
            )
        )
        await session.flush()


async def ingest_batch3_opportunities(
    session: AsyncSession,
    manifest_path: Path = MANIFEST_PATH,
    repo_root: Path = REPO_ROOT,
    score_date: str = "2026-11-12",
) -> Dict[str, Any]:
    """Verify and idempotently ingest Batch 3 competitor captures, suppliers, products & scores."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    batch_items = [
        item
        for item in manifest.get("dtc_manufacturer_evidence", [])
        if item.get("discovery_batch") == BATCH3_KEY
    ]
    by_identity = {item["product_identity"]: item for item in batch_items}
    if len(by_identity) != len(SOURCE_RECORD_IDS):
        raise RuntimeError(
            f"Expected {len(SOURCE_RECORD_IDS)} Batch 3 manifest items, found {len(by_identity)}"
        )

    # Validate priced retail artifacts via inspect_artifact_content before writing DB
    for opp in OPPORTUNITIES:
        item = by_identity[opp["external_id"]]
        passed, reason, _ = inspect_artifact_content(
            artifact_path=repo_root / item["artifact_path"],
            expected_digest=item["artifact_sha256"],
            expected_identity=opp["external_id"],
            expected_price=float(item["extracted_price_usd"]),
            expected_currency=item["currency"],
            source_url=item["url"],
            expected_timestamp=item["capture_timestamp"],
            repo_root=repo_root,
        )
        if not passed:
            raise RuntimeError(f"Batch 3 artifact validation failed for {opp['external_id']}: {reason}")

    counts_before = await snapshot_counts(session)
    await _ensure_batch3_run(session, len(by_identity))

    # Upsert all 7 SourceRecords (4 priced competitor/refill + 3 OEM supplier pages)
    signatures: Dict[str, str] = {}
    for sku, item in by_identity.items():
        srec_id = SOURCE_RECORD_IDS[sku]
        price_val = item["extracted_price_usd"]
        sig_price = float(price_val) if isinstance(price_val, (int, float)) else 0.0
        sig = generate_capture_signature(COLLECTION_RUN_ID, sku, sig_price, item["capture_timestamp"])
        signatures[sku] = sig

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
        item = by_identity[sku]
        srec_id = SOURCE_RECORD_IDS[sku]
        sup_item = by_identity[opp["supplier_identity"]]
        price_val = float(item["extracted_price_usd"])

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
            "discovery_batch": BATCH3_KEY,
            "commercial_model": opp["commercial_model"],
            "competitor_benchmark_sku": sku,
            "supplier_source_record_id": SOURCE_RECORD_IDS[opp["supplier_identity"]],
            "supplier_url": sup_item["url"],
            **opp["commercial_notes"],
        }

        if not existing_prod:
            prod_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"batch3:{item['url']}:{sku}"))
            existing_prod = Product(
                id=prod_id,
                name=opp["name"],
                normalized_name=opp["normalized_name"],
                description=opp["functional_use_case"],
                category=opp["category"],
                source_url=item["url"],
                min_price_usd=price_val,
                max_price_usd=price_val,
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
            existing_prod.raw_data = raw_prod
            dedup_stats["products_reused"] += 1
        await session.flush()

        offer_raw = {
            "source_record_id": srec_id,
            "collection_run_id": COLLECTION_RUN_ID,
            "artifact_path": item["artifact_path"],
            "artifact_sha256": item["artifact_sha256"],
            "capture_signature": signatures[sku],
            "availability": item["actual_availability"],
            "raw_schema_availability": item.get("raw_schema_availability"),
            "retailer": item["manufacturer"],
            "notes": f"Live US competitor benchmark capture from {item['url']}.",
        }
        observed_naive = datetime.fromisoformat(item["capture_timestamp"]).replace(tzinfo=None)
        offer = await session.get(ProductOffer, opp["offer_id"])
        if not offer:
            offer = ProductOffer(
                id=opp["offer_id"],
                product_id=existing_prod.id,
                source_url=item["url"],
                price_usd=price_val,
                currency=item["currency"],
                quantity=1,
                is_bundle=False,
                observed_at=observed_naive,
                evidence_type=opp["evidence_type"],
                price_evidence_type=opp["price_evidence_type"],
                raw_data=offer_raw,
            )
            session.add(offer)
            dedup_stats["offers_created"] += 1
        else:
            offer.product_id = existing_prod.id
            offer.price_usd = price_val
            offer.observed_at = observed_naive
            offer.evidence_type = opp["evidence_type"]
            offer.price_evidence_type = opp["price_evidence_type"]
            offer.raw_data = offer_raw
            dedup_stats["offers_updated"] += 1
        await session.flush()

        v_res = await verify_commercial_evidence_db(
            session,
            url=item["url"],
            price_evidence_type=opp["price_evidence_type"].value,
            source_record_id=srec_id,
            expected_asin=sku,
            observed_price=price_val,
            currency=item["currency"],
            retailer_name=item["manufacturer"],
            product_identity=sku,
            observed_at=item["capture_timestamp"],
        )
        if v_res.outcome != EvidenceVerificationOutcome.VERIFIED:
            raise RuntimeError(f"Batch 3 DB provenance gate rejected {sku}: {v_res.verification_notes}")

        records_out.append(
            {
                "product_id": existing_prod.id,
                "name": existing_prod.name,
                "category": existing_prod.category,
                "commercial_model": opp["commercial_model"],
                "collection_run_id": COLLECTION_RUN_ID,
                "source_record_id": srec_id,
                "supplier_source_record_id": SOURCE_RECORD_IDS[opp["supplier_identity"]],
                "supplier_url": sup_item["url"],
                "offer_id": opp["offer_id"],
                "sku": sku,
                "source_url": item["url"],
                "artifact_path": item["artifact_path"],
                "manifest_sha256": item["artifact_sha256"],
                "price_usd": price_val,
                "currency": item["currency"],
                "price_evidence_type": opp["price_evidence_type"].value,
                "declared_availability": item["actual_availability"],
                "verification_outcome": v_res.outcome.value,
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
        rec["evidence_confidence"] = score_row.evidence_confidence if score_row else None
        rec["core_opportunity_score"] = score_row.core_opportunity_score if score_row else None
        rec["composite_score"] = score_row.composite_score if score_row else None
        rec["bundle_potential"] = score_row.bundle_potential if score_row else None

    counts_after = await snapshot_counts(session)
    return {
        "batch_key": BATCH3_KEY,
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
        description="Idempotent Batch 3 US dropshipping opportunities ingestion."
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
