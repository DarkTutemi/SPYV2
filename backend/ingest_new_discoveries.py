"""
US WIN HUNTER — Ingestion & Commercial Validation of US Products
Enforces strict provenance validation:
- Rejects unverified, placeholder or synthetic URLs from being labeled as OBSERVED_RETAIL_LISTING_PRICE.
- Manually imported hypotheses are classified as UNVERIFIED_IMPORT / RESEARCH_HYPOTHESIS with SCENARIO_PRICE.
- CollectionRuns for manual imports are marked PARTIAL, never COMPLETED provider runs.
- SourceRecords preserve synthetic/manual flag and UNKNOWN geo confidence.
"""

import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select
from app.core.database import async_session_factory
from app.models.models import (
    BundleMechanism,
    ConfidenceLevel,
    DataSource,
    DataSourceType,
    CollectionJob,
    CollectionRun,
    CollectionJobStatus,
    PriceEvidenceType,
    EvidenceType,
    Product,
    ProductOffer,
    BundleOffer,
    SourceRecord,
    Advertiser,
    OpportunityScore,
    _uuid,
    _utcnow,
)
from app.engines.scoring import ScoringEngine


def validate_commercial_evidence(url: str, price_evidence_type: str) -> str:
    """
    Acceptance Gate: Reject unverified, placeholder or synthetic URLs
    from being labeled as OBSERVED_RETAIL_LISTING_PRICE or OBSERVED_CHECKOUT_PRICE.
    """
    placeholder_patterns = ["XYZ", "123456", "987654321", "placeholder", "demo"]
    is_placeholder = any(pat.lower() in url.lower() for pat in placeholder_patterns)

    if is_placeholder and price_evidence_type in (
        PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
        PriceEvidenceType.OBSERVED_CHECKOUT_PRICE.value,
        "OBSERVED_RETAIL_LISTING_PRICE",
        "OBSERVED_CHECKOUT_PRICE",
    ):
        raise ValueError(
            f"REJECTED: URL '{url}' contains unverified placeholder pattern and cannot be labeled "
            f"as '{price_evidence_type}'. Must use SCENARIO_PRICE or UNKNOWN."
        )
    return price_evidence_type


