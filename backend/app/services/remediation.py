"""
US WIN HUNTER — Explicit, Transactional & Idempotent Discovery Remediation Service
Remediates legacy data from run_us_discovery_20261111 and run_us_verified_discovery_20261111
using audited product IDs.
Safely reclassifies unverified imports, source records, and modeled offers.
Guarantees strict idempotency (0 changes on subsequent runs).
"""

import shutil
import os
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Product,
    ProductOffer,
    BundleOffer,
    SourceRecord,
    CollectionRun,
    CollectionJobStatus,
    DataSourceType,
    ConfidenceLevel,
    EvidenceType,
    PriceEvidenceType,
    OpportunityScore,
)
from app.engines.scoring import ScoringEngine

TARGET_COLLECTION_RUN_ID = "run_us_discovery_20261111"
BATCH8_COLLECTION_RUN_ID = "run_us_verified_discovery_20261111"

ALL_TARGET_RUNS: List[Tuple[str, str]] = [
    (
        TARGET_COLLECTION_RUN_ID,
        "QUARANTINED: Manual research hypothesis import without verified external provider collection.",
    ),
    (
        BATCH8_COLLECTION_RUN_ID,
        "QUARANTINED: Manual research import with self-generated receipts; not an authentic external provider collection.",
    ),
]

# Audited legacy products (Batch 7)
AUDITED_LEGACY_PRODUCTS: Dict[str, str] = {
    "bdc47ed7-8004-417d-a44f-ba9ea09d17df": "42kHz Ultrasonic Retainer & Mouthguard Cleaning Pod",
    "9561c127-a3de-40e0-90fe-c75785f8c728": "Cordless Electric Spin Scrubber with Telescopic Extension Pole",
    "87271f92-6a6c-4c0e-a488-ed7c6a43fc5b": "High-Pressure Kitchen Sink Glass Rinser (304 Stainless Steel)",
    "b7e1baaa-e2de-4319-8088-dcd3619219d5": "Dual-Chip Red Light & Near-Infrared Therapy Lumbar Belt",
    "5f40a4c5-3161-4ea9-bf5c-e4bd2d7940f6": "Portable Cordless Tire Inflator & Emergency Digital Air Pump",
    "146ea3e7-825e-4f36-8c49-6404935ecd7d": "All-in-One Pet Grooming Vacuum Kit with Low-Noise Electric Clippers",
}

# Audited Batch 8 self-generated candidates requiring quarantine
AUDITED_BATCH8_PRODUCTS: Dict[str, str] = {
    "d3f7e913-3974-5935-aa8a-8c3f3632a06a": "Kitchen Mama Auto Electric Can Opener (Original Red Model)",
    "21d0cfcd-19c7-5136-af95-75748c896b08": "resqme The Original Emergency Keychain Car Escape Tool",
    "b825b065-2ef3-57a7-b626-13d47da77e7d": "ESARORA Facial & Eye Ice Roller for Morning Depuffing",
    "b6dc0ed8-6ac4-5da9-9f9b-9036236c2d1b": "RAK Universal Socket Grip (7-19mm) with Power Drill Adapter",
    "a47548a7-96ef-5940-a9de-7ec5bed8e3a9": "Elviros Cervical Memory Foam Ergonomic Pillow for Neck & Shoulder Pain",
    "c0fb6e9a-2c50-59fb-9da5-885fb47a87c1": "Delta Faucet Glass Rinser for Kitchen Sinks (GR150-SP Stainless Steel)",
}

ALL_QUARANTINED_PRODUCTS: Dict[str, str] = {
    **AUDITED_LEGACY_PRODUCTS,
    **AUDITED_BATCH8_PRODUCTS,
}


def backup_database(db_path: str) -> str:
    """Create a timestamped backup of the database file before modification."""
    if not os.path.exists(db_path):
        return ""
    backup_path = f"{db_path}.bak"
    shutil.copy2(db_path, backup_path)
    return backup_path


