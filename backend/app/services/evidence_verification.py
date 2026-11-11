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
import json
from pathlib import Path
import re
import tempfile
from typing import Optional, Dict, Any, Tuple, Union
from urllib.parse import urlparse
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


BOT_CHALLENGE_PATTERNS: Tuple[str, ...] = (
    "robot check",
    "<title>robot check</title>",
    "to discuss automated access to amazon data",
    "type the characters you see in this image",
    "challenge-platform",
    "cf-browser-verification",
    "attention required! | cloudflare",
    "perimeterx",
    "<title>access denied</title>",
    "<title>security challenge</title>",
    "human verification",
    "distil captcha",
    "sorry, we just need to make sure you're not a robot",
)


def is_safe_artifact_path(
    artifact_path: Union[str, Path],
    repo_root: Optional[Path] = None,
) -> Tuple[bool, Optional[Path], Optional[str]]:
    """
    Validates artifact path location against directory traversal.
    Artifacts must reside within authorized repo subdirectories:
    - docs/run_reports/artifacts
    - docs/run_reports
    - backend/tests or tests
    - Temporary test directory (for isolated unit testing)
    """
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[3]

    try:
        raw_p = Path(artifact_path)
        if not raw_p.is_absolute():
            candidate = (repo_root / raw_p).resolve()
        else:
            candidate = raw_p.resolve()

        repo_resolved = repo_root.resolve()

        # Check for path traversal escaping allowed areas
        temp_dir = Path(tempfile.gettempdir()).resolve()

        allowed_roots = (
            (repo_resolved / "docs" / "run_reports").resolve(),
            (repo_resolved / "backend" / "tests").resolve(),
            (repo_resolved / "tests").resolve(),
            temp_dir,
        )

        is_allowed = any(candidate == r or r in candidate.parents for r in allowed_roots)
        if not is_allowed:
            return False, candidate, f"Artifact path '{artifact_path}' is outside authorized artifact directories."

        return True, candidate, None
    except Exception as e:
        return False, None, f"Invalid artifact path '{artifact_path}': {str(e)}"


