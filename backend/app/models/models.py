"""
US WIN HUNTER — SQLAlchemy ORM Models

Complete database schema covering:
- Data sources & collection infrastructure
- Advertisers & advertiser relationships
- Advertisements & snapshots
- Creatives & fingerprints
- Products, clusters & merge history
- Landing pages & offers
- Bundle offers
- Pain clusters & evidence
- Trend observations
- Product daily metrics & opportunity scores
- Evidence links
- Analyst reviews
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─── Enums ───────────────────────────────────────────────────────────────────

class DataSourceType(str, enum.Enum):
    META_AD_LIBRARY = "meta_ad_library"
    TIKTOK_CREATIVE_CENTER = "tiktok_creative_center"
    REDDIT = "reddit"
    GOOGLE_TRENDS = "google_trends"
    AMAZON = "amazon"
    APIFY = "apify"
    MANUAL_IMPORT = "manual_import"
    CRAWL4AI = "crawl4ai"
    OTHER = "other"


class CollectionJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


class EvidenceType(str, enum.Enum):
    OBSERVED_FACT = "observed_fact"
    DERIVED_METRIC = "derived_metric"
    AI_INFERENCE = "ai_inference"
    UNVERIFIED_HYPOTHESIS = "unverified_hypothesis"


class RelationshipType(str, enum.Enum):
    IDENTICAL_CREATIVE = "identical_creative"
    IDENTICAL_PRODUCT = "identical_product"
    PRODUCT_VARIANT = "product_variant"
    SIMILAR_CATEGORY = "similar_category"
    SUSPECTED_SAME_OPERATOR = "suspected_same_operator"
    VERIFIED_SAME_OPERATOR = "verified_same_operator"


class BundleMechanism(str, enum.Enum):
    DAILY_ROTATION = "daily_rotation"
    MULTIPLE_LOCATIONS = "multiple_locations"
    FREQUENT_USAGE = "frequent_usage"
    CONSUMABLE_REPLENISHMENT = "consumable_replenishment"
    COMPLETE_COVERAGE = "complete_coverage"
    MULTI_PERSON_HOUSEHOLD = "multi_person_household"
    MULTI_PET = "multi_pet"
    BACKUP_REPLACEMENT = "backup_replacement"
    UNKNOWN = "unknown"


class PainLanguageGroup(str, enum.Enum):
    COMPLAINT = "complaint"
    FAILED_WORKAROUND = "failed_workaround"
    PURCHASE_INTENT = "purchase_intent"
    PRODUCT_REPLACEMENT = "product_replacement"
    PRODUCT_FAILURE = "product_failure"


class ConfidenceLevel(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


# ─── Models ──────────────────────────────────────────────────────────────────

class DataSource(Base):
    """Registry of data sources the system can collect from."""
    __tablename__ = "data_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    source_type: Mapped[DataSourceType] = mapped_column(Enum(DataSourceType), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    geographic_coverage: Mapped[Optional[str]] = mapped_column(String(50), default="US")
    rate_limit_rpm: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_successful_collection: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    collection_jobs = relationship("CollectionJob", back_populates="data_source")


class CollectionJob(Base):
    """Definition of a recurring or one-time data collection job."""
    __tablename__ = "collection_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    data_source_id: Mapped[str] = mapped_column(String(36), ForeignKey("data_sources.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g., "ad_discovery", "pain_scan"
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    interval_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    data_source = relationship("DataSource", back_populates="collection_jobs")
    runs = relationship("CollectionRun", back_populates="job")


class CollectionRun(Base):
    """Individual execution of a collection job."""
    __tablename__ = "collection_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("collection_jobs.id"), nullable=False)
    status: Mapped[CollectionJobStatus] = mapped_column(Enum(CollectionJobStatus), default=CollectionJobStatus.PENDING)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    records_fetched: Mapped[int] = mapped_column(Integer, default=0)
    records_new: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    records_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    coverage_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    job = relationship("CollectionJob", back_populates="runs")
    source_records = relationship("SourceRecord", back_populates="collection_run")


class SourceRecord(Base):
    """Raw record from any data source, preserving provenance."""
    __tablename__ = "source_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    collection_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("collection_runs.id"), nullable=False)
    source_type: Mapped[DataSourceType] = mapped_column(Enum(DataSourceType), nullable=False)
    external_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    geographic_context: Mapped[Optional[str]] = mapped_column(String(50), default="US")
    geo_confidence: Mapped[ConfidenceLevel] = mapped_column(Enum(ConfidenceLevel), default=ConfidenceLevel.UNKNOWN)
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    duplicate_of_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    collection_run = relationship("CollectionRun", back_populates="source_records")

    __table_args__ = (
        Index("ix_source_records_external_id", "source_type", "external_id"),
        Index("ix_source_records_processed", "is_processed"),
    )


class Advertiser(Base):
    """An entity that runs advertisements."""
    __tablename__ = "advertisers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    facebook_page_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, unique=True)
    domain: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    domains: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # list of associated domains
    source_type: Mapped[DataSourceType] = mapped_column(Enum(DataSourceType), nullable=False)
    external_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    country: Mapped[str] = mapped_column(String(10), default="US")
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_evidence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    advertisements = relationship("Advertisement", back_populates="advertiser")
    relationships_from = relationship("AdvertiserRelationship", foreign_keys="AdvertiserRelationship.advertiser_id_a", back_populates="advertiser_a")
    relationships_to = relationship("AdvertiserRelationship", foreign_keys="AdvertiserRelationship.advertiser_id_b", back_populates="advertiser_b")

    __table_args__ = (
        Index("ix_advertisers_facebook_page_id", "facebook_page_id"),
        Index("ix_advertisers_domain", "domain"),
        Index("ix_advertisers_external_id", "source_type", "external_id"),
    )


class AdvertiserRelationship(Base):
    """Observable relationship between two advertisers."""
    __tablename__ = "advertiser_relationships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    advertiser_id_a: Mapped[str] = mapped_column(String(36), ForeignKey("advertisers.id"), nullable=False)
    advertiser_id_b: Mapped[str] = mapped_column(String(36), ForeignKey("advertisers.id"), nullable=False)
    relationship_type: Mapped[RelationshipType] = mapped_column(Enum(RelationshipType), nullable=False)
    confidence: Mapped[ConfidenceLevel] = mapped_column(Enum(ConfidenceLevel), default=ConfidenceLevel.UNKNOWN)
    evidence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    advertiser_a = relationship("Advertiser", foreign_keys=[advertiser_id_a], back_populates="relationships_from")
    advertiser_b = relationship("Advertiser", foreign_keys=[advertiser_id_b], back_populates="relationships_to")

    __table_args__ = (
        UniqueConstraint("advertiser_id_a", "advertiser_id_b", "relationship_type", name="uq_adv_relationship"),
    )


class Advertisement(Base):
    """An individual advertisement observed in any source."""
    __tablename__ = "advertisements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[DataSourceType] = mapped_column(Enum(DataSourceType), nullable=False)
    advertiser_id: Mapped[str] = mapped_column(String(36), ForeignKey("advertisers.id"), nullable=False)
    product_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("products.id"), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    creative_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    landing_page_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ad_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Link to view ad in library
    creative_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # image, video, carousel
    target_country: Mapped[str] = mapped_column(String(10), default="US")
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    advertiser_start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    raw_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    advertiser = relationship("Advertiser", back_populates="advertisements")
    product = relationship("Product", back_populates="advertisements")
    snapshots = relationship("AdvertisementSnapshot", back_populates="advertisement")
    creative = relationship("Creative", back_populates="advertisement", uselist=False)

    __table_args__ = (
        UniqueConstraint("source_type", "external_id", name="uq_ad_source_external"),
        Index("ix_advertisements_advertiser_id", "advertiser_id"),
        Index("ix_advertisements_product_id", "product_id"),
        Index("ix_advertisements_first_seen", "first_seen_at"),
        Index("ix_advertisements_active", "is_active"),
    )


class AdvertisementSnapshot(Base):
    """Daily snapshot of an advertisement's status for temporal analysis."""
    __tablename__ = "advertisement_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    advertisement_id: Mapped[str] = mapped_column(String(36), ForeignKey("advertisements.id"), nullable=False)
    snapshot_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source_type: Mapped[DataSourceType] = mapped_column(Enum(DataSourceType), nullable=False)
    collection_run_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("collection_runs.id"), nullable=True)
    raw_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    advertisement = relationship("Advertisement", back_populates="snapshots")

    __table_args__ = (
        UniqueConstraint("advertisement_id", "snapshot_date", name="uq_ad_snapshot_date"),
        Index("ix_snapshots_date", "snapshot_date"),
    )


