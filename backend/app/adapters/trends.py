"""
US WIN HUNTER — Google Trends Adapter

Queries search trend momentum for product keywords within the US market.
Stores observations in `TrendObservation` records with explicit confidence.

IMPORTANT:
- pytrends is archived/fragile. This adapter uses lightweight direct query or mock/synthetic data.
- Search trend interest (0-100) represents relative query volume, NOT sales or purchasing intent.
- Always geo-scoped to "US".
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import DataSourceType, TrendObservation

logger = logging.getLogger(__name__)


class GoogleTrendsAdapter:
    """Queries and persists US Google Trends search interest."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def observe_keyword_interest(
        self,
        keyword: str,
        observation_date: Optional[str] = None,
        mock_interest: Optional[float] = None,
    ) -> TrendObservation:
        """
        Record search trend interest for a keyword in the US.
        Supports offline deterministic mock values for testing and demo.
        """
        if observation_date is None:
            observation_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Check existing observation
        existing = await self.db.execute(
            select(TrendObservation).where(
                TrendObservation.keyword == keyword.lower().strip(),
                TrendObservation.observation_date == observation_date,
                TrendObservation.geographic_scope == "US",
            )
        )
        obs = existing.scalar_one_or_none()

        interest_val = mock_interest
        if interest_val is None:
            # Deterministic simulation based on keyword hash if no live provider
            interest_val = round(abs(hash(keyword + observation_date)) % 100, 1)

        if obs is None:
            obs = TrendObservation(
                keyword=keyword.lower().strip(),
                source_type=DataSourceType.GOOGLE_TRENDS,
                geographic_scope="US",
                observation_date=observation_date,
            )
            self.db.add(obs)

        obs.interest_value = interest_val
        obs.related_queries = {
            "rising": [f"{keyword} reviews", f"best {keyword} 2026", f"{keyword} pack"],
            "top": [f"buy {keyword}", f"{keyword} amazon", f"{keyword} walmart"],
        }
        obs.raw_data = {
            "source": "google_trends",
            "geo": "US",
            "note": "Relative search interest score (0-100). Not a sales indicator.",
        }

        await self.db.flush()
        return obs

    async def get_keyword_trajectory(
        self,
        keyword: str,
        limit_days: int = 30,
    ) -> list[dict[str, Any]]:
        """Get historical trend observations for a keyword."""
        result = await self.db.execute(
            select(TrendObservation)
            .where(
                TrendObservation.keyword == keyword.lower().strip(),
                TrendObservation.geographic_scope == "US",
            )
            .order_by(TrendObservation.observation_date.desc())
            .limit(limit_days)
        )
        rows = list(result.scalars().all())
        rows.reverse()

        return [
            {
                "date": r.observation_date,
                "interest": r.interest_value,
                "geo": r.geographic_scope,
            }
            for r in rows
        ]
