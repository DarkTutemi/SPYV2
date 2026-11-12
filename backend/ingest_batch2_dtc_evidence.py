"""
US WIN HUNTER — Reproducible & Idempotent Batch 2 Multi-Category DTC/OEM Ingestion

Reads the five verified Batch 2 captures from docs/run_reports/sanitized_acquisition_manifest.json,
audits each HTML capture against its recorded manifest SHA-256, URL, timestamp, SKU, price, and
currency, idempotently upserts CollectionRun / SourceRecord / deduplicated Product / ProductOffer,
verifies DB-backed provenance, and computes BalancedScoringEngine OpportunityScores.
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
from typing import Any, Dict, List, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Allow running both as `python backend/ingest_batch2_dtc_evidence.py` and as an imported module.
BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.engines.scoring import ScoringEngine  # noqa: E402
from app.models.models import (  # noqa: E402
    CollectionJob,
    CollectionJobStatus,
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
    validate_commercial_evidence_strict_db,
    verify_commercial_evidence_db,
)

DEFAULT_DB_PATH = REPO_ROOT / "data" / "winhunter.db"
MANIFEST_PATH = REPO_ROOT / "docs" / "run_reports" / "sanitized_acquisition_manifest.json"
BATCH_KEY = "2026-11-12_multi_category_public_dtc"
DATA_SOURCE_ID = "src_dtc_public_catalog_collector"
COLLECTION_JOB_ID = "job_dtc_discovery_batch2_20261112"
COLLECTION_RUN_ID = "run_dtc_discovery_batch2_20261112"

# Domain context for the 5 Batch 2 SKUs (no pricing/availability invented here; all commercial facts come from manifest + artifacts).
BATCH2_PRODUCT_METADATA: Dict[str, Dict[str, str]] = {
    "GENIUS5": {
        "source_record_id": "srec_dtc_noco_genius5_20261112",
        "offer_id": "off_dtc_noco_genius5_20261112",
        "name": "NOCO GENIUS5 5-Amp 6V/12V Smart Battery Charger",
        "normalized_name": "noco genius5 5-amp 6v 12v smart battery charger",
        "functional_use_case": (
            "Compact automatic 5A 6V/12V battery charger, maintainer, trickle charger, and "
            "desulfator for cars, trucks, SUVs, motorcycles, and marine batteries."
        ),
        "customer_pain": (
            "Dead morning car batteries, overcharged/damaged AGM or cold-weather cells, and "
            "bulky unsafe chargers that fail to restore sulfated lead-acid batteries."
        ),
    },
    "KPHJ320": {
        "source_record_id": "srec_dtc_kreg_kphj320_20261112",
        "offer_id": "off_dtc_kreg_kphj320_20261112",
        "name": "Kreg Pocket-Hole Jig 320 Woodworking Joinery Kit",
        "normalized_name": "kreg pocket-hole jig 320 woodworking joinery kit",
        "functional_use_case": (
            "Portable twist-apart hardened-steel pocket-hole drill guide with preset thickness "
            "stops for building and repairing wood furniture and cabinets cleanly."
        ),
        "customer_pain": (
            "Split wood boards, crooked butt joints, wobbly dining chairs/shelving, and "
            "inability to build clean hidden-screw repairs without an expensive stationary workshop."
        ),
    },
    "DLC-2ABC": {
        "source_record_id": "srec_dtc_cuisinart_dlc2abc_20261112",
        "offer_id": "off_dtc_cuisinart_dlc2abc_20261112",
        "name": "Cuisinart Mini-Prep Plus 3-Cup Food Processor (DLC-2ABC)",
        "normalized_name": "cuisinart mini-prep plus 3-cup food processor dlc-2abc",
        "functional_use_case": (
            "Compact 250W countertop mini chopper/grinder with auto-reversing SmartPower blade "
            "for daily garlic, onions, herbs, nuts, and small-batch sauces."
        ),
        "customer_pain": (
            "Tedious tear-inducing manual garlic/onion mincing and dragging a bulky 12-cup food "
            "processor out of deep cabinets for tiny everyday prep jobs."
        ),
    },
    "GS23L": {
        "source_record_id": "srec_dtc_conair_gs23l_20261112",
        "offer_id": "off_dtc_conair_gs23l_20261112",
        "name": "Conair ExtremeSteam Handheld Fabric Steamer (GS23L)",
        "normalized_name": "conair extremesteam handheld fabric steamer gs23l",
        "functional_use_case": (
            "Compact dual-heat handheld garment and upholstery steamer delivering fast vertical "
            "wrinkle release on shirts, dresses, drapes, and travel attire."
        ),
        "customer_pain": (
            "Setting up clunky ironing boards before morning commutes, scorching delicate "
            "fabrics, and wrinkled wardrobe garments after suitcase packing."
        ),
    },
    "841230028873": {
        "source_record_id": "srec_dtc_tempur_symphony_20261112",
        "offer_id": "off_dtc_tempur_symphony_20261112",
        "name": "Tempur-Pedic TEMPUR-Symphony Dual-Sided Support Pillow",
        "normalized_name": "tempur-pedic tempur-symphony dual-sided support pillow",
        "functional_use_case": (
            "Dual-sided TEMPUR pressure-relieving pillow combining an arched back-sleeper contour "
            "side with a flat traditional side sleeper profile and washable cover."
        ),
        "customer_pain": (
            "Flipping hot, flattened pillows all night and alternating between side and back "
            "sleeping positions with insufficient cervical loft stability."
        ),
    },
}


async def snapshot_counts(session: AsyncSession) -> Dict[str, int]:
    """Capture row counts across key commercial, discovery, and invariant tables."""
    queries = {
        "products": "SELECT COUNT(*) FROM products",
        "collection_runs": "SELECT COUNT(*) FROM collection_runs",
        "source_records": "SELECT COUNT(*) FROM source_records",
        "product_offers": "SELECT COUNT(*) FROM product_offers",
        "opportunity_scores": "SELECT COUNT(*) FROM opportunity_scores",
        "advertisements": "SELECT COUNT(*) FROM advertisements",
        "advertisement_snapshots": "SELECT COUNT(*) FROM advertisement_snapshots",
        "apify_spend_reservations": "SELECT COUNT(*) FROM apify_spend_reservations",
    }
    out: Dict[str, int] = {}
    for key, sql in queries.items():
        out[key] = int((await session.execute(text(sql))).scalar_one())
    return out


async def _ensure_batch2_run(session: AsyncSession, item_count: int) -> None:
    ds_obj = await session.get(DataSource, DATA_SOURCE_ID)
    if not ds_obj:
        session.add(
            DataSource(
                id=DATA_SOURCE_ID,
                name="Public DTC & OEM Catalog Collector",
                source_type=DataSourceType.OTHER,
                geographic_coverage="US",
                is_active=True,
                notes="Direct $0.00 public HTTP acquisition of official OEM/DTC product catalogs.",
            )
        )
        await session.flush()

    job_obj = await session.get(CollectionJob, COLLECTION_JOB_ID)
    if not job_obj:
        session.add(
            CollectionJob(
                id=COLLECTION_JOB_ID,
                data_source_id=DATA_SOURCE_ID,
                name="Batch 2 Multi-Category US DTC OEM Discovery",
                job_type="dtc_public_discovery",
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
                status=CollectionJobStatus.COMPLETED,
                started_at=now_naive,
                completed_at=now_naive,
                records_fetched=item_count,
                records_new=item_count,
                records_updated=0,
                records_duplicate=0,
                errors=0,
                coverage_notes=(
                    "Reproducible $0.00 public HTTP capture across 5 US DTC/OEM categories "
                    "(Automotive, Tools & DIY, Kitchen Prep, Apparel Care, Ergonomics & Sleep)."
                ),
            )
        )
        await session.flush()


async def ingest_batch2_evidence(
    session: AsyncSession,
    manifest_path: Path = MANIFEST_PATH,
    repo_root: Path = REPO_ROOT,
    score_date: str = "2026-11-12",
) -> Dict[str, Any]:
    """
    Idempotently verify and ingest all 5 Batch 2 manifest captures into SQLite/SQLAlchemy.
    Returns before/after counts, deduplication counters, and exact persisted record IDs & scores.
    """
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    batch_items = [
        item
        for item in manifest.get("dtc_manufacturer_evidence", [])
        if item.get("discovery_batch") == BATCH_KEY
    ]
    if len(batch_items) != len(BATCH2_PRODUCT_METADATA):
        raise RuntimeError(
            f"Expected {len(BATCH2_PRODUCT_METADATA)} Batch 2 manifest entries, found {len(batch_items)}"
        )

    # Pre-validate every disk artifact against recorded manifest digest & content before DB writes
    for item in batch_items:
        passed, reason, _ = inspect_artifact_content(
            artifact_path=repo_root / item["artifact_path"],
            expected_digest=item["artifact_sha256"],
            expected_identity=item["product_identity"],
            expected_price=float(item["extracted_price_usd"]),
            expected_currency=item["currency"],
            source_url=item["url"],
            expected_timestamp=item["capture_timestamp"],
            repo_root=repo_root,
        )
        if not passed:
            raise RuntimeError(
                f"Manifest/artifact validation failed for {item['product_identity']}: {reason}"
            )

    counts_before = await snapshot_counts(session)
    await _ensure_batch2_run(session, len(batch_items))

    dedup_stats = {"products_created": 0, "products_reused": 0, "offers_created": 0, "offers_updated": 0}
    records_out: List[Dict[str, Any]] = []

    for item in batch_items:
        sku = item["product_identity"]
        meta = BATCH2_PRODUCT_METADATA[sku]
        capture_sig = generate_capture_signature(
            COLLECTION_RUN_ID,
            sku,
            float(item["extracted_price_usd"]),
            item["capture_timestamp"],
        )

        srec_raw = {
            "acquisition_method": item.get("acquisition_method", "direct_http_public_request_with_sanitized_boundary"),
            "provider": "authorized_http_collector",
            "retailer": item["manufacturer"],
            "url": item["url"],
            "source_url": item["url"],
            "external_id": sku,
            "product_identity": sku,
            "observed_title": item["title"],
            "observed_price": float(item["extracted_price_usd"]),
            "currency": item["currency"],
            "availability": item["actual_availability"],
            "raw_schema_availability": item["raw_schema_availability"],
            "source_timestamp": item["capture_timestamp"],
            "raw_http_status": int(item["http_status"]),
            "retrieval_status": "VERIFIED_EXTRACTED",
            "artifact_path": item["artifact_path"],
            "artifact_sha256": item["artifact_sha256"],
            "original_response_sha256": item["original_response_sha256"],
            "capture_signature": capture_sig,
            "paid_apify_used": False,
            "estimated_spend_usd": 0.0,
        }
        srec = await session.get(SourceRecord, meta["source_record_id"])
        if not srec:
            srec = SourceRecord(
                id=meta["source_record_id"],
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
            session.add(srec)
        else:
            srec.collection_run_id = COLLECTION_RUN_ID
            srec.raw_data = srec_raw
        await session.flush()

        existing_prod = (
            await session.execute(
                select(Product).where(
                    (Product.normalized_name == meta["normalized_name"])
                    | (Product.external_id == sku)
                )
            )
        ).scalars().first()

        if not existing_prod:
            prod_id = str(uuid.uuid5(uuid.NAMESPACE_URL, item["url"]))
            existing_prod = Product(
                id=prod_id,
                name=meta["name"],
                normalized_name=meta["normalized_name"],
                description=meta["functional_use_case"],
                category=item["category"],
                source_url=item["url"],
                min_price_usd=float(item["extracted_price_usd"]),
                max_price_usd=float(item["extracted_price_usd"]),
                target_country="US",
                us_relevance_confidence=ConfidenceLevel.HIGH,
                is_physical=True,
                is_synthetic=False,
                opportunity_status="PARTIALLY_VALIDATED",
                functional_use_case=meta["functional_use_case"],
                customer_pain=meta["customer_pain"],
                primary_bundle_qty=1,
                source_type=DataSourceType.MANUAL_IMPORT,
                external_id=sku,
                raw_data={
                    "discovery_origin": "public_dtc_oem_capture",
                    "discovery_batch": BATCH_KEY,
                    "commercial_model": "MODEL_A_SINGLE_PRODUCT",
                    "manufacturer": item["manufacturer"],
                    "sku": sku,
                    "verified_catalog_price_usd": float(item["extracted_price_usd"]),
                    "actual_availability": item["actual_availability"],
                    "raw_schema_availability": item["raw_schema_availability"],
                    "why_unqualified_for_scale_yet": (
                        "Single-source OEM catalog price verified at $0.00 spend; independent "
                        "Meta/TikTok advertiser demand and supplier landed COGS remain UNKNOWN."
                    ),
                },
            )
            session.add(existing_prod)
            dedup_stats["products_created"] += 1
        else:
            existing_prod.source_type = DataSourceType.MANUAL_IMPORT
            existing_prod.opportunity_status = "PARTIALLY_VALIDATED"
            dedup_stats["products_reused"] += 1
        await session.flush()

        offer_raw = {
            "source_record_id": meta["source_record_id"],
            "collection_run_id": COLLECTION_RUN_ID,
            "artifact_path": item["artifact_path"],
            "artifact_sha256": item["artifact_sha256"],
            "capture_signature": capture_sig,
            "availability": item["actual_availability"],
            "raw_schema_availability": item["raw_schema_availability"],
            "retailer": item["manufacturer"],
            "notes": f"Authentic OEM catalog price & Schema.org availability extracted from {item['url']}.",
        }
        observed_naive = datetime.fromisoformat(item["capture_timestamp"]).replace(tzinfo=None)
        offer = await session.get(ProductOffer, meta["offer_id"])
        if not offer:
            offer = ProductOffer(
                id=meta["offer_id"],
                product_id=existing_prod.id,
                source_url=item["url"],
                price_usd=float(item["extracted_price_usd"]),
                currency=item["currency"],
                quantity=1,
                is_bundle=False,
                observed_at=observed_naive,
                evidence_type=EvidenceType.OEM_LIST_PRICE,
                price_evidence_type=PriceEvidenceType.OEM_LIST_PRICE,
                raw_data=offer_raw,
            )
            session.add(offer)
            dedup_stats["offers_created"] += 1
        else:
            offer.product_id = existing_prod.id
            offer.price_usd = float(item["extracted_price_usd"])
            offer.observed_at = observed_naive
            offer.evidence_type = EvidenceType.OEM_LIST_PRICE
            offer.price_evidence_type = PriceEvidenceType.OEM_LIST_PRICE
            offer.raw_data = offer_raw
            dedup_stats["offers_updated"] += 1
        await session.flush()

        v_res = await verify_commercial_evidence_db(
            session,
            url=item["url"],
            price_evidence_type="OEM_LIST_PRICE",
            source_record_id=meta["source_record_id"],
            expected_asin=sku,
            observed_price=float(item["extracted_price_usd"]),
            currency=item["currency"],
            retailer_name=item["manufacturer"],
            product_identity=sku,
            observed_at=item["capture_timestamp"],
        )
        if v_res.outcome != EvidenceVerificationOutcome.VERIFIED:
            raise RuntimeError(f"DB provenance gate rejected {sku}: {v_res.verification_notes}")

        strict_price_type = await validate_commercial_evidence_strict_db(
            session,
            url=item["url"],
            price_evidence_type="OEM_LIST_PRICE",
            source_record_id=meta["source_record_id"],
            expected_asin=sku,
            observed_price=float(item["extracted_price_usd"]),
            retailer_name=item["manufacturer"],
            product_identity=sku,
            observed_at=item["capture_timestamp"],
        )
        if strict_price_type != "OEM_LIST_PRICE":
            raise RuntimeError(f"Strict commercial check returned unexpected type for {sku}: {strict_price_type}")

        records_out.append(
            {
                "product_id": existing_prod.id,
                "name": existing_prod.name,
                "category": existing_prod.category,
                "collection_run_id": COLLECTION_RUN_ID,
                "source_record_id": meta["source_record_id"],
                "offer_id": meta["offer_id"],
                "sku": sku,
                "source_url": item["url"],
                "artifact_path": item["artifact_path"],
                "manifest_sha256": item["artifact_sha256"],
                "capture_timestamp": item["capture_timestamp"],
                "price_usd": float(item["extracted_price_usd"]),
                "currency": item["currency"],
                "price_evidence_type": "OEM_LIST_PRICE",
                "declared_availability": item["actual_availability"],
                "raw_schema_availability": item["raw_schema_availability"],
                "verification_outcome": v_res.outcome.value,
            }
        )

    await session.commit()

    scorer = ScoringEngine(session, mode="balanced")
    for rec in records_out:
        await scorer.score_product_balanced(rec["product_id"], score_date=score_date)
    await session.commit()

    # Fetch exact persisted OpportunityScore ID & score values for each ingested product
    for rec in records_out:
        score_row = (
            await session.execute(
                select(OpportunityScore)
                .where(OpportunityScore.product_id == rec["product_id"])
                .order_by(OpportunityScore.score_date.desc(), OpportunityScore.created_at.desc())
            )
        ).scalars().first()
        prod_row = await session.get(Product, rec["product_id"])
        if not score_row:
            raise RuntimeError(f"Missing OpportunityScore after scoring {rec['product_id']}")
        rec["opportunity_status"] = prod_row.opportunity_status if prod_row else None
        rec["opportunity_score_id"] = score_row.id
        rec["score_date"] = score_row.score_date
        rec["observed_single_price_usd"] = score_row.observed_single_price_usd
        rec["evidence_confidence"] = score_row.evidence_confidence
        rec["core_opportunity_score"] = score_row.core_opportunity_score
        rec["composite_score"] = score_row.composite_score
        rec["bundle_potential"] = score_row.bundle_potential

    counts_after = await snapshot_counts(session)
    return {
        "batch_key": BATCH_KEY,
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
        backup_path = resolved_db.parent / f"{resolved_db.stem}_pre_batch2_cli_{ts}.db"
        shutil.copy2(resolved_db, backup_path)

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{resolved_db.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_maker() as session:
            result = await ingest_batch2_evidence(session, score_date=score_date)
    finally:
        await engine.dispose()

    result["database_path"] = str(resolved_db)
    result["backup_path"] = str(backup_path) if backup_path else None
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Idempotent reproducible Batch 2 US DTC/OEM evidence ingestion."
    )
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to target SQLite database.")
    parser.add_argument("--score-date", default="2026-11-12", help="ISO score_date to persist.")
    parser.add_argument("--no-backup", action="store_true", help="Skip creating pre-run DB backup.")
    args = parser.parse_args()

    report = asyncio.run(run_cli(Path(args.db), args.score_date, create_backup=not args.no_backup))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
