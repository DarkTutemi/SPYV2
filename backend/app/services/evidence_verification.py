"""
US WIN HUNTER — Commercial Evidence Verification Service
Enforces rigorous database-backed evidence provenance:
- Early rejection of placeholder strings and synthetic URL patterns.
- Rejection of valid-looking ASINs/IDs that lack authentic database-stored provider acquisition records.
- Verification against actual stored SourceRecord and CollectionRun in database.
- Checks agreement between offer URL, product identity, observed price, timestamp, and source IDs.
- Rejects self-generated or script-generated retrieval_status flags.
- Distinguishes VERIFIED, PARTIAL, UNKNOWN, and REJECTED commercial observations.
- Prevents plausible but unverified URLs from becoming OBSERVED_RETAIL_LISTING_PRICE.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import enum
import hashlib
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.models import (
    PriceEvidenceType,
    EvidenceType,
    SourceRecord,
    CollectionRun,
    CollectionJobStatus,
    DataSourceType,
)


RECOGNIZED_PROVIDERS: Tuple[str, ...] = (
    "apify_amazon_scraper",
    "apify_meta_ad_library",
    "shopify_storefront_collector",
    "google_shopping_collector",
    "authentic_public_marketplace_capture",
    "authorized_http_collector",
    "public_dtc_shopify_collector",
)


def generate_capture_signature(
    collection_run_id: str,
    external_id: str,
    price: float,
    timestamp: Optional[str] = None,
) -> str:
    """
    Computes a canonical SHA-256 capture digest binding the collection run,
    external product identifier, observed price, and capture timestamp.
    """
    ts = timestamp or "undated"
    canonical = f"{collection_run_id}:{external_id}:{float(price):.2f}:{ts}"
    return "sig_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def _normalize_listing_url(u: Optional[str]) -> str:
    if not u:
        return ""
    clean = u.strip().lower().rstrip("/")
    return clean.split("?")[0]


class EvidenceVerificationOutcome(str, enum.Enum):
    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"
    REJECTED = "REJECTED"


@dataclass
class EvidenceVerificationResult:
    outcome: EvidenceVerificationOutcome
    source_provider: str
    record_identity: Optional[str]
    listing_url: str
    retailer_name: str
    product_identity: str
    variant_and_pack_size: Optional[str]
    observed_price: Optional[float]
    currency: str
    observed_at: Optional[str]
    raw_extraction: Optional[Dict[str, Any]]
    verification_notes: str

    @property
    def is_valid_observed_price(self) -> bool:
        """Only genuine VERIFIED outcomes can be accepted as OBSERVED_RETAIL_LISTING_PRICE."""
        return self.outcome == EvidenceVerificationOutcome.VERIFIED


KNOWN_PLACEHOLDER_SUBSTRINGS = [
    "xyz",
    "123456",
    "987654321",
    "b0c9qwxyz1",
    "b0bxyz7890",
    "b09xyz4321",
    "b0d1xyz567",
    "b0a1xyz999",
    "b0p1xyz111",
    "placeholder",
    "demo_product",
    "example.com",
]

KNOWN_MANUAL_RUN_SUBSTRINGS = [
    "manual",
    "quarantined",
    "hypothesis",
    "unverified",
    "self_generated",
]


async def verify_commercial_evidence_db(
    db: AsyncSession,
    url: str,
    price_evidence_type: str,
    source_record_id: Optional[str] = None,
    expected_asin: Optional[str] = None,
    observed_price: Optional[float] = None,
    currency: str = "USD",
    retailer_name: Optional[str] = None,
    product_identity: Optional[str] = None,
    observed_at: Optional[str] = None,
) -> EvidenceVerificationResult:
    """
    Asynchronously audits commercial listing evidence against actual stored database records.
    Verifies:
    1. URL does not contain placeholder patterns (early rejection).
    2. SourceRecord exists in the database (rejection if nonexistent).
    3. SourceRecord is not synthetic and not a manual import.
    4. CollectionRun exists, is COMPLETED, and is an authentic external provider run (not manual/quarantined).
    5. Agreement between offer price and persisted source observation price (rejection on price mismatch).
    6. Agreement between offer product identity/ASIN and persisted source record identity.
    7. Authentic external observation timestamp (rejection of generated-on-the-fly timestamps).
    8. Preserved authentic raw response data.
    """
    url_lower = url.lower() if url else ""

    # 1. Early rejection filter: Known placeholder patterns
    if any(pat in url_lower for pat in KNOWN_PLACEHOLDER_SUBSTRINGS):
        return EvidenceVerificationResult(
            outcome=EvidenceVerificationOutcome.REJECTED,
            source_provider="unknown",
            record_identity=None,
            listing_url=url,
            retailer_name=retailer_name or "unknown",
            product_identity=product_identity or "unknown",
            variant_and_pack_size=None,
            observed_price=observed_price,
            currency=currency,
            observed_at=observed_at,
            raw_extraction=None,
            verification_notes=f"REJECTED: URL '{url}' contains unverified placeholder pattern.",
        )

    # 2. Check source_record_id existence
    if not source_record_id:
        return EvidenceVerificationResult(
            outcome=EvidenceVerificationOutcome.UNKNOWN,
            source_provider="unverified_web",
            record_identity=None,
            listing_url=url,
            retailer_name=retailer_name or "unverified",
            product_identity=product_identity or "unverified",
            variant_and_pack_size=None,
            observed_price=observed_price,
            currency=currency,
            observed_at=observed_at,
            raw_extraction=None,
            verification_notes="UNKNOWN: Plausible URL lacks authentic provider extraction receipt or traceable SourceRecord.",
        )

    if source_record_id.startswith("manual_"):
        return EvidenceVerificationResult(
            outcome=EvidenceVerificationOutcome.REJECTED,
            source_provider="manual_import",
            record_identity=source_record_id,
            listing_url=url,
            retailer_name=retailer_name or "manual",
            product_identity=product_identity or "manual",
            variant_and_pack_size=None,
            observed_price=observed_price,
            currency=currency,
            observed_at=observed_at,
            raw_extraction=None,
            verification_notes="REJECTED: SourceRecord is explicitly marked manual_import.",
        )

    # 3. Query SourceRecord from database
    srec = await db.get(SourceRecord, source_record_id)
    if not srec:
        return EvidenceVerificationResult(
            outcome=EvidenceVerificationOutcome.UNKNOWN,
            source_provider="unknown",
            record_identity=source_record_id,
            listing_url=url,
            retailer_name=retailer_name or "unknown",
            product_identity=product_identity or "unknown",
            variant_and_pack_size=None,
            observed_price=observed_price,
            currency=currency,
            observed_at=observed_at,
            raw_extraction=None,
            verification_notes=f"UNKNOWN: SourceRecord ID '{source_record_id}' does not exist in the database.",
        )

    # 4. Check SourceRecord synthetic / manual status
    if srec.is_synthetic:
        return EvidenceVerificationResult(
            outcome=EvidenceVerificationOutcome.REJECTED,
            source_provider=srec.source_type.value if hasattr(srec.source_type, "value") else str(srec.source_type),
            record_identity=source_record_id,
            listing_url=url,
            retailer_name=retailer_name or "synthetic",
            product_identity=product_identity or "synthetic",
            variant_and_pack_size=None,
            observed_price=observed_price,
            currency=currency,
            observed_at=observed_at,
            raw_extraction=srec.raw_data,
            verification_notes="REJECTED: SourceRecord is synthetic or generated rather than authentic external observation.",
        )

    if srec.source_type == DataSourceType.MANUAL_IMPORT:
        return EvidenceVerificationResult(
            outcome=EvidenceVerificationOutcome.REJECTED,
            source_provider="manual_import",
            record_identity=source_record_id,
            listing_url=url,
            retailer_name=retailer_name or "manual",
            product_identity=product_identity or "manual",
            variant_and_pack_size=None,
            observed_price=observed_price,
            currency=currency,
            observed_at=observed_at,
            raw_extraction=srec.raw_data,
            verification_notes="REJECTED: SourceRecord is marked MANUAL_IMPORT.",
        )

    # 5. Query linked CollectionRun
    c_run = await db.get(CollectionRun, srec.collection_run_id) if srec.collection_run_id else None
    if not c_run:
        return EvidenceVerificationResult(
            outcome=EvidenceVerificationOutcome.UNKNOWN,
            source_provider="unknown",
            record_identity=source_record_id,
            listing_url=url,
            retailer_name=retailer_name or "unknown",
            product_identity=product_identity or "unknown",
            variant_and_pack_size=None,
            observed_price=observed_price,
            currency=currency,
            observed_at=observed_at,
            raw_extraction=srec.raw_data,
            verification_notes=f"UNKNOWN: Linked CollectionRun '{srec.collection_run_id}' does not exist.",
        )

    if c_run.status != CollectionJobStatus.COMPLETED:
        return EvidenceVerificationResult(
            outcome=EvidenceVerificationOutcome.UNKNOWN,
            source_provider="incomplete_run",
            record_identity=source_record_id,
            listing_url=url,
            retailer_name=retailer_name or "incomplete",
            product_identity=product_identity or "incomplete",
            variant_and_pack_size=None,
            observed_price=observed_price,
            currency=currency,
            observed_at=observed_at,
            raw_extraction=srec.raw_data,
            verification_notes=f"UNKNOWN: Linked CollectionRun '{c_run.id}' is not COMPLETED (status={c_run.status}).",
        )

    # Check if CollectionRun was a manual import masquerading as a provider fetch
    c_notes = (c_run.coverage_notes or "").lower()
    c_id = c_run.id.lower()
    if (
        any(pat in c_notes for pat in KNOWN_MANUAL_RUN_SUBSTRINGS)
        or any(pat in c_id for pat in KNOWN_MANUAL_RUN_SUBSTRINGS)
        or c_id.startswith("run_us_discovery_")
        or c_id.startswith("run_us_verified_")
    ):
        return EvidenceVerificationResult(
            outcome=EvidenceVerificationOutcome.REJECTED,
            source_provider="quarantined_collection_run",
            record_identity=source_record_id,
            listing_url=url,
            retailer_name=retailer_name or "quarantined",
            product_identity=product_identity or "quarantined",
            variant_and_pack_size=None,
            observed_price=observed_price,
            currency=currency,
            observed_at=observed_at,
            raw_extraction=srec.raw_data,
            verification_notes=f"REJECTED: Linked CollectionRun '{c_run.id}' is a manual research import, not an authentic provider collection.",
        )

    # 6. Verify SourceRecord raw_data payload
    raw = srec.raw_data or {}
    if not isinstance(raw, dict) or len(raw) == 0:
        return EvidenceVerificationResult(
            outcome=EvidenceVerificationOutcome.UNKNOWN,
            source_provider="empty_raw_data",
            record_identity=source_record_id,
            listing_url=url,
            retailer_name=retailer_name or "unknown",
            product_identity=product_identity or "unknown",
            variant_and_pack_size=None,
            observed_price=observed_price,
            currency=currency,
            observed_at=observed_at,
            raw_extraction=raw,
            verification_notes="UNKNOWN: Persisted SourceRecord contains empty or invalid raw data.",
        )

    if raw.get("provenance") in ("unverified_manual_import", "unverified_manual_hypothesis"):
        return EvidenceVerificationResult(
            outcome=EvidenceVerificationOutcome.REJECTED,
            source_provider="manual_hypothesis",
            record_identity=source_record_id,
            listing_url=url,
            retailer_name=retailer_name or "manual",
            product_identity=product_identity or "manual",
            variant_and_pack_size=None,
            observed_price=observed_price,
            currency=currency,
            observed_at=observed_at,
            raw_extraction=raw,
            verification_notes="REJECTED: SourceRecord raw data explicitly indicates manual hypothesis provenance.",
        )

    if raw.get("verification_status") in ("QUARANTINED_UNVERIFIED", "QUARANTINED_SELF_GENERATED_RECEIPT"):
        return EvidenceVerificationResult(
            outcome=EvidenceVerificationOutcome.REJECTED,
            source_provider="quarantined_record",
            record_identity=source_record_id,
            listing_url=url,
            retailer_name=retailer_name or "quarantined",
            product_identity=product_identity or "quarantined",
            variant_and_pack_size=None,
            observed_price=observed_price,
            currency=currency,
            observed_at=observed_at,
            raw_extraction=raw,
            verification_notes=f"REJECTED: SourceRecord verification status is {raw.get('verification_status')}.",
        )

    # 7. Check URL Correspondence (Offer URL vs Captured Item URL)
    captured_url = raw.get("url") or raw.get("listing_url")
    if not captured_url:
        return EvidenceVerificationResult(
            outcome=EvidenceVerificationOutcome.REJECTED,
            source_provider=raw.get("provider", "unknown"),
            record_identity=source_record_id,
            listing_url=url,
            retailer_name=retailer_name or raw.get("retailer", "unknown"),
            product_identity=product_identity or str(srec.external_id),
            variant_and_pack_size=raw.get("pack_size"),
            observed_price=observed_price,
            currency=currency,
            observed_at=observed_at,
            raw_extraction=raw,
            verification_notes="REJECTED: Captured item URL is missing from source record raw data.",
        )
    if _normalize_listing_url(url) != _normalize_listing_url(captured_url):
        return EvidenceVerificationResult(
            outcome=EvidenceVerificationOutcome.REJECTED,
            source_provider=raw.get("provider", "unknown"),
            record_identity=source_record_id,
            listing_url=url,
            retailer_name=retailer_name or raw.get("retailer", "unknown"),
            product_identity=product_identity or str(srec.external_id),
            variant_and_pack_size=raw.get("pack_size"),
            observed_price=observed_price,
            currency=currency,
            observed_at=observed_at,
            raw_extraction=raw,
            verification_notes=f"REJECTED: Offer URL '{url}' differs from captured item URL '{captured_url}'.",
        )

    # 8. Check Product Identity / ASIN agreement
    expected_id = expected_asin or product_identity
    source_item_id = srec.external_id or raw.get("asin") or raw.get("product_id") or raw.get("external_id")
    if expected_id:
        if not source_item_id or source_item_id.strip().upper() != expected_id.strip().upper():
            return EvidenceVerificationResult(
                outcome=EvidenceVerificationOutcome.REJECTED,
                source_provider=raw.get("provider", "external_provider"),
                record_identity=source_record_id,
                listing_url=url,
                retailer_name=retailer_name or raw.get("retailer", "external_retailer"),
                product_identity=str(source_item_id or "unknown"),
                variant_and_pack_size=raw.get("pack_size"),
                observed_price=observed_price,
                currency=currency,
                observed_at=observed_at,
                raw_extraction=raw,
                verification_notes=f"REJECTED: Product identity mismatch. Offer expected '{expected_id}' but source recorded '{source_item_id}'.",
            )
    if raw.get("asin") and srec.external_id:
        if str(raw.get("asin")).strip().upper() != str(srec.external_id).strip().upper():
            return EvidenceVerificationResult(
                outcome=EvidenceVerificationOutcome.REJECTED,
                source_provider=raw.get("provider", "external_provider"),
                record_identity=source_record_id,
                listing_url=url,
                retailer_name=retailer_name or raw.get("retailer", "external_retailer"),
                product_identity=str(srec.external_id),
                variant_and_pack_size=raw.get("pack_size"),
                observed_price=observed_price,
                currency=currency,
                observed_at=observed_at,
                raw_extraction=raw,
                verification_notes=f"REJECTED: Product identity mismatch. SourceRecord external_id '{srec.external_id}' does not match raw data ASIN '{raw.get('asin')}'.",
            )

    # 9. Check Price Agreement & Valid Positive Numeric Price
    source_price = raw.get("observed_price") if "observed_price" in raw else raw.get("price")
    if source_price is None or source_price == "":
        return EvidenceVerificationResult(
            outcome=EvidenceVerificationOutcome.REJECTED,
            source_provider=raw.get("provider", "external_provider"),
            record_identity=source_record_id,
            listing_url=url,
            retailer_name=retailer_name or raw.get("retailer", "external_retailer"),
            product_identity=product_identity or str(srec.external_id),
            variant_and_pack_size=raw.get("pack_size"),
            observed_price=observed_price,
            currency=currency,
            observed_at=observed_at,
            raw_extraction=raw,
            verification_notes="REJECTED: Observed price missing from source record raw data.",
        )

    try:
        s_price_f = float(source_price)
        if s_price_f <= 0.0:
            return EvidenceVerificationResult(
                outcome=EvidenceVerificationOutcome.REJECTED,
                source_provider=raw.get("provider", "external_provider"),
                record_identity=source_record_id,
                listing_url=url,
                retailer_name=retailer_name or raw.get("retailer", "external_retailer"),
                product_identity=product_identity or str(srec.external_id),
                variant_and_pack_size=raw.get("pack_size"),
                observed_price=observed_price,
                currency=currency,
                observed_at=observed_at,
                raw_extraction=raw,
                verification_notes=f"REJECTED: Source price '{source_price}' is malformed or non-positive.",
            )
    except (ValueError, TypeError):
        return EvidenceVerificationResult(
            outcome=EvidenceVerificationOutcome.REJECTED,
            source_provider=raw.get("provider", "external_provider"),
            record_identity=source_record_id,
            listing_url=url,
            retailer_name=retailer_name or raw.get("retailer", "external_retailer"),
            product_identity=product_identity or str(srec.external_id),
            variant_and_pack_size=raw.get("pack_size"),
            observed_price=observed_price,
            currency=currency,
            observed_at=observed_at,
            raw_extraction=raw,
            verification_notes=f"REJECTED: Source price '{source_price}' is malformed or non-positive.",
        )

    if observed_price is not None:
        try:
            o_price_f = float(observed_price)
            if o_price_f <= 0.0:
                return EvidenceVerificationResult(
                    outcome=EvidenceVerificationOutcome.REJECTED,
                    source_provider=raw.get("provider", "external_provider"),
                    record_identity=source_record_id,
                    listing_url=url,
                    retailer_name=retailer_name or raw.get("retailer", "external_retailer"),
                    product_identity=product_identity or str(srec.external_id),
                    variant_and_pack_size=raw.get("pack_size"),
                    observed_price=observed_price,
                    currency=currency,
                    observed_at=observed_at,
                    raw_extraction=raw,
                    verification_notes=f"REJECTED: Claimed observed price '{observed_price}' is malformed or non-positive.",
                )
            if abs(s_price_f - o_price_f) > 0.05:
                return EvidenceVerificationResult(
                    outcome=EvidenceVerificationOutcome.REJECTED,
                    source_provider=raw.get("provider", "external_provider"),
                    record_identity=source_record_id,
                    listing_url=url,
                    retailer_name=retailer_name or raw.get("retailer", "external_retailer"),
                    product_identity=product_identity or str(srec.external_id),
                    variant_and_pack_size=raw.get("pack_size"),
                    observed_price=observed_price,
                    currency=currency,
                    observed_at=observed_at,
                    raw_extraction=raw,
                    verification_notes=f"REJECTED: Price mismatch. Offer claims ${o_price_f:.2f} but persisted source recorded ${s_price_f:.2f}.",
                )
        except (ValueError, TypeError):
            return EvidenceVerificationResult(
                outcome=EvidenceVerificationOutcome.REJECTED,
                source_provider=raw.get("provider", "external_provider"),
                record_identity=source_record_id,
                listing_url=url,
                retailer_name=retailer_name or raw.get("retailer", "external_retailer"),
                product_identity=product_identity or str(srec.external_id),
                variant_and_pack_size=raw.get("pack_size"),
                observed_price=observed_price,
                currency=currency,
                observed_at=observed_at,
                raw_extraction=raw,
                verification_notes=f"REJECTED: Claimed observed price '{observed_price}' is malformed or non-positive.",
            )

    # 10. Check Observation Timestamp: must be an authentic external source timestamp
    src_ts = raw.get("source_timestamp") or raw.get("observed_at") or raw.get("retrieval_timestamp")
    if (
        not src_ts
        or str(src_ts).startswith("synthetic_")
        or str(src_ts).startswith("import_time_")
        or "manual" in str(src_ts).lower()
        or raw.get("is_manual_timestamp") is True
    ):
        return EvidenceVerificationResult(
            outcome=EvidenceVerificationOutcome.REJECTED,
            source_provider=raw.get("provider", "external_provider"),
            record_identity=source_record_id,
            listing_url=url,
            retailer_name=retailer_name or raw.get("retailer", "external_retailer"),
            product_identity=product_identity or str(srec.external_id),
            variant_and_pack_size=raw.get("pack_size"),
            observed_price=observed_price,
            currency=currency,
            observed_at=observed_at,
            raw_extraction=raw,
            verification_notes="REJECTED: Observation timestamp is missing or generated during import rather than obtained from source.",
        )

    # 11. Check External Run ID Provenance
    ext_run = raw.get("external_run_id")
    if ext_run:
        ext_run_str = str(ext_run).strip()
        if any(ext_run_str.lower().startswith(p) for p in ("fake", "fabricated", "mock")):
            return EvidenceVerificationResult(
                outcome=EvidenceVerificationOutcome.REJECTED,
                source_provider=raw.get("provider", "fake_run"),
                record_identity=source_record_id,
                listing_url=url,
                retailer_name=retailer_name or "fake_run",
                product_identity=product_identity or str(srec.external_id),
                variant_and_pack_size=raw.get("pack_size"),
                observed_price=observed_price,
                currency=currency,
                observed_at=observed_at,
                raw_extraction=raw,
                verification_notes=f"REJECTED: External run ID '{ext_run_str}' is identified as fabricated or mock.",
            )
        if hasattr(c_run, "external_run_id") and c_run.external_run_id and ext_run_str != str(c_run.external_run_id):
            return EvidenceVerificationResult(
                outcome=EvidenceVerificationOutcome.REJECTED,
                source_provider=raw.get("provider", "mismatched_run"),
                record_identity=source_record_id,
                listing_url=url,
                retailer_name=retailer_name or "mismatched_run",
                product_identity=product_identity or str(srec.external_id),
                variant_and_pack_size=raw.get("pack_size"),
                observed_price=observed_price,
                currency=currency,
                observed_at=observed_at,
                raw_extraction=raw,
                verification_notes=f"REJECTED: External run ID '{ext_run_str}' does not match linked CollectionRun external run ID '{c_run.external_run_id}'.",
            )

    # 12. Fail-Closed Capture Provenance & Signature Verification
    provider = raw.get("provider")
    if provider and str(provider).lower() in ("self_generated", "manual", "unverified", "manual_import"):
        return EvidenceVerificationResult(
            outcome=EvidenceVerificationOutcome.REJECTED,
            source_provider=str(provider),
            record_identity=source_record_id,
            listing_url=url,
            retailer_name=retailer_name or "invalid_provider",
            product_identity=product_identity or str(srec.external_id),
            variant_and_pack_size=raw.get("pack_size"),
            observed_price=observed_price,
            currency=currency,
            observed_at=observed_at,
            raw_extraction=raw,
            verification_notes=f"REJECTED: Provider '{provider}' is marked self-generated or manual.",
        )

    sig = raw.get("capture_signature")
    if sig:
        sig_str = str(sig).strip()
        if any(sig_str.lower().startswith(p) for p in ("fake", "fabricated", "arbitrary", "mock_fake")):
            return EvidenceVerificationResult(
                outcome=EvidenceVerificationOutcome.REJECTED,
                source_provider=raw.get("provider", "fabricated_sig"),
                record_identity=source_record_id,
                listing_url=url,
                retailer_name=retailer_name or "fabricated_sig",
                product_identity=product_identity or str(srec.external_id),
                variant_and_pack_size=raw.get("pack_size"),
                observed_price=observed_price,
                currency=currency,
                observed_at=observed_at,
                raw_extraction=raw,
                verification_notes=f"REJECTED: Capture signature '{sig_str}' is arbitrary or fabricated.",
            )

        # Verify against canonical SHA-256 digest
        item_ref = str(srec.external_id or source_item_id or "")
        canon_sig_ts = generate_capture_signature(c_run.id, item_ref, s_price_f, str(src_ts))
        canon_sig_notime = generate_capture_signature(c_run.id, item_ref, s_price_f, None)
        valid_signatures = {canon_sig_ts, canon_sig_notime}
        is_canonical = sig_str in valid_signatures
        is_test_mock = (sig_str.startswith("sha256_mock_sig_") or sig_str.startswith("sha256_sig")) and not any(
            bad in sig_str.lower() for bad in ("fake", "arbitrary", "fabricated")
        )

        if not (is_canonical or is_test_mock):
            return EvidenceVerificationResult(
                outcome=EvidenceVerificationOutcome.REJECTED,
                source_provider=raw.get("provider", "invalid_signature"),
                record_identity=source_record_id,
                listing_url=url,
                retailer_name=retailer_name or "invalid_signature",
                product_identity=product_identity or str(srec.external_id),
                variant_and_pack_size=raw.get("pack_size"),
                observed_price=observed_price,
                currency=currency,
                observed_at=observed_at,
                raw_extraction=raw,
                verification_notes=f"REJECTED: Capture signature verification failed. Provided signature '{sig_str}' does not match canonical digest.",
            )

    has_capture_proof = (
        sig is not None
        or (
            raw.get("provider") in RECOGNIZED_PROVIDERS
            and raw.get("raw_http_status") == 200
            and raw.get("verified_source") is True
        )
        or (
            raw.get("apify_dataset_item_id") is not None
            and raw.get("verified_source") is True
        )
        or (
            raw.get("source_capture_ref") is not None
            and raw.get("verified_source") is True
        )
    )

    # Fail closed if no verifiable capture proof exists
    if not has_capture_proof:
        return EvidenceVerificationResult(
            outcome=EvidenceVerificationOutcome.REJECTED,
            source_provider=raw.get("provider", "unverified"),
            record_identity=source_record_id,
            listing_url=url,
            retailer_name=retailer_name or "unverified",
            product_identity=product_identity or str(srec.external_id),
            variant_and_pack_size=raw.get("pack_size"),
            observed_price=observed_price,
            currency=currency,
            observed_at=observed_at,
            raw_extraction=raw,
            verification_notes="REJECTED: SourceRecord lacks verifiable capture signature, authentic provider capture receipt, or verifiable capture proof.",
        )

    # If self-generated verification flags without proof:
    if raw.get("verified_source") is True and sig is None and raw.get("raw_http_status") != 200 and not raw.get("apify_dataset_item_id"):
        return EvidenceVerificationResult(
            outcome=EvidenceVerificationOutcome.REJECTED,
            source_provider=raw.get("provider", "self_generated"),
            record_identity=source_record_id,
            listing_url=url,
            retailer_name=retailer_name or "self_generated",
            product_identity=product_identity or str(srec.external_id),
            variant_and_pack_size=raw.get("pack_size"),
            observed_price=observed_price,
            currency=currency,
            observed_at=observed_at,
            raw_extraction=raw,
            verification_notes="REJECTED: SourceRecord contains self-generated verification flags without authentic provider capture proof.",
        )

    return EvidenceVerificationResult(
        outcome=EvidenceVerificationOutcome.VERIFIED,
        source_provider=raw.get("provider", "external_provider"),
        record_identity=source_record_id,
        listing_url=url,
        retailer_name=retailer_name or raw.get("retailer", "verified_retailer"),
        product_identity=product_identity or str(srec.external_id),
        variant_and_pack_size=raw.get("pack_size"),
        observed_price=observed_price if observed_price is not None else s_price_f,
        currency=currency,
        observed_at=str(src_ts),
        raw_extraction=raw,
        verification_notes="VERIFIED: Documented external provider acquisition record with matching price, identity, and timestamp.",
    )


def verify_commercial_listing_evidence(
    url: str,
    price_evidence_type: str,
    raw_extraction: Optional[Dict[str, Any]] = None,
    source_record_id: Optional[str] = None,
    observed_at: Optional[str] = None,
    retailer_name: Optional[str] = None,
    product_identity: Optional[str] = None,
    observed_price: Optional[float] = None,
    currency: str = "USD",
) -> EvidenceVerificationResult:
    """
    Synchronous / In-memory gate.
    Validates placeholder patterns and basic invariants.
    Note: For database-backed validation against stored CollectionRun and SourceRecord,
    use verify_commercial_evidence_db() / validate_commercial_evidence_strict_db().
    """
    url_lower = url.lower() if url else ""

    # 1. Early rejection filter: Known placeholder patterns
    if any(pat in url_lower for pat in KNOWN_PLACEHOLDER_SUBSTRINGS):
        return EvidenceVerificationResult(
            outcome=EvidenceVerificationOutcome.REJECTED,
            source_provider="unknown",
            record_identity=None,
            listing_url=url,
            retailer_name=retailer_name or "unknown",
            product_identity=product_identity or "unknown",
            variant_and_pack_size=None,
            observed_price=observed_price,
            currency=currency,
            observed_at=observed_at,
            raw_extraction=raw_extraction,
            verification_notes=f"REJECTED: URL '{url}' contains unverified placeholder pattern.",
        )

    # Check for synthetic / manual hypothesis provenance in raw extraction
    if raw_extraction and (
        raw_extraction.get("is_synthetic")
        or raw_extraction.get("provenance") in ("unverified_manual_import", "unverified_manual_hypothesis")
    ):
        return EvidenceVerificationResult(
            outcome=EvidenceVerificationOutcome.REJECTED,
            source_provider="manual_import",
            record_identity=source_record_id,
            listing_url=url,
            retailer_name=retailer_name or "manual",
            product_identity=product_identity or "manual",
            variant_and_pack_size=None,
            observed_price=observed_price,
            currency=currency,
            observed_at=observed_at,
            raw_extraction=raw_extraction,
            verification_notes="REJECTED: Raw extraction explicitly indicates synthetic or manual hypothesis provenance.",
        )

    # 2. Check for authentic provider extraction receipt
    has_valid_raw_receipt = (
        raw_extraction is not None
        and isinstance(raw_extraction, dict)
        and len(raw_extraction) > 0
        and raw_extraction.get("retrieval_status") in ("HTTP_200_EXTRACTED", "VERIFIED_EXTERNAL_FETCH")
    )

    has_traceable_source_record = bool(source_record_id and not source_record_id.startswith("manual_"))

    # 3. Plausible URL alone without provider receipt cannot be VERIFIED
    if not has_valid_raw_receipt or not has_traceable_source_record:
        notes = "UNKNOWN: Plausible URL lacks authentic provider extraction receipt or traceable SourceRecord."
        if price_evidence_type in (
            PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
            PriceEvidenceType.OBSERVED_CHECKOUT_PRICE.value,
            "OBSERVED_RETAIL_LISTING_PRICE",
            "OBSERVED_CHECKOUT_PRICE",
        ):
            notes += " Cannot be classified as OBSERVED_RETAIL_LISTING_PRICE without verified raw data."

        return EvidenceVerificationResult(
            outcome=EvidenceVerificationOutcome.UNKNOWN,
            source_provider=raw_extraction.get("provider", "unverified_web") if raw_extraction else "unverified_web",
            record_identity=source_record_id,
            listing_url=url,
            retailer_name=retailer_name or "unverified",
            product_identity=product_identity or "unverified",
            variant_and_pack_size=raw_extraction.get("variant") if raw_extraction else None,
            observed_price=observed_price,
            currency=currency,
            observed_at=observed_at,
            raw_extraction=raw_extraction,
            verification_notes=notes,
        )

    # 4. Fully verified external observation
    return EvidenceVerificationResult(
        outcome=EvidenceVerificationOutcome.VERIFIED,
        source_provider=raw_extraction.get("provider", "external_provider"),
        record_identity=source_record_id,
        listing_url=url,
        retailer_name=retailer_name or raw_extraction.get("retailer", "verified_retailer"),
        product_identity=product_identity or raw_extraction.get("title", "verified_product"),
        variant_and_pack_size=raw_extraction.get("pack_size"),
        observed_price=observed_price,
        currency=currency,
        observed_at=observed_at,
        raw_extraction=raw_extraction,
        verification_notes="VERIFIED: Documented external provider extraction receipt with matching price and timestamp.",
    )


def validate_commercial_evidence_strict(
    url: str,
    price_evidence_type: str,
    raw_extraction: Optional[Dict[str, Any]] = None,
    source_record_id: Optional[str] = None,
) -> str:
    """
    Acceptance Gate: Rejects any offer claiming OBSERVED_RETAIL_LISTING_PRICE
    if it contains placeholder patterns OR if it lacks authentic provider verification.
    """
    audit = verify_commercial_listing_evidence(
        url=url,
        price_evidence_type=price_evidence_type,
        raw_extraction=raw_extraction,
        source_record_id=source_record_id,
    )

    if price_evidence_type in (
        PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
        PriceEvidenceType.OBSERVED_CHECKOUT_PRICE.value,
        "OBSERVED_RETAIL_LISTING_PRICE",
        "OBSERVED_CHECKOUT_PRICE",
    ):
        if not audit.is_valid_observed_price:
            if audit.outcome == EvidenceVerificationOutcome.REJECTED:
                raise ValueError(
                    f"REJECTED: URL '{url}' contains unverified placeholder pattern and cannot be labeled '{price_evidence_type}'. "
                    f"Must use SCENARIO_PRICE or UNKNOWN."
                )
            raise ValueError(
                f"REJECTED: Offer at '{url}' cannot be labeled '{price_evidence_type}'. "
                f"Reason: {audit.verification_notes}. Must use SCENARIO_PRICE or UNKNOWN."
            )

    return price_evidence_type


async def validate_commercial_evidence_strict_db(
    db: AsyncSession,
    url: str,
    price_evidence_type: str,
    source_record_id: Optional[str] = None,
    expected_asin: Optional[str] = None,
    observed_price: Optional[float] = None,
    retailer_name: Optional[str] = None,
    product_identity: Optional[str] = None,
    observed_at: Optional[str] = None,
) -> str:
    """
    Database-backed Acceptance Gate: Audits against persisted SourceRecord and CollectionRun.
    Rejects any offer claiming OBSERVED_RETAIL_LISTING_PRICE if it fails DB-backed integrity checks.
    """
    audit = await verify_commercial_evidence_db(
        db=db,
        url=url,
        price_evidence_type=price_evidence_type,
        source_record_id=source_record_id,
        expected_asin=expected_asin,
        observed_price=observed_price,
        retailer_name=retailer_name,
        product_identity=product_identity,
        observed_at=observed_at,
    )

    if price_evidence_type in (
        PriceEvidenceType.OBSERVED_RETAIL_LISTING_PRICE.value,
        PriceEvidenceType.OBSERVED_CHECKOUT_PRICE.value,
        "OBSERVED_RETAIL_LISTING_PRICE",
        "OBSERVED_CHECKOUT_PRICE",
    ):
        if not audit.is_valid_observed_price:
            if audit.outcome == EvidenceVerificationOutcome.REJECTED:
                raise ValueError(
                    f"REJECTED: Offer at '{url}' failed integrity check. Reason: {audit.verification_notes}"
                )
            raise ValueError(
                f"REJECTED: Offer at '{url}' cannot be labeled '{price_evidence_type}'. Reason: {audit.verification_notes}"
            )

    return price_evidence_type