# Initial research queue of 6 physical product concepts.
# Strictly labeled as UNVERIFIED_IMPORT / SCENARIO_PRICE until authentic external verification.
NEW_PRODUCTS_DATA = [
    {
        "name": "42kHz Ultrasonic Retainer & Mouthguard Cleaning Pod",
        "category": "Personal Care & Dental Hygiene",
        "description": "High-frequency 42kHz ultrasonic cavitation pod for deep cleaning orthodontic retainers, Invisalign aligners, night guards, and dentures without abrasive scratching.",
        "functional_use_case": "Removes plaque, white tartar buildup, and odor from dental appliances in a 5-minute automated cycle.",
        "customer_pain": "Invisalign and mouthguard wearers struggle with cloudy plastic, foul odors, and manual brushing creating micro-abrasions.",
        "source_url": "https://www.amazon.com/dp/B0C9QWXYZ1",
        "min_price_usd": 39.99,
        "max_price_usd": 69.99,
        "primary_bundle_qty": 2,
        "commercial_model": "MODEL_B_NATURAL_BUNDLE",
        "source_type": DataSourceType.MANUAL_IMPORT,
        "opportunity_status": "UNVERIFIED_IMPORT",
        "us_relevance_confidence": ConfidenceLevel.UNKNOWN,
        "offers": [
            {
                "source_url": "https://www.amazon.com/dp/B0C9QWXYZ1",
                "price_usd": 39.99,
                "compare_at_price_usd": 59.99,
                "price_evidence_type": PriceEvidenceType.SCENARIO_PRICE.value,
                "evidence_type": EvidenceType.UNVERIFIED_HYPOTHESIS,
                "quantity": 1,
                "is_bundle": False,
            },
            {
                "source_url": "https://www.walmart.com/ip/ultrasonic-dental-cleaner/184920491",
                "price_usd": 36.50,
                "compare_at_price_usd": 49.99,
                "price_evidence_type": PriceEvidenceType.SCENARIO_PRICE.value,
                "evidence_type": EvidenceType.UNVERIFIED_HYPOTHESIS,
                "quantity": 1,
                "is_bundle": False,
            }
        ],
        "bundles": [
            {
                "source_url": "https://www.amazon.com/dp/B0C9QWXYZ1",
                "quantity": 2,
                "bundle_price_usd": 64.99,
                "unit_price_usd": 32.495,
                "discount_claim": "Modeled Starter Pod + 120-Day Tablet Refill Scenario",
                "estimated_order_value_usd": 64.99,
                "bundle_mechanism": BundleMechanism.CONSUMABLE_REPLENISHMENT,
                "mechanism_evidence": "Orthodontic retainers require ongoing cleansing tablets; high theoretical replenishment demand.",
                "bundle_status": "modeled_scenario",
                "is_natural_bundle": False,
                "natural_bundle_reasoning": "Hypothetical scenario: Pod paired with cleansing tablets.",
                "price_evidence_type": PriceEvidenceType.SCENARIO_PRICE.value,
                "evidence_type": EvidenceType.UNVERIFIED_HYPOTHESIS,
            }
        ],
        "raw_data": {
            "physical_product_concept": "42kHz Ultrasonic Retainer Cleaning Pod",
            "commercial_listing_verified": False,
            "estimated_supplier_cost": 11.50,
            "modeled_bundle_offer": "Starter Pod + 120-Day Tablet Refills ($64.99)",
            "hypothetical_customer_pain": "Cloudy retainers and manual brushing damage",
            "unsupported_claims_warning": "Sales volume and ranking claims unverified without external provider feed.",
            "shipping_risk": "Low (compact pod, 380g, no hazardous liquids).",
            "compliance_risk": "Requires FCC/CE USB-C power certification.",
        }
    },
    {
        "name": "Cordless Electric Spin Scrubber with Telescopic Extension Pole",
        "category": "Home & Deep Cleaning",
        "description": "Rechargeable high-torque electric bathroom and floor scrubber with 8 interchangeable brush heads and an adjustable 54-inch extension handle.",
        "functional_use_case": "Deep cleans bathroom shower tiles, grout lines, bathtubs, sinks, and car wheels without bending or manual scrubbing.",
        "customer_pain": "Back and knee pain from kneeling on cold tile floors to scrub soap scum and mildew.",
        "source_url": "https://www.amazon.com/dp/B0BXYZ7890",
        "min_price_usd": 44.99,
        "max_price_usd": 69.99,
        "primary_bundle_qty": 1,
        "commercial_model": "MODEL_A_STANDALONE",
        "source_type": DataSourceType.MANUAL_IMPORT,
        "opportunity_status": "UNVERIFIED_IMPORT",
        "us_relevance_confidence": ConfidenceLevel.UNKNOWN,
        "offers": [
            {
                "source_url": "https://www.amazon.com/dp/B0BXYZ7890",
                "price_usd": 44.99,
                "compare_at_price_usd": 69.99,
                "price_evidence_type": PriceEvidenceType.SCENARIO_PRICE.value,
                "evidence_type": EvidenceType.UNVERIFIED_HYPOTHESIS,
                "quantity": 1,
                "is_bundle": False,
            },
            {
                "source_url": "https://www.walmart.com/ip/electric-spin-scrubber-cordless/592810482",
                "price_usd": 42.00,
                "compare_at_price_usd": 59.99,
                "price_evidence_type": PriceEvidenceType.SCENARIO_PRICE.value,
                "evidence_type": EvidenceType.UNVERIFIED_HYPOTHESIS,
                "quantity": 1,
                "is_bundle": False,
            }
        ],
        "bundles": [
            {
                "source_url": "https://www.amazon.com/dp/B0BXYZ7890",
                "quantity": 2,
                "bundle_price_usd": 79.99,
                "unit_price_usd": 39.995,
                "discount_claim": "Modeled Multi-Floor Accessory Pack Scenario",
                "estimated_order_value_usd": 79.99,
                "bundle_mechanism": BundleMechanism.MULTIPLE_LOCATIONS,
                "mechanism_evidence": "Multi-floor homes require separate brush heads for hygiene.",
                "bundle_status": "modeled_scenario",
                "is_natural_bundle": False,
                "natural_bundle_reasoning": "Hypothetical scenario: Upstairs master bath + downstairs guest bath.",
                "price_evidence_type": PriceEvidenceType.SCENARIO_PRICE.value,
                "evidence_type": EvidenceType.UNVERIFIED_HYPOTHESIS,
            }
        ],
        "raw_data": {
            "physical_product_concept": "Cordless Electric Spin Scrubber",
            "commercial_listing_verified": False,
            "estimated_supplier_cost": 14.80,
            "modeled_bundle_offer": "Scrubber + Extra Head Pack ($79.99)",
            "hypothetical_customer_pain": "Knee and back pain during bathtub scrubbing",
            "unsupported_claims_warning": "Sales volume and ranking claims unverified without external provider feed.",
            "shipping_risk": "Requires sturdy packaging to prevent bent telescopic tubes.",
            "compliance_risk": "UN38.3 battery certification required.",
        }
    },
    {
        "name": "High-Pressure Kitchen Sink Glass Rinser (304 Stainless Steel)",
        "category": "Kitchen & Dining / DIY",
        "description": "Five-nozzle high-pressure mechanical cup and glass washer installed into standard countertop soap dispenser holes.",
        "functional_use_case": "Quickly rinses baby bottles, wine glasses, coffee mugs, and protein shakers in seconds.",
        "customer_pain": "Hand-washing tall narrow bottles and wine glasses is awkward and leaves residue.",
        "source_url": "https://www.amazon.com/dp/B09XYZ4321",
        "min_price_usd": 27.99,
        "max_price_usd": 49.99,
        "primary_bundle_qty": 1,
        "commercial_model": "MODEL_A_STANDALONE",
        "source_type": DataSourceType.MANUAL_IMPORT,
        "opportunity_status": "UNVERIFIED_IMPORT",
        "us_relevance_confidence": ConfidenceLevel.UNKNOWN,
        "offers": [
            {
                "source_url": "https://www.amazon.com/dp/B09XYZ4321",
                "price_usd": 27.99,
                "compare_at_price_usd": 42.00,
                "price_evidence_type": PriceEvidenceType.SCENARIO_PRICE.value,
                "evidence_type": EvidenceType.UNVERIFIED_HYPOTHESIS,
                "quantity": 1,
                "is_bundle": False,
            },
            {
                "source_url": "https://www.homedepot.com/p/delta-glass-rinser-gr150",
                "price_usd": 89.00,
                "compare_at_price_usd": 105.00,
                "price_evidence_type": PriceEvidenceType.SCENARIO_PRICE.value,
                "evidence_type": EvidenceType.UNVERIFIED_HYPOTHESIS,
                "quantity": 1,
                "is_bundle": False,
            }
        ],
        "bundles": [
            {
                "source_url": "https://www.amazon.com/dp/B09XYZ4321",
                "quantity": 2,
                "bundle_price_usd": 48.99,
                "unit_price_usd": 24.495,
                "discount_claim": "Modeled 2-Pack Kitchen + Wet Bar Scenario",
                "estimated_order_value_usd": 48.99,
                "bundle_mechanism": BundleMechanism.MULTIPLE_LOCATIONS,
                "mechanism_evidence": "Secondary sinks in home bars or outdoor kitchens.",
                "bundle_status": "modeled_scenario",
                "is_natural_bundle": False,
                "natural_bundle_reasoning": "Hypothetical scenario: Kitchen sink + basement wet bar.",
                "price_evidence_type": PriceEvidenceType.SCENARIO_PRICE.value,
                "evidence_type": EvidenceType.UNVERIFIED_HYPOTHESIS,
            }
        ],
        "raw_data": {
            "physical_product_concept": "High-Pressure Kitchen Sink Glass Rinser",
            "commercial_listing_verified": False,
            "estimated_supplier_cost": 6.20,
            "modeled_bundle_offer": "Kitchen + Wet Bar 2-Pack ($48.99)",
            "hypothetical_customer_pain": "Difficult bottle and shaker cleaning",
            "unsupported_claims_warning": "Sales volume and ranking claims unverified without external provider feed.",
            "shipping_risk": "Extremely low (solid metal, non-fragile).",
            "compliance_risk": "Standard 9/16\" US plumbing tee fitting required.",
        }
    },
    {
        "name": "Dual-Chip Red Light & Near-Infrared Therapy Lumbar Belt",
        "category": "Health & Wellness",
        "description": "Flexible wearable light therapy belt emitting dual medical-grade wavelengths (660nm visible red light + 850nm near-infrared light).",
        "functional_use_case": "Relieves lower back stiffness, sciatica pain, and muscle fatigue via deep cellular photobiomodulation.",
        "customer_pain": "Chronic lower back ache and sciatica stiffness without expensive chiropractic visits.",
        "source_url": "https://www.amazon.com/dp/B0D1XYZ567",
        "min_price_usd": 89.99,
        "max_price_usd": 149.99,
        "primary_bundle_qty": 1,
        "commercial_model": "MODEL_A_STANDALONE",
        "source_type": DataSourceType.MANUAL_IMPORT,
        "opportunity_status": "UNVERIFIED_IMPORT",
        "us_relevance_confidence": ConfidenceLevel.UNKNOWN,
        "offers": [
            {
                "source_url": "https://www.amazon.com/dp/B0D1XYZ567",
                "price_usd": 89.99,
                "compare_at_price_usd": 139.99,
                "price_evidence_type": PriceEvidenceType.SCENARIO_PRICE.value,
                "evidence_type": EvidenceType.UNVERIFIED_HYPOTHESIS,
                "quantity": 1,
                "is_bundle": False,
            },
            {
                "source_url": "https://lifeprofitness.com/products/alleva-red-light-belt",
                "price_usd": 149.99,
                "compare_at_price_usd": 199.99,
                "price_evidence_type": PriceEvidenceType.SCENARIO_PRICE.value,
                "evidence_type": EvidenceType.UNVERIFIED_HYPOTHESIS,
                "quantity": 1,
                "is_bundle": False,
            }
        ],
        "bundles": [
            {
                "source_url": "https://www.amazon.com/dp/B0D1XYZ567",
                "quantity": 2,
                "bundle_price_usd": 119.99,
                "unit_price_usd": 59.995,
                "discount_claim": "Modeled Belt + 10,000mAh Battery Pack Scenario",
                "estimated_order_value_usd": 119.99,
                "bundle_mechanism": BundleMechanism.COMPLETE_COVERAGE,
                "mechanism_evidence": "Portable wireless therapy while walking or working.",
                "bundle_status": "modeled_scenario",
                "is_natural_bundle": False,
                "natural_bundle_reasoning": "Hypothetical scenario: Belt + portable battery pack.",
                "price_evidence_type": PriceEvidenceType.SCENARIO_PRICE.value,
                "evidence_type": EvidenceType.UNVERIFIED_HYPOTHESIS,
            }
        ],
        "raw_data": {
            "physical_product_concept": "Dual-Chip Red Light Lumbar Belt",
            "commercial_listing_verified": False,
            "estimated_supplier_cost": 24.50,
            "modeled_bundle_offer": "Belt + Battery Pack ($119.99)",
            "hypothetical_customer_pain": "Chronic lumbar stiffness and sciatic ache",
            "unsupported_claims_warning": "Medical outcomes and revenue unverified without clinical and marketplace proof.",
            "shipping_risk": "Moderate (flexible electronics, ~850g).",
            "compliance_risk": "FDA general wellness exemption required; do not claim medical cures.",
        }
    },
    {
        "name": "Portable Cordless Tire Inflator & Emergency Digital Air Pump",
        "category": "Automotive & Outdoor Utility",
        "description": "Handheld 150 PSI cordless air compressor with digital auto-shutoff pressure gauge and emergency LED light.",
        "functional_use_case": "Inflates car tires, bicycle tires, sports balls, and motorcycles with precision auto-stop.",
        "customer_pain": "Low tire pressure warning on cold mornings; broken gas station air pumps.",
        "source_url": "https://www.amazon.com/dp/B0A1XYZ999",
        "min_price_usd": 39.99,
        "max_price_usd": 59.99,
        "primary_bundle_qty": 1,
        "commercial_model": "MODEL_A_STANDALONE",
        "source_type": DataSourceType.MANUAL_IMPORT,
        "opportunity_status": "UNVERIFIED_IMPORT",
        "us_relevance_confidence": ConfidenceLevel.UNKNOWN,
        "offers": [
            {
                "source_url": "https://www.amazon.com/dp/B0A1XYZ999",
                "price_usd": 39.99,
                "compare_at_price_usd": 59.99,
                "price_evidence_type": PriceEvidenceType.SCENARIO_PRICE.value,
                "evidence_type": EvidenceType.UNVERIFIED_HYPOTHESIS,
                "quantity": 1,
                "is_bundle": False,
            },
            {
                "source_url": "https://www.walmart.com/ip/cordless-air-compressor-tire-pump/981240182",
                "price_usd": 36.99,
                "compare_at_price_usd": 49.99,
                "price_evidence_type": PriceEvidenceType.SCENARIO_PRICE.value,
                "evidence_type": EvidenceType.UNVERIFIED_HYPOTHESIS,
                "quantity": 1,
                "is_bundle": False,
            }
        ],
        "bundles": [
            {
                "source_url": "https://www.amazon.com/dp/B0A1XYZ999",
                "quantity": 2,
                "bundle_price_usd": 69.99,
                "unit_price_usd": 34.995,
                "discount_claim": "Modeled Two-Car Household Emergency Pack Scenario",
                "estimated_order_value_usd": 69.99,
                "bundle_mechanism": BundleMechanism.MULTI_PERSON_HOUSEHOLD,
                "mechanism_evidence": "Multi-car families keep one inflator in each vehicle.",
                "bundle_status": "modeled_scenario",
                "is_natural_bundle": False,
                "natural_bundle_reasoning": "Hypothetical scenario: His & Hers vehicle emergency pack.",
                "price_evidence_type": PriceEvidenceType.SCENARIO_PRICE.value,
                "evidence_type": EvidenceType.UNVERIFIED_HYPOTHESIS,
            }
        ],
        "raw_data": {
            "physical_product_concept": "Portable Cordless Tire Inflator",
            "commercial_listing_verified": False,
            "estimated_supplier_cost": 11.80,
            "modeled_bundle_offer": "2-Car Emergency Pack ($69.99)",
            "hypothetical_customer_pain": "Cold morning tire pressure drops",
            "unsupported_claims_warning": "Sales volume and ranking claims unverified without external provider feed.",
            "shipping_risk": "Low (compact, ~580g).",
            "compliance_risk": "UN38.3 lithium battery certification required.",
        }
    },
    {
        "name": "All-in-One Pet Grooming Vacuum Kit with Low-Noise Electric Clippers",
        "category": "Pet Care & Supplies",
        "description": "Low-noise (<60dB) pet grooming station that grooms, de-sheds, and trims dog/cat coats while vacuuming fur into a sealed 2L canister.",
        "functional_use_case": "Eliminates pet hair mess and flying dander while trimming and brushing dogs and cats at home.",
        "customer_pain": "Flying pet dander on furniture and high salon grooming fees.",
        "source_url": "https://www.amazon.com/dp/B0P1XYZ111",
        "min_price_usd": 79.99,
        "max_price_usd": 119.99,
        "primary_bundle_qty": 1,
        "commercial_model": "MODEL_A_STANDALONE",
        "source_type": DataSourceType.MANUAL_IMPORT,
        "opportunity_status": "UNVERIFIED_IMPORT",
        "us_relevance_confidence": ConfidenceLevel.UNKNOWN,
        "offers": [
            {
                "source_url": "https://www.amazon.com/dp/B0P1XYZ111",
                "price_usd": 79.99,
                "compare_at_price_usd": 129.99,
                "price_evidence_type": PriceEvidenceType.SCENARIO_PRICE.value,
                "evidence_type": EvidenceType.UNVERIFIED_HYPOTHESIS,
                "quantity": 1,
                "is_bundle": False,
            },
            {
                "source_url": "https://www.walmart.com/ip/pet-grooming-vacuum-kit/391024819",
                "price_usd": 74.99,
                "compare_at_price_usd": 109.99,
                "price_evidence_type": PriceEvidenceType.SCENARIO_PRICE.value,
                "evidence_type": EvidenceType.UNVERIFIED_HYPOTHESIS,
                "quantity": 1,
                "is_bundle": False,
            }
        ],
        "bundles": [
            {
                "source_url": "https://www.amazon.com/dp/B0P1XYZ111",
                "quantity": 2,
                "bundle_price_usd": 104.99,
                "unit_price_usd": 52.495,
                "discount_claim": "Modeled Vacuum + Extra Blade Replacement Scenario",
                "estimated_order_value_usd": 104.99,
                "bundle_mechanism": BundleMechanism.CONSUMABLE_REPLENISHMENT,
                "mechanism_evidence": "Ceramic clipper blades wear out and need periodic replacement.",
                "bundle_status": "modeled_scenario",
                "is_natural_bundle": False,
                "natural_bundle_reasoning": "Hypothetical scenario: Vacuum + replacement clipper blade pack.",
                "price_evidence_type": PriceEvidenceType.SCENARIO_PRICE.value,
                "evidence_type": EvidenceType.UNVERIFIED_HYPOTHESIS,
            }
        ],
        "raw_data": {
            "physical_product_concept": "All-in-One Pet Grooming Vacuum Kit",
            "commercial_listing_verified": False,
            "estimated_supplier_cost": 23.50,
            "modeled_bundle_offer": "Vacuum + Replacement Blade Kit ($104.99)",
            "hypothetical_customer_pain": "Flying pet fur and costly pet grooming bills",
            "unsupported_claims_warning": "Sales volume and ranking claims unverified without external provider feed.",
            "shipping_risk": "Moderate (bulkier unit, volumetric box ~2.8kg).",
            "compliance_risk": "UL/ETL motor electrical safety testing required.",
        }
    }
]


