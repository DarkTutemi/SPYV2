"""
US WIN HUNTER — Live Discovery API Routes

Endpoints for:
- Live discovery status, budget metrics, and provider health
- Triggering bounded live keyword discovery runs
- Taxonomy and seed query management
- Advertiser graph expansion queue inspection and execution
- Real-data Apify fixture ingestion
"""

from __future__ import annotations

from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.apify import ApifyProviderAdapter
from app.core.database import get_db
from app.engines.advertiser_expansion import AdvertiserExpansionEngine
from app.engines.seed_engine import DiscoverySeedEngine
from app.services.scheduler import get_scheduler

router = APIRouter(prefix="/discovery", tags=["Live Discovery"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class RunDiscoveryRequest(BaseModel):
    keywords: Optional[list[str]] = Field(default=None, description="Keywords to query in Meta Ad Library")
    category: Optional[str] = Field(default=None, description="Category name to pick top seeds from")
    max_ads: int = Field(default=50, ge=10, le=250, description="Max ads to scrape per query")
    use_fallback: bool = Field(default=False, description="Use curious_coder fallback actor instead of automation-lab")
    force: bool = Field(default=False, description="Bypass auto_collection_enabled guard for manual run")


class AddSeedRequest(BaseModel):
    keyword: str
    category: str
    source: str = "custom"
    reason: str = "Operator generated research seed"
    bundle_rationale: str = "Multi-unit purchase potential"
    target_bundle_units: list[int] = Field(default_factory=lambda: [3, 5])


class RunExpansionRequest(BaseModel):
    max_advertisers: int = Field(default=3, ge=1, le=10)
    max_ads_per_advertiser: int = Field(default=25, ge=10, le=100)
    use_fallback: bool = False


class ImportFixtureRequest(BaseModel):
    records: list[dict[str, Any]]
    actor_name: str = "automation-lab/facebook-ads-library"


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/status")
async def get_discovery_status(db: AsyncSession = Depends(get_db)):
    """Get live provider status, Apify credentials state, and spend metrics."""
    adapter = ApifyProviderAdapter(db)
    status = await adapter.get_status()
    scheduler = get_scheduler()
    status["scheduler_status"] = scheduler.status
    return status


@router.get("/seeds")
async def list_seeds(
    limit: int = Query(default=50, ge=1, le=200),
    category: Optional[str] = Query(default=None),
    only_uncollected: bool = Query(default=False),
):
    """List prioritized discovery seeds across the 10 US product categories."""
    seed_engine = DiscoverySeedEngine()
    seeds = seed_engine.get_prioritized_seeds(
        limit=limit,
        category=category,
        only_uncollected=only_uncollected,
    )
    return {"total": len(seeds), "seeds": seeds}


@router.post("/seeds")
async def add_seed(body: AddSeedRequest):
    """Add a new custom discovery query with bundle rationale."""
    seed_engine = DiscoverySeedEngine()
    seed = seed_engine.add_custom_seed(
        keyword=body.keyword,
        category=body.category,
        source=body.source,
        reason=body.reason,
        bundle_rationale=body.bundle_rationale,
        target_bundle_units=body.target_bundle_units,
    )
    return {"success": True, "seed": seed}


@router.post("/seeds/generate")
async def generate_seeds():
    """Regenerate default seeds from the 10 US product category taxonomy."""
    seed_engine = DiscoverySeedEngine()
    seeds = seed_engine.generate_taxonomy_seeds()
    return {"success": True, "generated_count": len(seeds), "total_seeds": len(seed_engine.seeds)}


@router.post("/run")
async def run_discovery(
    body: RunDiscoveryRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger an authorized, bounded live discovery run.
    Queries the live Meta Ad Library via the Apify adapter.
    """
    adapter = ApifyProviderAdapter(db)
    seed_engine = DiscoverySeedEngine()

    keywords = body.keywords
    if not keywords:
        # Pick top prioritized seed
        seeds = seed_engine.get_prioritized_seeds(limit=1, category=body.category)
        if not seeds:
            raise HTTPException(status_code=400, detail="No seeds available to query.")
        keywords = [seeds[0].keyword]

    result = await adapter.discover_by_keywords(
        keywords=keywords,
        max_ads=body.max_ads,
        use_fallback=body.use_fallback,
        persist=True,
    )

    if result.get("success"):
        fetched = result.get("records_fetched", 0)
        new_recs = result.get("records_new", 0)
        dupes = result.get("records_duplicate", 0)
        for kw in keywords:
            seed_engine.record_query_feedback(
                keyword=kw,
                total_fetched=fetched,
                unique_products=new_recs,
                new_advertisers=max(1, new_recs // 2) if new_recs else 0,
                duplicates=dupes,
                cost_usd=fetched * 0.0012,
            )

    return result


@router.get("/expansion/queue")
async def get_expansion_queue(
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """View top candidate US advertisers eligible for catalog expansion."""
    expansion_engine = AdvertiserExpansionEngine(db)
    candidates = await expansion_engine.get_expansion_candidates(max_candidates=limit)
    return {"total": len(candidates), "candidates": candidates}


@router.post("/expansion/run")
async def run_expansion(
    body: RunExpansionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Trigger bounded advertiser expansion loop."""
    expansion_engine = AdvertiserExpansionEngine(db)
    result = await expansion_engine.run_expansion_cycle(
        max_advertisers=body.max_advertisers,
        max_ads_per_advertiser=body.max_ads_per_advertiser,
        use_fallback=body.use_fallback,
    )
    return result


@router.post("/import-fixture")
async def import_real_fixture(
    body: ImportFixtureRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Import an authentic Apify dataset fixture directly into the live pipeline.
    Useful for testing, zero-cost development, and verified offline datasets.
    """
    adapter = ApifyProviderAdapter(db)
    normalized = adapter.normalize_records(body.records, body.actor_name)
    valid_records, validation_errors = adapter.validate_records(normalized)

    if not valid_records:
        return {
            "success": False,
            "error": "No valid US records passed quality gate validation.",
            "validation_errors": validation_errors,
        }

    # Persist via ImportService
    from app.services.import_service import ImportService
    from app.models.models import DataSourceType
    import_service = ImportService(db)
    import_res = await import_service.import_data(
        source_type=DataSourceType.META_AD_LIBRARY,
        data=valid_records,
        options={"is_synthetic": False},
    )

    return {
        "success": import_res.success,
        "records_received": len(body.records),
        "records_valid": len(valid_records),
        "records_new": import_res.records_new,
        "records_duplicate": import_res.records_duplicate,
        "records_updated": import_res.records_updated,
        "validation_errors": validation_errors[:10],
    }