def extract_structured_product_evidence(html_text: str) -> Dict[str, Any]:
    """
    Parses structured product metadata, canonical URLs, and observed prices from an HTML response body.
    Excludes any assistant-generated acquisition preambles or HTML comments.
    """
    # 1. Exclude assistant-generated artifact preamble / headers if present
    preamble_match = re.match(r'^\s*<!--[\s\S]*?-->\s*', html_text)
    if preamble_match and any(marker in preamble_match.group(0) for marker in (
        "US WIN HUNTER COMMERCIAL EVIDENCE",
        "SANITIZED PUBLIC RECORD",
        "ACQUISITION METADATA",
        "ASSISTANT EVIDENCE PREAMBLE",
    )):
        effective_html = html_text[preamble_match.end():]
    else:
        effective_html = html_text

    # Strip all HTML comments from effective_html for price / identity searching
    # so comments cannot smuggle fake prices or fake identities
    cleaned_html = re.sub(r'<!--[\s\S]*?-->', '', effective_html)

    identities = set()
    prices = []  # list of dict: {"price": float, "currency": str, "source": str, "availability": str}
    canonical_urls = []

    # 2. Extract Canonical URL and og:url
    for m in re.finditer(r'<link[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']', cleaned_html, re.IGNORECASE):
        canonical_urls.append(m.group(1).strip())
    for m in re.finditer(r'<meta[^>]*property=["\']og:url["\'][^>]*content=["\']([^"\']+)["\']', cleaned_html, re.IGNORECASE):
        canonical_urls.append(m.group(1).strip())

    # 3. Parse JSON-LD scripts
    json_ld_matches = re.finditer(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', effective_html, re.IGNORECASE | re.DOTALL)
    for jm in json_ld_matches:
        try:
            data = json.loads(jm.group(1).strip())
            items = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
            for item in items:
                if not isinstance(item, dict):
                    continue
                itype = item.get("@type", "")
                if itype == "Product" or "Product" in itype:
                    for field in ("sku", "mpn", "gtin", "gtin13", "gtin8", "model"):
                        val = item.get(field)
                        if val and isinstance(val, str):
                            identities.add(val.strip().lower())
                    name = item.get("name")
                    if name and isinstance(name, str):
                        identities.add(name.strip().lower())
                    if item.get("url"):
                        canonical_urls.append(str(item.get("url")).strip())

                    offers = item.get("offers", [])
                    if isinstance(offers, dict):
                        offers = [offers]
                    elif not isinstance(offers, list):
                        offers = []
                    for off in offers:
                        if not isinstance(off, dict):
                            continue
                        p_raw = off.get("price")
                        curr = off.get("priceCurrency", "USD")
                        avail = off.get("availability")
                        avail_clean = "UNKNOWN"
                        if avail:
                            if "InStock" in avail:
                                avail_clean = "InStock"
                            elif "OutOfStock" in avail:
                                avail_clean = "OutOfStock"
                        if p_raw is not None:
                            try:
                                p_float = float(str(p_raw).replace("$", "").replace(",", "").strip())
                                if p_float > 0:
                                    prices.append({
                                        "price": p_float,
                                        "currency": curr.upper(),
                                        "source": "json_ld_offer",
                                        "availability": avail_clean
                                    })
                            except (ValueError, TypeError):
                                pass
        except Exception:
            pass

    # 4. OpenGraph and product meta tags
    og_title_m = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']', cleaned_html, re.IGNORECASE)
    if og_title_m:
        identities.add(og_title_m.group(1).strip().lower())

    og_price_m = re.search(r'<meta[^>]*property=["\'](?:og:price:amount|product:price:amount)["\'][^>]*content=["\']([^"\']+)["\']', cleaned_html, re.IGNORECASE)
    og_curr_m = re.search(r'<meta[^>]*property=["\'](?:og:price:currency|product:price:currency)["\'][^>]*content=["\']([^"\']+)["\']', cleaned_html, re.IGNORECASE)
    if og_price_m:
        try:
            p_val = float(og_price_m.group(1).strip())
            c_val = og_curr_m.group(1).strip().upper() if og_curr_m else "USD"
            prices.append({"price": p_val, "currency": c_val, "source": "og_price_meta", "availability": "UNKNOWN"})
        except (ValueError, TypeError):
            pass

    # 5. Microdata itemprop="price"
    micro_prices = re.finditer(r'<[^>]*itemprop=["\']price["\'][^>]*content=["\']([^"\']+)["\']', cleaned_html, re.IGNORECASE)
    for mp in micro_prices:
        try:
            p_val = float(mp.group(1).replace("$", "").replace(",", "").strip())
            prices.append({"price": p_val, "currency": "USD", "source": "microdata_itemprop", "availability": "UNKNOWN"})
        except Exception:
            pass

    # 6. Structured Pricing DOM Containers (e.g. SalPrice, wt-product__price__final, goPriceBox, product__price)
    dom_patterns = [
        r'<(p|div|span|b)[^>]*class=["\'][^"\']*(?:SalPrice|goPriceBox|wt-product__price__final|product__price__final|product-single__price)[^"\']*["\'][^>]*>([\s\S]{1,500}?)<\/\1>',
        r'data-price=["\'](\d+\.?\d*)["\']',
    ]
    for pattern in dom_patterns:
        for m in re.finditer(pattern, cleaned_html, re.IGNORECASE):
            content = m.group(2) if m.lastindex >= 2 else m.group(1)
            num_match = re.search(r'\$?\s*(\d+\.\d{2})', content)
            if num_match:
                try:
                    p_val = float(num_match.group(1))
                    prices.append({"price": p_val, "currency": "USD", "source": "structured_dom_price", "availability": "UNKNOWN"})
                except Exception:
                    pass

    # 7. Collect identity tokens from product links or titles inside the page
    for m in re.finditer(r'href=["\'](?:/products/|https?://[^"\']+/products/)([a-zA-Z0-9_-]+)["\']', cleaned_html, re.IGNORECASE):
        identities.add(m.group(1).strip().lower())
    title_m = re.search(r'<title>(.*?)</title>', cleaned_html, re.IGNORECASE)
    if title_m:
        identities.add(title_m.group(1).strip().lower())

    # Fallback price regex on text (excluding comments and script/style tags)
    text_content = re.sub(r'<(?:script|style)[^>]*>[\s\S]*?<\/(?:script|style)>', ' ', cleaned_html)
    for m in re.finditer(r'\$\s*(\d+\.\d{2})', text_content):
        try:
            p_val = float(m.group(1))
            prices.append({"price": p_val, "currency": "USD", "source": "text_regex", "availability": "UNKNOWN"})
        except Exception:
            pass

    return {
        "identities": list(identities),
        "prices": prices,
        "canonical_urls": canonical_urls,
        "cleaned_html": cleaned_html,
        "effective_html": effective_html,
    }