async def ingest_new_products():
    """
    Ingests research hypothesis products with strict provenance validation.
    Enforces idempotency and ensures hypothetical prices are never marked as observed.
    """
    print(f"Ingesting {len(NEW_PRODUCTS_DATA)} research hypothesis products with strict provenance...")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    async with async_session_factory() as db:
        # Validate all offer price evidence types against placeholder URLs
        for p in NEW_PRODUCTS_DATA:
            for off in p["offers"]:
                validate_commercial_evidence(off["source_url"], off["price_evidence_type"])
            for bnd in p.get("bundles", []):
                validate_commercial_evidence(bnd["source_url"], bnd["price_evidence_type"])

        # Fetch existing products
        existing_res = await db.execute(select(Product))
        existing_products = {p.name: p for p in existing_res.scalars().all()}

        # Verify or create DataSource for MANUAL_IMPORT
        ds_res = await db.execute(
            select(DataSource).where(DataSource.source_type == DataSourceType.MANUAL_IMPORT)
        )
        data_source = ds_res.scalar_one_or_none()
        if not data_source:
            data_source = DataSource(
                id=_uuid(),
                name="manual_import_registry",
                source_type=DataSourceType.MANUAL_IMPORT,
                is_active=True,
                geographic_coverage="US",
                notes="Manual research import registry for unverified product hypotheses.",
            )
            db.add(data_source)
            await db.flush()

        # CollectionJob
        cj_res = await db.execute(
            select(CollectionJob).where(CollectionJob.name == "us_product_discovery_manual")
        )
        c_job = cj_res.scalar_one_or_none()
        if not c_job:
            c_job = CollectionJob(
                id=_uuid(),
                data_source_id=data_source.id,
                name="us_product_discovery_manual",
                job_type="research_hypothesis_import",
                is_recurring=False,
                is_active=True,
            )
            db.add(c_job)
            await db.flush()

        # CollectionRun marked PARTIAL (manual hypothesis import, not a successful external provider run)
        c_run_id = "run_us_discovery_20261111"
        c_run = await db.get(CollectionRun, c_run_id)
        if not c_run:
            c_run = CollectionRun(
                id=c_run_id,
                job_id=c_job.id,
                status=CollectionJobStatus.PARTIAL,
                records_fetched=0,
                records_new=0,
                records_updated=0,
                records_duplicate=0,
                coverage_notes="QUARANTINED: Manual research hypothesis import without verified external provider collection.",
                started_at=_utcnow(),
                completed_at=_utcnow(),
            )
            db.add(c_run)
            await db.flush()
        else:
            c_run.status = CollectionJobStatus.PARTIAL
            c_run.coverage_notes = "QUARANTINED: Manual research hypothesis import without verified external provider collection."

        # Advertiser
        adv_res = await db.execute(
            select(Advertiser).where(Advertiser.normalized_name == "unverified_research_marketplaces")
        )
        adv = adv_res.scalar_one_or_none()
        if not adv:
            adv = Advertiser(
                id=_uuid(),
                name="Unverified Research Marketplaces",
                normalized_name="unverified_research_marketplaces",
                source_type=DataSourceType.MANUAL_IMPORT,
                country="US",
                is_verified=False,
            )
            db.add(adv)
            await db.flush()

        # Ingest or update each product
        for i, p_data in enumerate(NEW_PRODUCTS_DATA):
            p_name = p_data["name"]
            prod = existing_products.get(p_name)

            if prod:
                # Update existing product with quarantined unverified classification
                prod.opportunity_status = "UNVERIFIED_IMPORT"
                prod.source_type = DataSourceType.MANUAL_IMPORT
                prod.us_relevance_confidence = ConfidenceLevel.UNKNOWN
                raw = dict(prod.raw_data or {})
                raw.update(p_data["raw_data"])
                raw["provenance"] = "unverified_manual_import"
                raw["verification_status"] = "QUARANTINED_UNVERIFIED"
                prod.raw_data = raw
            else:
                prod = Product(
                    id=_uuid(),
                    name=p_name,
                    normalized_name=p_name.lower().strip(),
                    description=p_data["description"],
                    category=p_data["category"],
                    source_url=p_data["source_url"],
                    min_price_usd=p_data["min_price_usd"],
                    max_price_usd=p_data["max_price_usd"],
                    target_country="US",
                    us_relevance_confidence=ConfidenceLevel.UNKNOWN,
                    is_physical=True,
                    is_synthetic=False,
                    opportunity_status="UNVERIFIED_IMPORT",
                    functional_use_case=p_data["functional_use_case"],
                    customer_pain=p_data["customer_pain"],
                    primary_bundle_qty=p_data["primary_bundle_qty"],
                    source_type=DataSourceType.MANUAL_IMPORT,
                    external_id=f"discovery_{abs(hash(p_name)) % 100000000:08x}",
                    raw_data=p_data["raw_data"],
                    first_seen_at=_utcnow(),
                    last_seen_at=_utcnow(),
                )
                db.add(prod)
                await db.flush()

                # SourceRecord
                srec = SourceRecord(
                    id=_uuid(),
                    collection_run_id=c_run.id,
                    source_type=DataSourceType.MANUAL_IMPORT,
                    external_id=prod.external_id,
                    geographic_context="United States",
                    geo_confidence=ConfidenceLevel.UNKNOWN,
                    is_synthetic=True,
                    raw_data={
                        "title": p_name,
                        "provenance": "unverified_manual_hypothesis",
                        "verification_status": "QUARANTINED_UNVERIFIED",
                        "quarantine_reason": "Retail URLs contain placeholder patterns; no verified external marketplace data.",
                    },
                )
                db.add(srec)

                # Offers
                for off in p_data["offers"]:
                    po = ProductOffer(
                        id=_uuid(),
                        product_id=prod.id,
                        advertiser_id=adv.id,
                        source_url=off["source_url"],
                        price_usd=off["price_usd"],
                        compare_at_price_usd=off.get("compare_at_price_usd"),
                        currency="USD",
                        quantity=off.get("quantity", 1),
                        is_bundle=off.get("is_bundle", False),
                        observed_at=_utcnow(),
                        evidence_type=off["evidence_type"],
                        price_evidence_type=off["price_evidence_type"],
                    )
                    db.add(po)

                # Bundles
                for bnd in p_data.get("bundles", []):
                    bo = BundleOffer(
                        id=_uuid(),
                        product_id=prod.id,
                        advertiser_id=adv.id,
                        source_url=bnd["source_url"],
                        quantity=bnd["quantity"],
                        bundle_price_usd=bnd["bundle_price_usd"],
                        unit_price_usd=bnd["unit_price_usd"],
                        discount_claim=bnd.get("discount_claim"),
                        estimated_order_value_usd=bnd.get("estimated_order_value_usd"),
                        bundle_mechanism=bnd["bundle_mechanism"],
                        mechanism_evidence=bnd["mechanism_evidence"],
                        bundle_status=bnd.get("bundle_status", "modeled_scenario"),
                        is_natural_bundle=bnd.get("is_natural_bundle", False),
                        natural_bundle_reasoning=bnd.get("natural_bundle_reasoning"),
                        observed_at=_utcnow(),
                        evidence_type=bnd["evidence_type"],
                        price_evidence_type=bnd["price_evidence_type"],
                    )
                    db.add(bo)

        await db.commit()
        print("Idempotent ingestion finished.")

        # Recompute balanced scores
        print("Recomputing balanced scores with provenance guardrails...")
        scoring = ScoringEngine(db, mode="balanced")
        scores = await scoring.score_all_products(score_date=today, mode="balanced")
        await db.commit()
        print(f"Scoring completed. Re-scored {len(scores)} products total.")


if __name__ == "__main__":
    asyncio.run(ingest_new_products())
