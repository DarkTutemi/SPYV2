"""
US WIN HUNTER — API Routes
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.advertisers import router as advertisers_router
from app.api.advertisements import router as advertisements_router
from app.api.products import router as products_router
from app.api.data_sources import router as data_sources_router
from app.api.import_export import router as import_router
from app.api.health import router as health_router
from app.api.scores import router as scores_router
from app.api.bundles import router as bundles_router
from app.api.pain import router as pain_router
from app.api.clusters import router as clusters_router
from app.api.temporal import router as temporal_router
from app.api.alerts import router as alerts_router

router = APIRouter()

router.include_router(health_router, prefix="/health", tags=["Health"])
router.include_router(data_sources_router, prefix="/sources", tags=["Data Sources"])
router.include_router(import_router, prefix="/import", tags=["Import"])
router.include_router(advertisers_router, prefix="/advertisers", tags=["Advertisers"])
router.include_router(advertisements_router, prefix="/advertisements", tags=["Advertisements"])
router.include_router(products_router, prefix="/products", tags=["Products"])
router.include_router(scores_router, prefix="/scores", tags=["Scores"])
router.include_router(bundles_router, prefix="/bundles", tags=["Bundles"])
router.include_router(pain_router, prefix="/pain", tags=["Pain Discovery"])
router.include_router(clusters_router, prefix="/clusters", tags=["Clusters"])
router.include_router(temporal_router, prefix="/temporal", tags=["Temporal Intelligence"])
router.include_router(alerts_router, prefix="/alerts", tags=["Alerts & Scheduler"])

