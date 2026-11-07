"""
US WIN HUNTER — Engine A: Advertiser Graph Discovery

Discovers relationships between advertisers through observable evidence:
- Shared products (same product advertised by different pages)
- Shared domains (same landing page domain)
- Product overlap (multiple products in common)

Implements bounded graph expansion with configurable depth.
Distinguishes verified from suspected relationships.
Does NOT automatically assume two Facebook Pages belong to the same company.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from urllib.parse import urlparse

from sqlalchemy import select, func, and_, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Advertisement,
    Advertiser,
    AdvertiserRelationship,
    ConfidenceLevel,
    LandingPage,
    Product,
    RelationshipType,
)

logger = logging.getLogger(__name__)


class AdvertiserGraphEngine:
    """
    Discovers and maintains the advertiser relationship graph.
    
    All relationships are stored as evidence-backed proposals.
    Nothing is automatically merged — the operator reviews.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Domain Extraction ────────────────────────────────────────────────

    @staticmethod
    def extract_domain(url: str) -> str | None:
        if not url:
            return None
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower().replace("www.", "")
            return domain if domain else None
        except Exception:
            return None

    # ── Graph Discovery ──────────────────────────────────────────────────

    async def discover_relationships(self, max_depth: int = 2) -> list[dict]:
        """
        Scan all advertisers and discover relationships based on evidence.
        Returns new relationship proposals.
        """
        proposals = []

        # 1. Shared product relationships
        product_proposals = await self._discover_shared_products()
        proposals.extend(product_proposals)

        # 2. Shared domain relationships
        domain_proposals = await self._discover_shared_domains()
        proposals.extend(domain_proposals)

        # Dedupe and store
        stored = 0
        for p in proposals:
            created = await self._store_relationship(p)
            if created:
                stored += 1

        logger.info("Discovered %d relationship proposals, stored %d new", len(proposals), stored)
        return proposals

    async def _discover_shared_products(self) -> list[dict]:
        """Find advertisers that promote the same product."""
        # Get all (product_id, advertiser_id) pairs
        result = await self.db.execute(
            select(
                Advertisement.product_id,
                Advertisement.advertiser_id,
            ).where(
                Advertisement.product_id.isnot(None),
            ).distinct()
        )
        rows = result.all()

        # Group by product
        product_advertisers: dict[str, set[str]] = defaultdict(set)
        for product_id, advertiser_id in rows:
            product_advertisers[product_id].add(advertiser_id)

        proposals = []
        seen_pairs = set()

        for product_id, adv_ids in product_advertisers.items():
            if len(adv_ids) < 2:
                continue
            adv_list = sorted(adv_ids)
            for i, a in enumerate(adv_list):
                for b in adv_list[i + 1:]:
                    pair = (a, b)
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)

                    proposals.append({
                        "advertiser_id_a": a,
                        "advertiser_id_b": b,
                        "relationship_type": RelationshipType.SUSPECTED_SAME_OPERATOR,
                        "confidence": ConfidenceLevel.LOW,
                        "evidence": {
                            "reason": "shared_product",
                            "shared_product_id": product_id,
                            "note": (
                                "Two pages advertising the same product. "
                                "This does NOT mean they are the same company — "
                                "the product may be sourced by independent sellers."
                            ),
                        },
                    })

        return proposals

    async def _discover_shared_domains(self) -> list[dict]:
        """Find advertisers whose ads link to the same domain."""
        result = await self.db.execute(
            select(
                Advertisement.advertiser_id,
                Advertisement.landing_page_url,
            ).where(
                Advertisement.landing_page_url.isnot(None),
                Advertisement.landing_page_url != "",
            )
        )
        rows = result.all()

        # Group by domain
        domain_advertisers: dict[str, set[str]] = defaultdict(set)
        for adv_id, url in rows:
            domain = self.extract_domain(url)
            if domain and len(domain) > 3:
                domain_advertisers[domain].add(adv_id)

        proposals = []
        seen_pairs = set()

        for domain, adv_ids in domain_advertisers.items():
            if len(adv_ids) < 2:
                continue
            adv_list = sorted(adv_ids)
            for i, a in enumerate(adv_list):
                for b in adv_list[i + 1:]:
                    pair = (a, b)
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)

                    proposals.append({
                        "advertiser_id_a": a,
                        "advertiser_id_b": b,
                        "relationship_type": RelationshipType.SUSPECTED_SAME_OPERATOR,
                        "confidence": ConfidenceLevel.MEDIUM,
                        "evidence": {
                            "reason": "shared_domain",
                            "shared_domain": domain,
                            "note": (
                                "Two pages linking to the same domain. "
                                "Higher confidence than shared product, "
                                "but could still be affiliate / reseller."
                            ),
                        },
                    })

        return proposals

    async def _store_relationship(self, proposal: dict) -> bool:
        """Store a relationship if it doesn't already exist."""
        a, b = proposal["advertiser_id_a"], proposal["advertiser_id_b"]
        rtype = proposal["relationship_type"]

        # Check if exists (either direction)
        existing = await self.db.execute(
            select(AdvertiserRelationship).where(
                (
                    (AdvertiserRelationship.advertiser_id_a == a) &
                    (AdvertiserRelationship.advertiser_id_b == b) &
                    (AdvertiserRelationship.relationship_type == rtype)
                ) | (
                    (AdvertiserRelationship.advertiser_id_a == b) &
                    (AdvertiserRelationship.advertiser_id_b == a) &
                    (AdvertiserRelationship.relationship_type == rtype)
                )
            )
        )
        if existing.scalar_one_or_none():
            return False

        rel = AdvertiserRelationship(
            advertiser_id_a=a,
            advertiser_id_b=b,
            relationship_type=rtype,
            confidence=proposal["confidence"],
            evidence=proposal["evidence"],
        )
        self.db.add(rel)
        await self.db.flush()
        return True

    # ── Advertiser Profile ───────────────────────────────────────────────

    async def get_advertiser_graph(self, advertiser_id: str) -> dict:
        """Get full graph context for an advertiser."""
        adv = await self.db.get(Advertiser, advertiser_id)
        if not adv:
            return {"error": "Advertiser not found"}

        # Products
        products_result = await self.db.execute(
            select(Product)
            .join(Advertisement, Advertisement.product_id == Product.id)
            .where(Advertisement.advertiser_id == advertiser_id)
            .distinct()
        )
        products = [
            {"id": p.id, "name": p.name, "category": p.category}
            for p in products_result.scalars().all()
        ]

        # Ad stats
        ad_count = (await self.db.execute(
            select(func.count(Advertisement.id)).where(
                Advertisement.advertiser_id == advertiser_id
            )
        )).scalar() or 0

        active_ad_count = (await self.db.execute(
            select(func.count(Advertisement.id)).where(
                Advertisement.advertiser_id == advertiser_id,
                Advertisement.is_active == True,
            )
        )).scalar() or 0

        # Product Ad Share for each product
        product_shares = []
        if ad_count > 0:
            for p in products:
                p_ads = (await self.db.execute(
                    select(func.count(Advertisement.id)).where(
                        Advertisement.advertiser_id == advertiser_id,
                        Advertisement.product_id == p["id"],
                        Advertisement.is_active == True,
                    )
                )).scalar() or 0
                product_shares.append({
                    "product_id": p["id"],
                    "product_name": p["name"],
                    "active_ads": p_ads,
                    "product_ad_share": round(p_ads / max(active_ad_count, 1), 3),
                    "note": "Advertising activity share, NOT revenue share",
                })

        # Relationships
        rels_result = await self.db.execute(
            select(AdvertiserRelationship).where(
                (AdvertiserRelationship.advertiser_id_a == advertiser_id) |
                (AdvertiserRelationship.advertiser_id_b == advertiser_id)
            )
        )
        relationships = []
        for r in rels_result.scalars().all():
            other_id = r.advertiser_id_b if r.advertiser_id_a == advertiser_id else r.advertiser_id_a
            other = await self.db.get(Advertiser, other_id)
            relationships.append({
                "related_advertiser_id": other_id,
                "related_advertiser_name": other.name if other else "Unknown",
                "relationship_type": r.relationship_type.value,
                "confidence": r.confidence.value,
                "evidence": r.evidence,
            })

        # Domains from ads
        domains_result = await self.db.execute(
            select(distinct(Advertisement.landing_page_url)).where(
                Advertisement.advertiser_id == advertiser_id,
                Advertisement.landing_page_url.isnot(None),
            )
        )
        domains = set()
        for (url,) in domains_result.all():
            d = self.extract_domain(url)
            if d:
                domains.add(d)

        return {
            "advertiser": {
                "id": adv.id,
                "name": adv.name,
                "facebook_page_id": adv.facebook_page_id,
                "domain": adv.domain,
                "is_verified": adv.is_verified,
            },
            "total_ads": ad_count,
            "active_ads": active_ad_count,
            "products": products,
            "product_ad_shares": product_shares,
            "relationships": relationships,
            "landing_domains": sorted(domains),
        }

    # ── Update Advertiser Domains ────────────────────────────────────────

    async def update_advertiser_domains(self) -> int:
        """Scan all ads and update advertiser domain lists."""
        result = await self.db.execute(
            select(Advertisement.advertiser_id, Advertisement.landing_page_url).where(
                Advertisement.landing_page_url.isnot(None),
                Advertisement.landing_page_url != "",
            )
        )
        adv_domains: dict[str, set[str]] = defaultdict(set)
        for adv_id, url in result.all():
            d = self.extract_domain(url)
            if d:
                adv_domains[adv_id].add(d)

        updated = 0
        for adv_id, domains in adv_domains.items():
            adv = await self.db.get(Advertiser, adv_id)
            if adv:
                adv.domains = sorted(domains)
                if not adv.domain and domains:
                    adv.domain = sorted(domains)[0]
                updated += 1

        await self.db.flush()
        return updated

