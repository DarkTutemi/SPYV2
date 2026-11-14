"""Temporal Intelligence & Advertiser Graph API routes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.engines.temporal import TemporalEngine
from app.engines.advertiser_graph import AdvertiserGraphEngine
from app.models.models import Product, ProductDailyMetric

router = APIRouter()


# ── Snapshots & Metrics ──────────────────────────────────────────────────

@router.post("/snapshot")
async def create_snapshot(
    date: Optional[str] = None,
    collection_run_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Create or update daily advertisement snapshots. Observation quality is server-derived from evidence."""
    engine = TemporalEngine(db)
    return await engine.create_daily_snapshot(
        snapshot_date=date,
        collection_run_id=collection_run_id,
    )


@router.post("/aggregate")
async def aggregate_metrics(
    date: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Aggregate daily metrics for all US products."""
    engine = TemporalEngine(db)
    metrics = await engine.aggregate_daily_metrics(date)
    return {"date": date or "today", "products_aggregated": len(metrics)}


@router.get("/emerging")
async def get_emerging(
    window: int = Query(7, ge=7, le=90),
    db: AsyncSession = Depends(get_db),
):
    """Detect products with accelerating advertising signals."""
    engine = TemporalEngine(db)
    return await engine.detect_emerging_products(window)


@router.get("/comparison/{product_id}")
async def window_comparison(
    product_id: str,
    window: int = Query(7, ge=7, le=90),
    db: AsyncSession = Depends(get_db),
):
    """Compare recent vs. prior window for a product."""
    engine = TemporalEngine(db)
    return await engine.compute_window_comparison(product_id, window)


# ── Advertiser Graph ─────────────────────────────────────────────────────

@router.post("/graph/discover")
async def discover_graph(db: AsyncSession = Depends(get_db)):
    """Run advertiser relationship discovery."""
    engine = AdvertiserGraphEngine(db)
    proposals = await engine.discover_relationships()
    await engine.update_advertiser_domains()
    return {"proposals": len(proposals)}


@router.get("/graph/{advertiser_id}")
async def get_graph(
    advertiser_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get full graph context for an advertiser."""
    engine = AdvertiserGraphEngine(db)
    return await engine.get_advertiser_graph(advertiser_id)


# ── Historical Metrics for Charts ────────────────────────────────────────

@router.get("/metrics/{product_id}")
async def get_product_metrics(
    product_id: str,
    window: int = Query(30, ge=7, le=90),
    db: AsyncSession = Depends(get_db),
):
    """Get historical daily metrics for a product (for charting)."""
    from datetime import datetime, timedelta, timezone

    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")

    end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_date = (datetime.now(timezone.utc) - timedelta(days=window)).strftime("%Y-%m-%d")

    result = await db.execute(
        select(ProductDailyMetric)
        .where(
            ProductDailyMetric.product_id == product_id,
            ProductDailyMetric.metric_date >= start_date,
            ProductDailyMetric.metric_date <= end_date,
        )
        .order_by(ProductDailyMetric.metric_date)
    )
    metrics = list(result.scalars().all())

    return {
        "product_id": product_id,
        "product_name": product.name,
        "window_days": window,
        "start_date": start_date,
        "end_date": end_date,
        "data_points": len(metrics),
        "metrics": [
            {
                "date": m.metric_date,
                "active_ads": m.active_ad_count,
                "new_ads": m.new_ad_count,
                "unique_advertisers": m.unique_advertiser_count,
                "new_advertisers": m.new_advertiser_count,
                "unique_creatives": m.unique_creative_count,
                "new_creatives": m.new_creative_count,
                "coverage": m.coverage_completeness,
            }
            for m in metrics
        ],
        "coverage_warning": (
            "Some days have low or zero coverage — metrics on those days "
            "may be unreliable or missing."
            if any((m.coverage_completeness or 0) < 0.3 for m in metrics)
            else None
        ),
    }


@router.get("/analytics/overview")
async def analytics_overview(
    window: int = Query(7, ge=7, le=90),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated analytics overview across all US products."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func

    end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_date = (datetime.now(timezone.utc) - timedelta(days=window)).strftime("%Y-%m-%d")

    result = await db.execute(
        select(
            ProductDailyMetric.metric_date,
            func.sum(ProductDailyMetric.active_ad_count).label("total_ads"),
            func.sum(ProductDailyMetric.new_ad_count).label("total_new_ads"),
            func.max(ProductDailyMetric.unique_advertiser_count).label("max_advertisers"),
            func.count(ProductDailyMetric.id).label("products_tracked"),
        )
        .where(
            ProductDailyMetric.metric_date >= start_date,
            ProductDailyMetric.metric_date <= end_date,
        )
        .group_by(ProductDailyMetric.metric_date)
        .order_by(ProductDailyMetric.metric_date)
    )
    rows = result.all()

    return {
        "window_days": window,
        "start_date": start_date,
        "end_date": end_date,
        "daily_overview": [
            {
                "date": row.metric_date,
                "total_ads": row.total_ads or 0,
                "total_new_ads": row.total_new_ads or 0,
                "max_advertisers": row.max_advertisers or 0,
                "products_tracked": row.products_tracked or 0,
            }
            for row in rows
        ],
    }

"""
# TASK — AUDIT AND SELECTIVELY INTEGRATE CLAUDE SUPER KIT INTO ANTIGRAVITY

You are working inside Google Antigravity IDE on Windows.

The attached Claude-Super_Kit.zip contains ClaudeKit Engineer agents, skills, commands, hooks and scripts.

Your objective is to improve our existing AI agent capabilities WITHOUT replacing the current configuration or disrupting any project.

## 1. Inspect before installation

Analyze the ZIP and identify:

- Available agents and skills.
- Duplicate capabilities already installed.
- Compatibility with Google Antigravity IDE.
- Unsupported Claude Code-specific tools.
- External dependencies.
- Executable scripts, hooks and permission risks.
- Outdated MCP and API instructions.

Do not execute bundled scripts during the initial audit.

## 2. Select only valuable capabilities

Prioritize:

- code-review
- debugging
- backend-development
- databases
- chrome-devtools
- mcp-builder

Consider Shopify, repomix and research skills only when they add real value.

Use the official Antigravity workspace skill convention:

.agents/skills/<skill-name>/SKILL.md

Adapt references and frontmatter to Antigravity where necessary.

Do not blindly copy Claude Code subagent definitions, slash commands or hooks.

## 3. Preserve existing configuration

DO NOT overwrite:

- Existing agent instructions.
- Existing MCP configuration.
- Existing skills.
- Existing workspace rules.
- Existing API credentials.
- Existing Git configuration.

Do not import settings.local.json.

Do not install automatic tool-approval rules.

Do not enable Discord or Telegram notification hooks.

Do not automatically execute installation scripts or remote packages.

## 4. Correct conflicting instructions

Keep mock data permitted in isolated unit tests.

Never allow mocks, fixtures or manually invented records to become production commercial evidence.

Require actual external source provenance before marking product evidence verified.

Require operator authorization before:

- Paid API launches.
- Production database mutation.
- Git push.
- Live Shopify theme deployment.
- Destructive operations.

Keep existing SPYV2 T+14 monitoring safeguards intact.

## 5. Adapt Chrome DevTools safely

Audit the included Puppeteer scripts.

Do not disable the browser sandbox by default.

Verify that browser automation works with the Windows environment.

Do not bypass CAPTCHA or website access controls.

Prefer an isolated browser session for UI testing.

## 6. Minimal integration

Perform integration in a separate temporary branch or staging directory.

Install only selected compatible skills.

Avoid unnecessary dependencies.

Run a small functional test for each installed skill.

Verify that existing Antigravity capabilities still work.

Do not modify production application code merely to install skills.

## 7. Final report in Vietnamese

Return:

1. Skills reviewed.
2. Skills selected.
3. Skills rejected and reasons.
4. Existing skills preserved.
5. Files created or modified.
6. Dependencies required.
7. Security risks eliminated.
8. Functional tests.
9. How to activate each new skill.
10. Exact rollback procedure.

Do not push or deploy anything without operator approval.

The goal is a smaller, safer and more capable agent — not installing the entire ZIP.
"""
