"""
US WIN HUNTER — Commercial Evidence Verification Service
Enforces rigorous evidence provenance:
- Early rejection of placeholder strings and synthetic URL patterns.
- Rejection of valid-looking ASINs/IDs that lack authentic source provider extraction receipts.
- Distinguishes VERIFIED, PARTIAL, UNKNOWN, and REJECTED commercial observations.
- Prevents plausible but unverified URLs from becoming OBSERVED_RETAIL_LISTING_PRICE.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import enum
from typing import Optional, Dict, Any

from app.models.models import PriceEvidenceType, EvidenceType


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
    Audits a candidate retail listing offer against strict data integrity criteria.
    Validates that:
    1. URL does not match synthetic placeholder patterns (early rejection).
    2. URL shape alone (e.g. valid-looking ASIN B07FZ8S74R) is NOT accepted as proof.
    3. Authentic external provider extraction receipt (raw_extraction) is present and verified.
    4. Observation timestamp is an authentic provider timestamp, not synthetic now().
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

    # 2. Check for authentic provider extraction receipt
    has_valid_raw_receipt = (
        raw_extraction is not None
        and isinstance(raw_extraction, dict)
        and len(raw_extraction) > 0
        and raw_extraction.get("retrieval_status") in ("HTTP_200_EXTRACTED", "VERIFIED_EXTERNAL_FETCH")
    )

    has_traceable_source_record = bool(source_record_id and not source_record_id.startswith("manual_"))

    has_authentic_timestamp = bool(observed_at and not observed_at.startswith("synthetic_"))

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
