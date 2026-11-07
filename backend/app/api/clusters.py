"""Clusters & Merge/Split API — Product identity management."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import (
    ProductCluster, ProductClusterMember, ProductMergeHistory,
    RelationshipType, ConfidenceLevel,
)
from app.engines.fingerprinting import ClusteringService

router = APIRouter()


class ClusterCreateRequest(BaseModel):
    name: str
    canonical_product_id: str
    member_ids: list[str]
    relationship_type: str = "identical_product"
    reviewed_by: str = "operator"


class SplitRequest(BaseModel):
    product_id: str
    cluster_id: str
    reason: str = ""


@router.get("/proposals/{product_id}")
async def get_cluster_proposals(
    product_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get duplicate candidates for a product. These are proposals, not final merges."""
    svc = ClusteringService(db)
    return await svc.propose_cluster(product_id)


@router.get("/proposals")
async def scan_all_proposals(db: AsyncSession = Depends(get_db)):
    """Scan all products for potential duplicate pairs."""
    svc = ClusteringService(db)
    return await svc.scan_all_products()


@router.post("/")
async def create_cluster(
    req: ClusterCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a reviewed cluster from accepted proposals."""
    try:
        rtype = RelationshipType(req.relationship_type)
    except ValueError:
        rtype = RelationshipType.IDENTICAL_PRODUCT

    svc = ClusteringService(db)
    cluster = await svc.create_cluster(
        name=req.name,
        canonical_product_id=req.canonical_product_id,
        member_ids=req.member_ids,
        relationship_type=rtype,
        reviewed_by=req.reviewed_by,
    )
    return {"id": cluster.id, "name": cluster.name, "members": len(req.member_ids)}


@router.post("/split")
async def split_product(
    req: SplitRequest,
    db: AsyncSession = Depends(get_db),
):
    """Remove a product from a cluster (reversible)."""
    svc = ClusteringService(db)
    await svc.split_from_cluster(
        product_id=req.product_id,
        cluster_id=req.cluster_id,
        reason=req.reason,
    )
    return {"status": "split", "product_id": req.product_id, "cluster_id": req.cluster_id}


@router.get("/")
async def list_clusters(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List all product clusters."""
    result = await db.execute(
        select(ProductCluster)
        .order_by(ProductCluster.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    clusters = result.scalars().all()
    out = []
    for c in clusters:
        members_result = await db.execute(
            select(ProductClusterMember).where(ProductClusterMember.cluster_id == c.id)
        )
        members = members_result.scalars().all()
        out.append({
            "id": c.id,
            "name": c.name,
            "canonical_product_id": c.canonical_product_id,
            "confidence": c.cluster_confidence.value,
            "is_reviewed": c.is_reviewed,
            "member_count": len(members),
            "members": [
                {"product_id": m.product_id, "relationship": m.relationship_type.value, "similarity": m.similarity_score}
                for m in members
            ],
        })
    return out


@router.get("/history")
async def merge_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """View merge/split history (audit trail)."""
    result = await db.execute(
        select(ProductMergeHistory)
        .order_by(ProductMergeHistory.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    return [
        {
            "id": h.id,
            "action": h.action,
            "source_product_id": h.source_product_id,
            "target_product_id": h.target_product_id,
            "cluster_id": h.cluster_id,
            "reason": h.reason,
            "performed_by": h.performed_by,
            "is_reverted": h.is_reverted,
            "created_at": str(h.created_at),
        }
        for h in result.scalars().all()
    ]