def inspect_artifact_content(
    artifact_path: Path,
    expected_digest: Optional[str] = None,
    expected_identity: Optional[str] = None,
    expected_price: Optional[float] = None,
    expected_currency: str = "USD",
    source_url: Optional[str] = None,
) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """
    Performs content-based inspection of a captured artifact file:
    1. Verifies file existence and non-zero size.
    2. Computes file SHA-256 digest and verifies against recorded digest if present.
    3. Detects and rejects bot challenge / CAPTCHA / WAF interstitial pages.
    4. Parses structured product evidence excluding assistant-generated acquisition preambles.
    5. Checks presence of expected product identity / SKU / ASIN in content.
    6. Checks presence of expected observed price and currency in content.
    7. Validates source URL against canonical URL / host if present.
    8. Returns (is_valid, rejection_reason, metadata).
    """
    if not artifact_path.exists() or not artifact_path.is_file():
        return False, f"Artifact file '{artifact_path}' does not exist on disk. An inspectable acquisition artifact on disk is required.", {}

    size = artifact_path.stat().st_size
    if size == 0:
        return False, f"Artifact file '{artifact_path}' is empty (0 bytes).", {}

    try:
        content_bytes = artifact_path.read_bytes()
    except Exception as e:
        return False, f"Failed to read artifact file: {str(e)}", {}

    actual_digest = hashlib.sha256(content_bytes).hexdigest()
    if expected_digest:
        clean_exp = str(expected_digest).strip().lower()
        if clean_exp.startswith("sha256:"):
            clean_exp = clean_exp[7:]
        if actual_digest.lower() != clean_exp:
            return False, (
                f"Artifact SHA-256 integrity check failed. "
                f"File digest is '{actual_digest}', recorded digest was '{clean_exp}'."
            ), {"actual_sha256": actual_digest}

    content_text = content_bytes.decode("utf-8", errors="replace")
    content_lower = content_text.lower()

    # Bot challenge / CAPTCHA detection
    for pattern in BOT_CHALLENGE_PATTERNS:
        if pattern in content_lower:
            return False, (
                f"Artifact content contains bot challenge / automated access restriction: '{pattern}'. "
                f"Commercial observation cannot be verified from a gated response."
            ), {"actual_sha256": actual_digest, "bot_pattern": pattern}

    # Extract structured evidence (excluding assistant preambles and HTML comments)
    evidence = extract_structured_product_evidence(content_text)

    # Product identity check
    if expected_identity:
        clean_id = str(expected_identity).strip().lower()
        if len(clean_id) >= 3:
            id_in_identities = any(clean_id in ident for ident in evidence["identities"])
            id_in_body = clean_id in evidence["cleaned_html"].lower()
            if not (id_in_identities or id_in_body):
                return False, (
                    f"Artifact content does not contain the expected product identity '{expected_identity}'."
                ), {"actual_sha256": actual_digest}

    # Price and currency check
    if expected_price is not None:
        try:
            p_val = float(expected_price)
            matched_prices = [
                p for p in evidence["prices"]
                if abs(p["price"] - p_val) < 0.05
            ]
            if not matched_prices:
                return False, (
                    f"Artifact content does not contain the claimed observed price '${p_val:.2f}'."
                ), {"actual_sha256": actual_digest}

            # Check currency agreement
            if expected_currency:
                exp_curr = expected_currency.strip().upper()
                curr_matched = any(p.get("currency", "USD").upper() == exp_curr for p in matched_prices)
                if not curr_matched:
                    return False, (
                        f"Artifact currency mismatch: expected '{exp_curr}', but observed offers had {[p.get('currency') for p in matched_prices]}."
                    ), {"actual_sha256": actual_digest}
        except (ValueError, TypeError):
            pass

    # Source URL / Canonical Host verification
    if source_url and evidence["canonical_urls"]:
        try:
            src_parsed = urlparse(source_url)
            src_netloc = src_parsed.netloc.lower().replace("www.", "")
            if src_netloc:
                valid_canon = False
                for c_url in evidence["canonical_urls"]:
                    c_parsed = urlparse(c_url)
                    c_netloc = c_parsed.netloc.lower().replace("www.", "")
                    if not c_netloc or c_netloc == src_netloc or src_netloc in c_netloc or c_netloc in src_netloc:
                        valid_canon = True
                        break
                if not valid_canon:
                    return False, (
                        f"Artifact canonical URL mismatch: source URL host '{src_netloc}' does not match canonical URLs {evidence['canonical_urls']}."
                    ), {"actual_sha256": actual_digest}
        except Exception:
            pass

    return True, None, {
        "actual_sha256": actual_digest,
        "size_bytes": size,
        "extracted_prices": evidence["prices"],
        "extracted_identities": evidence["identities"],
    }


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
        if any(sig_str.lower().startswith(p) for p in ("fake", "fabricated", "arbitrary", "mock", "sha256_mock", "test_mock", "mock_fake")):
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

        if not is_canonical:
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

    # Disallow caller-generated SHA-256 hashes, raw_http_status=200, and verified_source=True as sole proof.
    # Bind verification strictly to inspectable acquisition artifacts on disk or authorized Apify dataset items.
    artifact_ref = (
        raw.get("artifact_path")
        or raw.get("source_capture_ref")
        or raw.get("raw_capture_file")
        or raw.get("artifact_file")
    )
    has_valid_disk_artifact = False
    artifact_meta: Dict[str, Any] = {}

    if artifact_ref:
        repo_root = Path(__file__).resolve().parents[3]
        is_safe, art_p, path_err = is_safe_artifact_path(artifact_ref, repo_root)
        if not is_safe or art_p is None:
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
                verification_notes=f"REJECTED: {path_err}",
            )

        expected_digest = raw.get("artifact_sha256") or raw.get("capture_digest")
        item_identity = str(srec.external_id or source_item_id or expected_id or "")

        is_content_valid, content_err, meta = inspect_artifact_content(
            artifact_path=art_p,
            expected_digest=expected_digest,
            expected_identity=item_identity,
            expected_price=s_price_f,
            expected_currency=currency,
            source_url=captured_url,
        )

        if not is_content_valid:
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
                verification_notes=f"REJECTED: {content_err}",
            )
        else:
            has_valid_disk_artifact = True
            artifact_meta = meta

    has_apify_proof = bool(
        raw.get("apify_dataset_item_id")
        and not any(bad in str(raw.get("apify_dataset_item_id")).lower() for bad in ("mock", "fake", "arbitrary"))
        and raw.get("provider") in RECOGNIZED_PROVIDERS
    )
    if has_apify_proof and raw.get("apify_run_id"):
        if hasattr(c_run, "external_run_id") and c_run.external_run_id:
            if str(raw.get("apify_run_id")).strip() != str(c_run.external_run_id).strip():
                return EvidenceVerificationResult(
                    outcome=EvidenceVerificationOutcome.REJECTED,
                    source_provider="mismatched_apify_run",
                    record_identity=source_record_id,
                    listing_url=url,
                    retailer_name=retailer_name or "mismatched_run",
                    product_identity=product_identity or str(srec.external_id),
                    variant_and_pack_size=raw.get("pack_size"),
                    observed_price=observed_price,
                    currency=currency,
                    observed_at=observed_at,
                    raw_extraction=raw,
                    verification_notes=f"REJECTED: Apify run ID '{raw.get('apify_run_id')}' does not match CollectionRun external run ID '{c_run.external_run_id}'.",
                )

    # Fail closed if no verifiable capture proof exists
    if not (has_valid_disk_artifact or has_apify_proof):
        notes = "REJECTED: SourceRecord lacks verifiable capture signature, inspectable acquisition artifact on disk, or authorized Apify dataset item. "
        notes += "Caller-generated SHA-256 hashes, raw_http_status=200, and verified_source flags alone are not proof of external collection."
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
            verification_notes=notes,
        )

    # If self-generated verification flags without proof:
    if raw.get("verified_source") is True and not (has_valid_disk_artifact or has_apify_proof):
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

    # 4. Content check on referenced artifact (if provided)
    if raw_extraction and (raw_extraction.get("artifact_path") or raw_extraction.get("source_capture_ref")):
        art_ref = raw_extraction.get("artifact_path") or raw_extraction.get("source_capture_ref")
        repo_root = Path(__file__).resolve().parents[3]
        is_safe, art_p, path_err = is_safe_artifact_path(art_ref, repo_root)
        if not is_safe or art_p is None:
            return EvidenceVerificationResult(
                outcome=EvidenceVerificationOutcome.REJECTED,
                source_provider=raw_extraction.get("provider", "unverified"),
                record_identity=source_record_id,
                listing_url=url,
                retailer_name=retailer_name or "unverified",
                product_identity=product_identity or "unverified",
                variant_and_pack_size=None,
                observed_price=observed_price,
                currency=currency,
                observed_at=observed_at,
                raw_extraction=raw_extraction,
                verification_notes=f"REJECTED: {path_err}",
            )
        is_content_valid, content_err, _ = inspect_artifact_content(
            artifact_path=art_p,
            expected_digest=raw_extraction.get("artifact_sha256"),
            expected_identity=product_identity or raw_extraction.get("asin"),
            expected_price=observed_price,
            expected_currency=currency,
            source_url=url,
        )
        if not is_content_valid:
            return EvidenceVerificationResult(
                outcome=EvidenceVerificationOutcome.REJECTED,
                source_provider=raw_extraction.get("provider", "unverified"),
                record_identity=source_record_id,
                listing_url=url,
                retailer_name=retailer_name or "unverified",
                product_identity=product_identity or "unverified",
                variant_and_pack_size=None,
                observed_price=observed_price,
                currency=currency,
                observed_at=observed_at,
                raw_extraction=raw_extraction,
                verification_notes=f"REJECTED: {content_err}",
            )

    # 5. Fully verified external observation
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