class Creative(Base):
    """Creative asset (image/video) associated with an advertisement."""
    __tablename__ = "creatives"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    advertisement_id: Mapped[str] = mapped_column(String(36), ForeignKey("advertisements.id"), nullable=False)
    creative_type: Mapped[str] = mapped_column(String(50), nullable=False)  # image, video
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    local_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)  # SHA-256
    perceptual_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    advertisement = relationship("Advertisement", back_populates="creative")
    fingerprints = relationship("CreativeFingerprint", back_populates="creative")

    __table_args__ = (
        Index("ix_creatives_file_hash", "file_hash"),
        Index("ix_creatives_perceptual_hash", "perceptual_hash"),
    )


class CreativeFingerprint(Base):
    """Multi-layer fingerprint for creative identity matching."""
    __tablename__ = "creative_fingerprints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    creative_id: Mapped[str] = mapped_column(String(36), ForeignKey("creatives.id"), nullable=False)
    fingerprint_type: Mapped[str] = mapped_column(String(50), nullable=False)  # phash, dhash, embedding, etc.
    fingerprint_value: Mapped[str] = mapped_column(Text, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(50), default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    creative = relationship("Creative", back_populates="fingerprints")

    __table_args__ = (
        Index("ix_fingerprints_type_value", "fingerprint_type", "fingerprint_value"),
    )


class Product(Base):
    """A physical product identified from advertisements or other sources."""
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    min_price_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_price_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_country: Mapped[str] = mapped_column(String(10), default="US")
    us_relevance_confidence: Mapped[ConfidenceLevel] = mapped_column(Enum(ConfidenceLevel), default=ConfidenceLevel.UNKNOWN)
    is_physical: Mapped[bool] = mapped_column(Boolean, default=True)
    functional_use_case: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    customer_pain: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_type: Mapped[DataSourceType] = mapped_column(Enum(DataSourceType), nullable=False)
    external_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    raw_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    advertisements = relationship("Advertisement", back_populates="product")
    cluster_memberships = relationship("ProductClusterMember", back_populates="product")
    offers = relationship("ProductOffer", back_populates="product")
    bundle_offers = relationship("BundleOffer", back_populates="product")
    daily_metrics = relationship("ProductDailyMetric", back_populates="product")
    opportunity_scores = relationship("OpportunityScore", back_populates="product")
    analyst_reviews = relationship("AnalystReview", back_populates="product")

    __table_args__ = (
        Index("ix_products_normalized_name", "normalized_name"),
        Index("ix_products_category", "category"),
        Index("ix_products_source_external", "source_type", "external_id"),
    )


class ProductCluster(Base):
    """Group of products identified as being the same or closely related."""
    __tablename__ = "product_clusters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    canonical_product_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("products.id"), nullable=True)
    cluster_confidence: Mapped[ConfidenceLevel] = mapped_column(Enum(ConfidenceLevel), default=ConfidenceLevel.UNKNOWN)
    is_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    members = relationship("ProductClusterMember", back_populates="cluster")


class ProductClusterMember(Base):
    """Membership of a product in a cluster."""
    __tablename__ = "product_cluster_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    cluster_id: Mapped[str] = mapped_column(String(36), ForeignKey("product_clusters.id"), nullable=False)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), nullable=False)
    relationship_type: Mapped[RelationshipType] = mapped_column(Enum(RelationshipType), nullable=False)
    similarity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    matching_evidence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    confidence: Mapped[ConfidenceLevel] = mapped_column(Enum(ConfidenceLevel), default=ConfidenceLevel.UNKNOWN)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    cluster = relationship("ProductCluster", back_populates="members")
    product = relationship("Product", back_populates="cluster_memberships")

    __table_args__ = (
        UniqueConstraint("cluster_id", "product_id", name="uq_cluster_product"),
    )


class ProductMergeHistory(Base):
    """Reversible history of product merge/split decisions."""
    __tablename__ = "product_merge_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # merge, split, reassign
    source_product_id: Mapped[str] = mapped_column(String(36), nullable=False)
    target_product_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    cluster_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    performed_by: Mapped[str] = mapped_column(String(255), default="system")
    is_reverted: Mapped[bool] = mapped_column(Boolean, default=False)
    reverted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class LandingPage(Base):
    """Landing pages linked from advertisements."""
    __tablename__ = "landing_pages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(512), nullable=False)
    advertiser_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("advertisers.id"), nullable=True)
    product_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("products.id"), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    page_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # product, collection, home
    last_crawled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    crawl_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    extracted_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_landing_pages_domain", "domain"),
    )


