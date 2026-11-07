"""
US WIN HUNTER — Engine D: Pain Discovery Service

Analyzes public US consumer discussions, reviews, and complaints.
Clusters them across five key language groups:
1. complaints
2. failed_workarounds
3. purchase_intent
4. product_replacements
5. product_failures

Generates actionable product hypotheses, problem definitions, and search keywords.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    ConfidenceLevel,
    DataSourceType,
    EvidenceType,
    PainCluster,
    PainEvidence,
    PainLanguageGroup,
)

logger = logging.getLogger(__name__)


class PainDiscoveryService:
    """Engine D: Pain point extraction, language grouping, and clustering."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def import_evidence_and_cluster(
        self,
        cluster_name: str,
        core_problem: str,
        category: Optional[str],
        evidence_items: list[dict[str, Any]],
        product_hypotheses: Optional[list[str]] = None,
        search_keywords: Optional[list[str]] = None,
    ) -> PainCluster:
        """
        Create or update a PainCluster and ingest supporting evidence items.
        """
        existing = await self.db.execute(
            select(PainCluster).where(PainCluster.name == cluster_name)
        )
        cluster = existing.scalar_one_or_none()

        if cluster is None:
            cluster = PainCluster(
                name=cluster_name,
                core_problem=core_problem,
                category=category,
                us_relevance_confidence=ConfidenceLevel.HIGH,
            )
            self.db.add(cluster)
            await self.db.flush()

        # Update metadata
        cluster.product_hypotheses = {"hypotheses": product_hypotheses or []}
        cluster.search_keywords = {"keywords": search_keywords or []}

        # Ingest evidence items
        distinct_sources = set()
        distinct_authors = set()

        for item in evidence_items:
            lang_group = self._classify_language_group(item.get("content_excerpt", ""))
            if "language_group" in item and item["language_group"]:
                try:
                    lang_group = PainLanguageGroup(item["language_group"])
                except ValueError:
                    pass

            source_type = DataSourceType.MANUAL_IMPORT
            if "source_type" in item:
                try:
                    source_type = DataSourceType(item["source_type"])
                except ValueError:
                    pass

            evidence = PainEvidence(
                cluster_id=cluster.id,
                source_type=source_type,
                language_group=lang_group,
                source_url=item.get("source_url"),
                author_id=item.get("author_id"),
                content_excerpt=item.get("content_excerpt", ""),
                geographic_context=item.get("geographic_context", "US"),
                sentiment_score=float(item.get("sentiment_score", -0.5)),
                evidence_type=EvidenceType.OBSERVED_FACT,
            )
            self.db.add(evidence)

            if evidence.source_url:
                distinct_sources.add(evidence.source_url)
            if evidence.author_id:
                distinct_authors.add(evidence.author_id)

        cluster.distinct_source_count = max(cluster.distinct_source_count, len(distinct_sources))
        cluster.distinct_author_count = max(cluster.distinct_author_count, len(distinct_authors))
        cluster.frequency_score = min(100.0, len(evidence_items) * 15.0)
        cluster.recency_score = 90.0

        await self.db.flush()
        return cluster

    def _classify_language_group(self, text: str) -> PainLanguageGroup:
        """Heuristically assign text to one of the 5 language groups."""
        t = text.lower()

        if any(w in t for w in ["broke", "failed", "stopped working", "cheap plastic", "fell apart", "ripped"]):
            return PainLanguageGroup.PRODUCT_FAILURE
        if any(w in t for w in ["tried using", "taped it", "workaround", "diy", "rigged", "temporary fix"]):
            return PainLanguageGroup.FAILED_WORKAROUND
        if any(w in t for w in ["looking for", "want to buy", "need a good", "where can i get", "recommend"]):
            return PainLanguageGroup.PURCHASE_INTENT
        if any(w in t for w in ["replacing my", "switched from", "better alternative", "threw away my"]):
            return PainLanguageGroup.PRODUCT_REPLACEMENT
        return PainLanguageGroup.COMPLAINT

    async def list_clusters(
        self,
        category: Optional[str] = None,
        min_evidence: int = 0,
    ) -> list[dict[str, Any]]:
        """List pain clusters with evidence counts and top keywords."""
        query = select(PainCluster)
        if category:
            query = query.where(PainCluster.category == category)
        query = query.order_by(PainCluster.frequency_score.desc())

        result = await self.db.execute(query)
        clusters = list(result.scalars().all())

        out = []
        for c in clusters:
            evidence_count = (await self.db.execute(
                select(func.count(PainEvidence.id)).where(PainEvidence.cluster_id == c.id)
            )).scalar() or 0

            if evidence_count >= min_evidence:
                out.append({
                    "id": c.id,
                    "name": c.name,
                    "core_problem": c.core_problem,
                    "category": c.category,
                    "distinct_sources": c.distinct_source_count,
                    "distinct_authors": c.distinct_author_count,
                    "frequency_score": c.frequency_score,
                    "evidence_count": evidence_count,
                    "hypotheses": c.product_hypotheses.get("hypotheses", []) if c.product_hypotheses else [],
                    "keywords": c.search_keywords.get("keywords", []) if c.search_keywords else [],
                    "us_confidence": c.us_relevance_confidence.value,
                })
        return out

    async def get_cluster_detail(self, cluster_id: str) -> Optional[dict[str, Any]]:
        """Get full cluster with categorized evidence items."""
        cluster = await self.db.get(PainCluster, cluster_id)
        if not cluster:
            return None

        result = await self.db.execute(
            select(PainEvidence).where(PainEvidence.cluster_id == cluster_id)
        )
        evidence_list = list(result.scalars().all())

        return {
            "id": cluster.id,
            "name": cluster.name,
            "core_problem": cluster.core_problem,
            "category": cluster.category,
            "frequency_score": cluster.frequency_score,
            "recency_score": cluster.recency_score,
            "hypotheses": cluster.product_hypotheses.get("hypotheses", []) if cluster.product_hypotheses else [],
            "keywords": cluster.search_keywords.get("keywords", []) if cluster.search_keywords else [],
            "us_confidence": cluster.us_relevance_confidence.value,
            "evidence": [
                {
                    "id": e.id,
                    "language_group": e.language_group.value,
                    "content": e.content_excerpt,
                    "source_url": e.source_url,
                    "source_type": e.source_type.value,
                    "geographic_context": e.geographic_context,
                    "sentiment": e.sentiment_score,
                }
                for e in evidence_list
            ],
        }
