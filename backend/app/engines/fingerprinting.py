"""
US WIN HUNTER — Engine B: Creative Fingerprinting

Multi-layer identity system for detecting the same product across
different advertisers, names, and creatives.

Layers:
1. Exact URL / canonical URL matching
2. Product title normalization
3. Image perceptual hashing (pHash, dHash)
4. Image file hash (SHA-256)
5. Semantic description similarity (Phase 2+, requires sentence-transformers)
6. AI-assisted verification for ambiguous cases (Phase 5)

Relationship types:
- identical_creative: exact same creative asset
- identical_product: same physical product, different creative
- product_variant: variant (size, color)
- similar_category: same category, different product

Every match includes: evidence, similarity score, confidence, reversible merge history.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
from typing import Optional
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

import httpx
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Advertisement,
    Creative,
    CreativeFingerprint,
    Product,
    ProductCluster,
    ProductClusterMember,
    ProductMergeHistory,
    RelationshipType,
    ConfidenceLevel,
    DataSourceType,
)

logger = logging.getLogger(__name__)

# ─── Perceptual Hashing ─────────────────────────────────────────────────────

try:
    from PIL import Image
    import imagehash
    HAS_IMAGE_LIBS = True
except ImportError:
    HAS_IMAGE_LIBS = False
    logger.warning("PIL/imagehash not installed; image fingerprinting disabled")


def compute_file_hash(data: bytes) -> str:
    """SHA-256 hash of raw image bytes."""
    return hashlib.sha256(data).hexdigest()


def compute_perceptual_hash(data: bytes, method: str = "phash") -> Optional[str]:
    """Compute perceptual hash from image bytes."""
    if not HAS_IMAGE_LIBS:
        return None
    try:
        img = Image.open(io.BytesIO(data))
        if method == "phash":
            h = imagehash.phash(img)
        elif method == "dhash":
            h = imagehash.dhash(img)
        elif method == "whash":
            h = imagehash.whash(img)
        elif method == "average_hash":
            h = imagehash.average_hash(img)
        else:
            h = imagehash.phash(img)
        return str(h)
    except Exception as e:
        logger.warning("Failed to compute %s: %s", method, e)
        return None


def hamming_distance(hash_a: str, hash_b: str) -> int:
    """Hamming distance between two hex-encoded hashes."""
    if len(hash_a) != len(hash_b):
        return 999
    # Convert hex to binary
    try:
        a = int(hash_a, 16)
        b = int(hash_b, 16)
        return bin(a ^ b).count("1")
    except ValueError:
        return 999


# ─── URL Normalization ───────────────────────────────────────────────────────

def normalize_url(url: str) -> str:
    """Normalize a URL by removing tracking params and fragments."""
    if not url:
        return ""
    try:
        parsed = urlparse(url.lower().strip())
        # Remove common tracking params
        tracking_params = {
            "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
            "fbclid", "gclid", "ref", "source", "mc_cid", "mc_eid", "dclid",
            "msclkid", "twclid", "li_fat_id",
        }
        if parsed.query:
            params = parse_qs(parsed.query)
            cleaned = {k: v for k, v in params.items() if k not in tracking_params}
            query = urlencode(cleaned, doseq=True) if cleaned else ""
        else:
            query = ""
        # Remove fragment, trailing slash
        path = parsed.path.rstrip("/") or "/"
        domain = parsed.netloc.replace("www.", "")
        return urlunparse((parsed.scheme, domain, path, "", query, ""))
    except Exception:
        return url.lower().strip()


# ─── Title Normalization ─────────────────────────────────────────────────────

STOP_WORDS = {
    "the", "a", "an", "and", "or", "for", "of", "in", "on", "at", "to", "is", "it",
    "with", "by", "from", "as", "new", "free", "shipping", "sale", "hot",
    "buy", "get", "best", "top", "premium", "pro", "ultra", "super",
    "limited", "edition", "exclusive", "official",
}


def normalize_product_title(title: str) -> str:
    """Normalize product title for matching.
    
    Removes punctuation, stop words, excess whitespace, and lowercases.
    Does NOT strip meaningful descriptors like size, color, quantity.
    """
    if not title:
        return ""
    text = title.lower().strip()
    # Remove emojis and special chars but keep alphanumeric + spaces + hyphens
    text = re.sub(r'[^\w\s\-]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove stop words
    words = [w for w in text.split() if w not in STOP_WORDS and len(w) > 1]
    return " ".join(words)


# ─── Fingerprinting Engine ──────────────────────────────────────────────────

class FingerprintEngine:
    """Multi-layer creative and product fingerprinting."""

    # Thresholds (configurable)
    PHASH_IDENTICAL_THRESHOLD = 4        # hamming dist <= 4 → same creative
    PHASH_SIMILAR_THRESHOLD = 10         # 5-10 → similar product
    TITLE_EXACT_MATCH = True
    
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Layer 1: URL Matching ────────────────────────────────────────────

    async def find_url_duplicates(self, product_id: str) -> list[dict]:
        """Find products that share the same normalized URL."""
        product = await self.db.get(Product, product_id)
        if not product or not product.source_url:
            return []

        norm_url = normalize_url(product.source_url)
        result = await self.db.execute(
            select(Product).where(
                Product.id != product_id,
                Product.source_url.isnot(None),
            )
        )
        matches = []
        for other in result.scalars().all():
            if normalize_url(other.source_url) == norm_url:
                matches.append({
                    "product_id": other.id,
                    "product_name": other.name,
                    "match_type": "url",
                    "similarity": 1.0,
                    "confidence": ConfidenceLevel.HIGH,
                    "relationship": RelationshipType.IDENTICAL_PRODUCT,
                    "evidence": {"normalized_url": norm_url},
                })
        return matches

    # ── Layer 2: Title Matching ──────────────────────────────────────────

    async def find_title_duplicates(self, product_id: str) -> list[dict]:
        """Find products with identical normalized titles."""
        product = await self.db.get(Product, product_id)
        if not product:
            return []

        norm_title = normalize_product_title(product.name)
        if len(norm_title) < 5:
            return []

        result = await self.db.execute(
            select(Product).where(
                Product.id != product_id,
            )
        )
        matches = []
        for other in result.scalars().all():
            other_norm = normalize_product_title(other.name)
            if other_norm == norm_title and len(other_norm) >= 5:
                matches.append({
                    "product_id": other.id,
                    "product_name": other.name,
                    "match_type": "title_exact",
                    "similarity": 1.0,
                    "confidence": ConfidenceLevel.HIGH,
                    "relationship": RelationshipType.IDENTICAL_PRODUCT,
                    "evidence": {
                        "normalized_title": norm_title,
                        "original_a": product.name,
                        "original_b": other.name,
                    },
                })
        return matches

    # ── Layer 3: Image Perceptual Hashing ────────────────────────────────

    async def fingerprint_creative(self, creative_id: str, image_data: bytes) -> Creative:
        """Compute and store fingerprints for a creative asset."""
        creative = await self.db.get(Creative, creative_id)
        if not creative:
            raise ValueError(f"Creative not found: {creative_id}")

        # SHA-256
        file_hash = compute_file_hash(image_data)
        creative.file_hash = file_hash

        # pHash
        phash = compute_perceptual_hash(image_data, "phash")
        if phash:
            creative.perceptual_hash = phash
            # Store fingerprint record
            fp = CreativeFingerprint(
                creative_id=creative_id,
                fingerprint_type="phash",
                fingerprint_value=phash,
                algorithm_version="v1",
            )
            self.db.add(fp)

        # dHash
        dhash = compute_perceptual_hash(image_data, "dhash")
        if dhash:
            fp = CreativeFingerprint(
                creative_id=creative_id,
                fingerprint_type="dhash",
                fingerprint_value=dhash,
                algorithm_version="v1",
            )
            self.db.add(fp)

        # Image dimensions
        if HAS_IMAGE_LIBS:
            try:
                img = Image.open(io.BytesIO(image_data))
                creative.width, creative.height = img.size
            except Exception:
                pass

        await self.db.flush()
        return creative

    async def find_visual_duplicates(self, creative_id: str) -> list[dict]:
        """Find creatives with similar perceptual hashes."""
        creative = await self.db.get(Creative, creative_id)
        if not creative or not creative.perceptual_hash:
            return []

        target_hash = creative.perceptual_hash

        # Get all other creatives with perceptual hashes
        result = await self.db.execute(
            select(Creative).where(
                Creative.id != creative_id,
                Creative.perceptual_hash.isnot(None),
            )
        )
        matches = []
        for other in result.scalars().all():
            dist = hamming_distance(target_hash, other.perceptual_hash)

            if dist <= self.PHASH_IDENTICAL_THRESHOLD:
                matches.append({
                    "creative_id": other.id,
                    "advertisement_id": other.advertisement_id,
                    "match_type": "phash_identical",
                    "hamming_distance": dist,
                    "similarity": 1.0 - (dist / 64),
                    "confidence": ConfidenceLevel.HIGH,
                    "relationship": RelationshipType.IDENTICAL_CREATIVE,
                })
            elif dist <= self.PHASH_SIMILAR_THRESHOLD:
                matches.append({
                    "creative_id": other.id,
                    "advertisement_id": other.advertisement_id,
                    "match_type": "phash_similar",
                    "hamming_distance": dist,
                    "similarity": 1.0 - (dist / 64),
                    "confidence": ConfidenceLevel.MEDIUM,
                    "relationship": RelationshipType.PRODUCT_VARIANT,
                })

        return matches

    async def find_exact_file_duplicates(self, creative_id: str) -> list[dict]:
        """Find creatives with identical SHA-256 file hash."""
        creative = await self.db.get(Creative, creative_id)
        if not creative or not creative.file_hash:
            return []

        result = await self.db.execute(
            select(Creative).where(
                Creative.id != creative_id,
                Creative.file_hash == creative.file_hash,
            )
        )
        return [
            {
                "creative_id": other.id,
                "advertisement_id": other.advertisement_id,
                "match_type": "file_hash_exact",
                "similarity": 1.0,
                "confidence": ConfidenceLevel.HIGH,
                "relationship": RelationshipType.IDENTICAL_CREATIVE,
            }
            for other in result.scalars().all()
        ]

    # ── Combined Duplicate Scan ──────────────────────────────────────────

    async def scan_product_duplicates(self, product_id: str) -> list[dict]:
        """Run all matching layers and return combined candidates.
        
        These are CANDIDATES — they must be reviewed before merging.
        """
        all_matches: dict[str, dict] = {}

        # Layer 1: URL
        for m in await self.find_url_duplicates(product_id):
            key = m["product_id"]
            if key not in all_matches or m["similarity"] > all_matches[key]["similarity"]:
                all_matches[key] = m

        # Layer 2: Title
        for m in await self.find_title_duplicates(product_id):
            key = m["product_id"]
            if key not in all_matches:
                all_matches[key] = m
            else:
                # Boost confidence when multiple layers agree
                all_matches[key]["confidence"] = ConfidenceLevel.HIGH
                all_matches[key]["evidence"] = {
                    **(all_matches[key].get("evidence") or {}),
                    **(m.get("evidence") or {}),
                    "multi_layer_match": True,
                }

        return sorted(all_matches.values(), key=lambda x: x["similarity"], reverse=True)


# ─── Product Clustering Service ──────────────────────────────────────────────

class ClusteringService:
    """Manages product clusters with manual review workflow."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.fingerprint = FingerprintEngine(db)

    async def propose_cluster(self, product_id: str) -> list[dict]:
        """Find duplicate candidates and return them for review.
        
        Does NOT auto-merge. Returns candidates that the operator must accept or reject.
        """
        return await self.fingerprint.scan_product_duplicates(product_id)

    async def create_cluster(
        self,
        name: str,
        canonical_product_id: str,
        member_ids: list[str],
        relationship_type: RelationshipType = RelationshipType.IDENTICAL_PRODUCT,
        reviewed_by: str = "operator",
    ) -> ProductCluster:
        """Create a cluster from reviewed matches."""
        cluster = ProductCluster(
            name=name,
            canonical_product_id=canonical_product_id,
            cluster_confidence=ConfidenceLevel.HIGH,
            is_reviewed=True,
            reviewed_by=reviewed_by,
        )
        self.db.add(cluster)
        await self.db.flush()

        # Add canonical product as member
        canonical_member = ProductClusterMember(
            cluster_id=cluster.id,
            product_id=canonical_product_id,
            relationship_type=relationship_type,
            similarity_score=1.0,
            confidence=ConfidenceLevel.HIGH,
        )
        self.db.add(canonical_member)

        # Add other members
        for pid in member_ids:
            if pid == canonical_product_id:
                continue
            member = ProductClusterMember(
                cluster_id=cluster.id,
                product_id=pid,
                relationship_type=relationship_type,
                confidence=ConfidenceLevel.MEDIUM,
            )
            self.db.add(member)

            # Record merge history
            history = ProductMergeHistory(
                action="merge",
                source_product_id=pid,
                target_product_id=canonical_product_id,
                cluster_id=cluster.id,
                reason=f"Manual cluster creation by {reviewed_by}",
                performed_by=reviewed_by,
            )
            self.db.add(history)

        await self.db.flush()
        return cluster

    async def split_from_cluster(
        self,
        product_id: str,
        cluster_id: str,
        reason: str = "",
        performed_by: str = "operator",
    ) -> None:
        """Remove a product from a cluster (reversible split)."""
        result = await self.db.execute(
            select(ProductClusterMember).where(
                ProductClusterMember.cluster_id == cluster_id,
                ProductClusterMember.product_id == product_id,
            )
        )
        member = result.scalar_one_or_none()
        if member:
            await self.db.delete(member)

            history = ProductMergeHistory(
                action="split",
                source_product_id=product_id,
                cluster_id=cluster_id,
                reason=reason,
                performed_by=performed_by,
            )
            self.db.add(history)
            await self.db.flush()

    async def scan_all_products(self) -> list[dict]:
        """Scan all products for potential duplicates. Returns candidate pairs."""
        result = await self.db.execute(
            select(Product.id).where(Product.target_country == "US")
        )
        product_ids = [row[0] for row in result.all()]

        all_candidates = []
        seen_pairs = set()

        for pid in product_ids:
            candidates = await self.propose_cluster(pid)
            for c in candidates:
                pair = tuple(sorted([pid, c["product_id"]]))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    all_candidates.append({
                        "product_a_id": pid,
                        "product_b_id": c["product_id"],
                        "product_b_name": c["product_name"],
                        **c,
                    })

        return sorted(all_candidates, key=lambda x: x["similarity"], reverse=True)