class ProductOffer(Base):
    """Observable price/offer for a product at a specific time."""
    __tablename__ = "product_offers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), nullable=False)
    advertiser_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("advertisers.id"), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    compare_at_price_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    is_bundle: Mapped[bool] = mapped_column(Boolean, default=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    evidence_type: Mapped[EvidenceType] = mapped_column(Enum(EvidenceType), default=EvidenceType.OBSERVED_FACT)
    raw_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    product = relationship("Product", back_populates="offers")


class BundleOffer(Base):
    """Specific bundle offer observed for a product."""
    __tablename__ = "bundle_offers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), nullable=False)
    advertiser_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("advertisers.id"), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    bundle_price_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit_price_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    discount_claim: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    estimated_order_value_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bundle_mechanism: Mapped[BundleMechanism] = mapped_column(Enum(BundleMechanism), default=BundleMechanism.UNKNOWN)
    mechanism_evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bundle_status: Mapped[str] = mapped_column(String(50), default="offered")  # offered, promoted, purchased
    purchase_evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_natural_bundle: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    natural_bundle_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    evidence_type: Mapped[EvidenceType] = mapped_column(Enum(EvidenceType), default=EvidenceType.OBSERVED_FACT)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    product = relationship("Product", back_populates="bundle_offers")

    __table_args__ = (
        Index("ix_bundle_offers_product_quantity", "product_id", "quantity"),
    )


class PainCluster(Base):
    """Cluster of semantically related consumer complaints/pain points."""
    __tablename__ = "pain_clusters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    core_problem: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    distinct_source_count: Mapped[int] = mapped_column(Integer, default=0)
    distinct_author_count: Mapped[int] = mapped_column(Integer, default=0)
    frequency_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recency_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    repeated_frustrations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    existing_solutions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    solution_shortcomings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    product_hypotheses: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    search_keywords: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    us_relevance_confidence: Mapped[ConfidenceLevel] = mapped_column(Enum(ConfidenceLevel), default=ConfidenceLevel.UNKNOWN)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    evidence = relationship("PainEvidence", back_populates="cluster")


class PainEvidence(Base):
    """Individual evidence item supporting a pain cluster."""
    __tablename__ = "pain_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    cluster_id: Mapped[str] = mapped_column(String(36), ForeignKey("pain_clusters.id"), nullable=False)
    source_type: Mapped[DataSourceType] = mapped_column(Enum(DataSourceType), nullable=False)
    language_group: Mapped[PainLanguageGroup] = mapped_column(Enum(PainLanguageGroup), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    author_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # hashed/anonymized
    content_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    original_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    geographic_context: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sentiment_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evidence_type: Mapped[EvidenceType] = mapped_column(Enum(EvidenceType), default=EvidenceType.OBSERVED_FACT)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    cluster = relationship("PainCluster", back_populates="evidence")


class TrendObservation(Base):
    """Search trend data point for a keyword/product."""
    __tablename__ = "trend_observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    keyword: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[DataSourceType] = mapped_column(Enum(DataSourceType), nullable=False)
    geographic_scope: Mapped[str] = mapped_column(String(50), default="US")
    observation_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    interest_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    related_queries: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    rising_queries: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    raw_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        Index("ix_trends_keyword_date", "keyword", "observation_date"),
    )


class ProductDailyMetric(Base):
    """Daily aggregated metrics for a product."""
    __tablename__ = "product_daily_metrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), nullable=False)
    metric_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    active_ad_count: Mapped[int] = mapped_column(Integer, default=0)
    new_ad_count: Mapped[int] = mapped_column(Integer, default=0)
    unique_advertiser_count: Mapped[int] = mapped_column(Integer, default=0)
    new_advertiser_count: Mapped[int] = mapped_column(Integer, default=0)
    unique_creative_count: Mapped[int] = mapped_column(Integer, default=0)
    new_creative_count: Mapped[int] = mapped_column(Integer, default=0)
    coverage_completeness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0-1
    collection_errors: Mapped[int] = mapped_column(Integer, default=0)
    evidence_type: Mapped[EvidenceType] = mapped_column(Enum(EvidenceType), default=EvidenceType.DERIVED_METRIC)
    raw_components: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    product = relationship("Product", back_populates="daily_metrics")

    __table_args__ = (
        UniqueConstraint("product_id", "metric_date", name="uq_product_daily_metric"),
        Index("ix_product_metrics_date", "metric_date"),
    )


class OpportunityScore(Base):
    """Computed opportunity score for a product at a point in time."""
    __tablename__ = "opportunity_scores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), nullable=False)
    score_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD

    # Emergence Score (0-100)
    emergence_score: Mapped[float] = mapped_column(Float, default=0.0)
    emergence_components: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Evidence Confidence (0-100)
    evidence_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_components: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Bundle Potential (0-100)
    bundle_potential: Mapped[float] = mapped_column(Float, default=0.0)
    bundle_components: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Composite
    composite_score: Mapped[float] = mapped_column(Float, default=0.0)
    requires_verification: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Weights used
    weights_version: Mapped[str] = mapped_column(String(50), default="v1")
    weights_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    product = relationship("Product", back_populates="opportunity_scores")

    __table_args__ = (
        UniqueConstraint("product_id", "score_date", name="uq_product_score_date"),
        Index("ix_scores_composite", "composite_score"),
        Index("ix_scores_emergence", "emergence_score"),
    )


class EvidenceLink(Base):
    """Links evidence artifacts to any entity in the system."""
    __tablename__ = "evidence_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # product, advertiser, cluster, etc.
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    evidence_type: Mapped[EvidenceType] = mapped_column(Enum(EvidenceType), nullable=False)
    source_type: Mapped[Optional[DataSourceType]] = mapped_column(Enum(DataSourceType), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    confidence: Mapped[ConfidenceLevel] = mapped_column(Enum(ConfidenceLevel), default=ConfidenceLevel.UNKNOWN)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        Index("ix_evidence_entity", "entity_type", "entity_id"),
    )


class AlertType(str, enum.Enum):
    NEW_ADVERTISER_ENTRY = "new_advertiser_entry"
    CREATIVE_SPIKE = "creative_spike"
    SUDDEN_CONTRACTION = "sudden_contraction"
    SUSTAINED_GROWTH = "sustained_growth"
    SEASONAL_PATTERN = "seasonal_pattern"
    COVERAGE_GAP = "coverage_gap"
    HIGH_EMERGENCE_LOW_CONFIDENCE = "high_emergence_low_confidence"


class AlertSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Alert(Base):
    """Structured alert generated by temporal analysis or scoring."""
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    alert_type: Mapped[AlertType] = mapped_column(Enum(AlertType), nullable=False)
    severity: Mapped[AlertSeverity] = mapped_column(Enum(AlertSeverity), default=AlertSeverity.INFO)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # product, advertiser
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    entity_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        Index("ix_alerts_type", "alert_type"),
        Index("ix_alerts_entity", "entity_type", "entity_id"),
        Index("ix_alerts_created", "created_at"),
        Index("ix_alerts_unread", "is_read", "is_dismissed"),
    )


class SchedulerRunLog(Base):
    """Log of automated scheduler pipeline runs."""
    __tablename__ = "scheduler_run_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_type: Mapped[str] = mapped_column(String(50), nullable=False)  # daily_pipeline, manual
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running, completed, failed
    steps_completed: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    errors: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    alerts_generated: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AnalystReview(Base):
    """Manual analyst review of a product or recommendation."""
    __tablename__ = "analyst_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(255), default="operator")
    verdict: Mapped[str] = mapped_column(String(50), nullable=False)  # promising, rejected, needs_more_data, testing
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bundle_assessment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_aov: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_bundle_qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    action_items: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    product = relationship("Product", back_populates="analyst_reviews")

