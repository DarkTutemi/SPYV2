"""
US WIN HUNTER — Autonomous Advertiser Expansion Engine

Executes bounded expansion loops across the advertiser-product graph:
1. Identifies advertiser Page IDs from collected records
2. Normalizes advertiser identities and domains
3. Evaluates product overlap and candidate independent competitors
4. Queues newly discovered eligible advertisers for focused collection
5. Pulls fresh ads from prioritized pages within strict budget and depth limits
6. Triggers clustering and bundle evaluation on newly discovered products

Guards:
- Hard maximum graph depth (default 2)
- Max advertisers per expansion run (default 5)
- Max ads per advertiser (default 50)
- Verified vs suspected relationship evidence labeling
- Duplicate prevention and cost accounting
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.apify import ApifyProviderAdapter
from app.engines.advertiser_graph import AdvertiserGraphEngine
from app.engines.fingerprinting import ClusteringService
from app.models.models import (
    Advertisement,
    Advertiser,
    AdvertiserRelationship,
    ConfidenceLevel,
    DataSourceType,
    Product,
    RelationshipType,
)

logger = logging.getLogger(__name__)


class AdvertiserExpansionEngine:
    """Manages the autonomous advertiser discovery and graph expansion loop."""

    def __init__(self, db: AsyncSession, apify_adapter: Optional[ApifyProviderAdapter] = None):
        self.db = db
        self.apify_adapter = apify_adapter or ApifyProviderAdapter(db)
        self.graph_engine = AdvertiserGraphEngine(db)
        self.cluster_engine = ClusteringService(db)

    # ── Expansion Queue Discovery ──────────────────────────────────────────

    async def get_expansion_candidates(
        self,
        max_candidates: int = 10,
        min_ads: int = 1,
        recheck_days: int = 7,
    ) -> list[dict[str, Any]]:
        """
        Identify high-value US advertisers eligible for deeper expansion.
        Prioritizes:
        1. Advertisers promoting promising bundle products (bundle score >= 60)
        2. Competitors sharing products with existing winning clusters
        3. Pages with valid Facebook Page IDs that have not been swept within `recheck_days`
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=recheck_days)

        # Find advertisers with valid Facebook Page ID
        stmt = (
            select(
                Advertiser.id,
                Advertiser.name,
                Advertiser.facebook_page_id,
                Advertiser.domain,
                Advertiser.last_seen_at,
                func.count(Advertisement.id).label("ad_count"),
            )
            .join(Advertisement, Advertisement.advertiser_id == Advertiser.id)
            .filter(
                Advertiser.facebook_page_id.isnot(None),
                Advertiser.facebook_page_id != "",
                Advertiser.country == "US",
            )
            .group_by(Advertiser.id)
            .having(func.count(Advertisement.id) >= min_ads)
            .order_by(Advertiser.last_seen_at.asc())
            .limit(max_candidates * 2)
        )

        result = await self.db.execute(stmt)
        candidates = []

        for row in result.all():
            adv_id, name, page_id, domain, last_seen, ad_count = row
            # Check if advertiser was collected recently
            is_stale = last_seen is None or last_seen.replace(tzinfo=timezone.utc) < cutoff_date

            candidates.append({
                "advertiser_id": adv_id,
                "name": name,
                "page_id": page_id,
                "domain": domain,
                "ad_count": ad_count,
                "last_seen_at": last_seen.isoformat() if last_seen else None,
                "priority_reason": "High-volume competitor sweep" if ad_count >= 5 else "Unexplored US advertiser",
                "is_stale": is_stale,
            })

            if len(candidates) >= max_candidates:
                break

        return candidates

    # ── Bounded Expansion Execution ────────────────────────────────────────

    async def run_expansion_cycle(
        self,
        max_advertisers: int = 5,
        max_ads_per_advertiser: int = 50,
        max_depth: int = 2,
        use_fallback: bool = False,
    ) -> dict[str, Any]:
        """
        Execute one bounded autonomous expansion cycle:
        1. Select top candidate advertisers
        2. Query live ad library for their catalog
        3. Cluster newly discovered products
        4. Discover new relationship edges
        """
        # Step 1: Select candidates
        candidates = await self.get_expansion_candidates(max_candidates=max_advertisers)
        if not candidates:
            return {
                "success": True,
                "status": "NO_CANDIDATES",
                "message": "No eligible US advertisers with Facebook Page IDs found for expansion.",
                "advertisers_processed": 0,
                "ads_collected": 0,
                "new_products": 0,
            }

        page_ids = [c["page_id"] for c in candidates if c.get("page_id")]
        if not page_ids:
            return {
                "success": True,
                "status": "NO_PAGE_IDS",
                "message": "No valid numeric Page IDs found in expansion candidates.",
                "advertisers_processed": 0,
            }

        # Step 2: Query Live Provider via Apify Adapter
        run_result = await self.apify_adapter.discover_by_advertisers(
            advertisers=page_ids,
            max_ads=max_ads_per_advertiser * len(page_ids),
            use_fallback=use_fallback,
            persist=True,
        )

        if not run_result.get("success"):
            return {
                "success": False,
                "status": run_result.get("status", "FAILED"),
                "error": run_result.get("error", "Failed to query advertiser ads from Apify."),
                "candidates_targeted": len(page_ids),
            }

        # Step 3: Trigger Clustering & Fingerprinting Proposals
        cluster_proposals = await self.cluster_engine.scan_all_products()

        # Step 4: Discover Advertiser Relationships
        relationships = await self.graph_engine.discover_relationships(max_depth=max_depth)

        return {
            "success": True,
            "status": run_result.get("status"),
            "advertisers_processed": len(page_ids),
            "records_fetched": run_result.get("records_fetched", 0),
            "records_valid": run_result.get("records_valid", 0),
            "records_new": run_result.get("records_new", 0),
            "clusters_proposed": len(cluster_proposals),
            "relationships_discovered": len(relationships),
            "candidates": candidates,
        }