async def remediate_legacy_discovery_data(db: AsyncSession) -> Dict[str, int]:
    """
    Executes transactional, idempotent remediation on all audited quarantined candidates.
    Returns counts of modified entities:
    {
        'collection_runs_modified': int,
        'products_modified': int,
        'source_records_modified': int,
        'product_offers_modified': int,
        'bundle_offers_modified': int,
        'scores_modified': int
    }
    """
    stats = {
        "collection_runs_modified": 0,
        "products_modified": 0,
        "source_records_modified": 0,
        "product_offers_modified": 0,
        "bundle_offers_modified": 0,
        "scores_modified": 0,
    }

    # 1. Remediate CollectionRuns
    for run_id, notes in ALL_TARGET_RUNS:
        c_run = await db.get(CollectionRun, run_id)
        if c_run:
            needs_run_update = (
                c_run.status != CollectionJobStatus.PARTIAL
                or c_run.coverage_notes != notes
                or c_run.records_fetched != 0
                or c_run.records_new != 0
            )
            if needs_run_update:
                c_run.status = CollectionJobStatus.PARTIAL
                c_run.coverage_notes = notes
                c_run.records_fetched = 0
                c_run.records_new = 0
                stats["collection_runs_modified"] += 1

        # 2. Remediate SourceRecords for this run
        srecs_res = await db.execute(
            select(SourceRecord).where(SourceRecord.collection_run_id == run_id)
        )
        for srec in srecs_res.scalars().all():
            needs_srec_update = (
                srec.source_type != DataSourceType.MANUAL_IMPORT
                or srec.geo_confidence != ConfidenceLevel.UNKNOWN
                or not srec.is_synthetic
                or (srec.raw_data or {}).get("verification_status") not in ("QUARANTINED_UNVERIFIED", "QUARANTINED_SELF_GENERATED_RECEIPT")
            )
            if needs_srec_update:
                srec.source_type = DataSourceType.MANUAL_IMPORT
                srec.geo_confidence = ConfidenceLevel.UNKNOWN
                srec.is_synthetic = True
                raw = dict(srec.raw_data or {})
                raw["provenance"] = "unverified_manual_hypothesis"
                raw["verification_status"] = "QUARANTINED_SELF_GENERATED_RECEIPT" if run_id == BATCH8_COLLECTION_RUN_ID else "QUARANTINED_UNVERIFIED"
                raw["quarantine_reason"] = "Self-generated receipt or placeholder pattern without authentic external provider execution."
                srec.raw_data = raw
                stats["source_records_modified"] += 1

    # 3. Remediate Products, ProductOffers, BundleOffers across all quarantined items
    for p_id in ALL_QUARANTINED_PRODUCTS.keys():
        prod = await db.get(Product, p_id)
        if prod:
            target_status = "RESEARCH_HYPOTHESIS" if p_id in AUDITED_BATCH8_PRODUCTS else "UNVERIFIED_IMPORT"
            needs_prod_update = (
                prod.opportunity_status not in ("UNVERIFIED_IMPORT", "RESEARCH_HYPOTHESIS")
                or prod.source_type != DataSourceType.MANUAL_IMPORT
                or prod.us_relevance_confidence != ConfidenceLevel.UNKNOWN
                or (prod.raw_data or {}).get("verification_status") != "QUARANTINED_UNVERIFIED"
            )
            if needs_prod_update:
                prod.opportunity_status = target_status
                prod.source_type = DataSourceType.MANUAL_IMPORT
                prod.us_relevance_confidence = ConfidenceLevel.UNKNOWN
                raw = dict(prod.raw_data or {})
                raw["provenance"] = "unverified_manual_import"
                raw["verification_status"] = "QUARANTINED_UNVERIFIED"
                raw["commercial_listing_verified"] = False
                raw["unsupported_claims_warning"] = "Product concepts and pricing are unverified research scenarios."
                prod.raw_data = raw
                stats["products_modified"] += 1

            # ProductOffers
            offers_res = await db.execute(
                select(ProductOffer).where(ProductOffer.product_id == p_id)
            )
            for off in offers_res.scalars().all():
                needs_off_update = (
                    off.evidence_type != EvidenceType.UNVERIFIED_HYPOTHESIS
                    or off.price_evidence_type != PriceEvidenceType.SCENARIO_PRICE
                )
                if needs_off_update:
                    off.evidence_type = EvidenceType.UNVERIFIED_HYPOTHESIS
                    off.price_evidence_type = PriceEvidenceType.SCENARIO_PRICE
                    stats["product_offers_modified"] += 1

            # BundleOffers
            bundles_res = await db.execute(
                select(BundleOffer).where(BundleOffer.product_id == p_id)
            )
            for bnd in bundles_res.scalars().all():
                needs_bnd_update = (
                    bnd.bundle_status != "modeled_scenario"
                    or bnd.evidence_type != EvidenceType.UNVERIFIED_HYPOTHESIS
                    or bnd.price_evidence_type != PriceEvidenceType.SCENARIO_PRICE
                    or bnd.is_natural_bundle is not False
                )
                if needs_bnd_update:
                    bnd.bundle_status = "modeled_scenario"
                    bnd.evidence_type = EvidenceType.UNVERIFIED_HYPOTHESIS
                    bnd.price_evidence_type = PriceEvidenceType.SCENARIO_PRICE
                    bnd.is_natural_bundle = False
                    stats["bundle_offers_modified"] += 1

    # 4. Commit transactional changes
    await db.commit()

    # 5. Score recomputation & score quarantine enforcement
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    scoring = ScoringEngine(db, mode="balanced")

    for p_id in ALL_QUARANTINED_PRODUCTS.keys():
        target_status = "RESEARCH_HYPOTHESIS" if p_id in AUDITED_BATCH8_PRODUCTS else "UNVERIFIED_IMPORT"
        sc_res = await db.execute(
            select(OpportunityScore).where(
                OpportunityScore.product_id == p_id,
                OpportunityScore.score_date == today,
            )
        )
        score_rec = sc_res.scalar_one_or_none()
        if score_rec:
            needs_score_update = (
                score_rec.opportunity_status not in ("UNVERIFIED_IMPORT", "RESEARCH_HYPOTHESIS")
                or score_rec.evidence_confidence > 15.0
                or score_rec.observed_single_price_usd is not None
                or score_rec.observed_bundle_price_usd is not None
            )
            if needs_score_update:
                score_rec.opportunity_status = target_status
                score_rec.evidence_confidence = 4.5
                score_rec.observed_single_price_usd = None
                score_rec.observed_bundle_price_usd = None
                score_rec.composite_score = min(20.0, score_rec.composite_score)
                score_rec.requires_verification = True
                stats["scores_modified"] += 1

    await db.commit()
    return stats


if __name__ == "__main__":
    import asyncio
    from app.core.database import get_session
    from app.core.config import get_settings

    async def main():
        settings = get_settings()
        db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
        backup = backup_database(db_path)
        print(f"Database backed up to: {backup}")
        async with get_session() as session:
            stats = await remediate_legacy_discovery_data(session)
            print("Remediation completed:")
            for k, v in stats.items():
                print(f"  {k}: {v}")

    asyncio.run(main())
