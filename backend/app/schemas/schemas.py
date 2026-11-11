"""
US WIN HUNTER — Pydantic Schemas for API contracts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, ConfigDict

from app.models.models import (
    BundleMechanism,
    CollectionJobStatus,
    ConfidenceLevel,
    DataSourceType,
    EvidenceType,
    PainLanguageGroup,
    RelationshipType,
)


# ─── Base ────────────────────────────────────────────────────────────────────

class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ─── Data Source ─────────────────────────────────────────────────────────────

class DataSourceCreate(BaseModel):
    name: str
    source_type: DataSourceType
    is_active: bool = True
    config: Optional[dict] = None
    geographic_coverage: str = "US"
    rate_limit_rpm: Optional[int] = None
    notes: Optional[str] = None


class DataSourceRead(BaseSchema):
    id: str
    name: str
    source_type: DataSourceType
    is_active: bool
    config: Optional[dict] = None
    geographic_coverage: Optional[str]
    rate_limit_rpm: Optional[int]
    last_successful_collection: Optional[datetime]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


# ─── Collection ──────────────────────────────────────────────────────────────

class CollectionJobCreate(BaseModel):
    data_source_id: str
    name: str
    job_type: str
    config: Optional[dict] = None
    is_recurring: bool = False
    interval_minutes: Optional[int] = None


class CollectionJobRead(BaseSchema):
    id: str
    data_source_id: str
    name: str
    job_type: str
    config: Optional[dict]
    is_recurring: bool
    interval_minutes: Optional[int]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CollectionRunRead(BaseSchema):
    id: str
    job_id: str
    status: CollectionJobStatus
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    records_fetched: int
    records_new: int
    records_updated: int
    records_duplicate: int
    errors: Optional[dict]
    coverage_notes: Optional[str]
    created_at: datetime


# ─── Advertiser ──────────────────────────────────────────────────────────────

class AdvertiserCreate(BaseModel):
    name: str
    facebook_page_id: Optional[str] = None
    domain: Optional[str] = None
    source_type: DataSourceType
    external_id: Optional[str] = None
    country: str = "US"


class AdvertiserRead(BaseSchema):
    id: str
    name: str
    normalized_name: Optional[str]
    facebook_page_id: Optional[str]
    domain: Optional[str]
    domains: Optional[list]
    source_type: DataSourceType
    external_id: Optional[str]
    country: str
    is_verified: bool
    first_seen_at: datetime
    last_seen_at: datetime
    created_at: datetime


class AdvertiserDetail(AdvertiserRead):
    ad_count: int = 0
    active_ad_count: int = 0
    product_count: int = 0


# ─── Advertisement ───────────────────────────────────────────────────────────

class AdvertisementCreate(BaseModel):
    external_id: str
    source_type: DataSourceType
    advertiser_id: str
    product_id: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    creative_url: Optional[str] = None
    landing_page_url: Optional[str] = None
    ad_url: Optional[str] = None
    creative_type: Optional[str] = None
    target_country: str = "US"
    is_active: Optional[bool] = None
    advertiser_start_date: Optional[datetime] = None
    raw_data: Optional[dict] = None


class AdvertisementRead(BaseSchema):
    id: str
    external_id: str
    source_type: DataSourceType
    advertiser_id: str
    product_id: Optional[str]
    title: Optional[str]
    body: Optional[str]
    creative_url: Optional[str]
    landing_page_url: Optional[str]
    ad_url: Optional[str]
    creative_type: Optional[str]
    target_country: str
    is_active: Optional[bool]
    advertiser_start_date: Optional[datetime]
    first_seen_at: datetime
    last_seen_at: datetime
    created_at: datetime


# ─── Product ─────────────────────────────────────────────────────────────────

class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    source_url: Optional[str] = None
    min_price_usd: Optional[float] = None
    max_price_usd: Optional[float] = None
    target_country: str = "US"
    is_physical: bool = True
    functional_use_case: Optional[str] = None
    customer_pain: Optional[str] = None
    source_type: DataSourceType
    external_id: Optional[str] = None
    raw_data: Optional[dict] = None


class ProductRead(BaseSchema):
    id: str
    name: str
    normalized_name: Optional[str]
    description: Optional[str]
    category: Optional[str]
    image_url: Optional[str]
    source_url: Optional[str]
    min_price_usd: Optional[float]
    max_price_usd: Optional[float]
    target_country: str
    us_relevance_confidence: ConfidenceLevel
    is_physical: bool
    is_synthetic: bool = False
    opportunity_status: Optional[str] = "DISCOVERED"
    primary_bundle_qty: Optional[int] = None
    functional_use_case: Optional[str]
    customer_pain: Optional[str]
    source_type: DataSourceType
    first_seen_at: datetime
    last_seen_at: datetime
    created_at: datetime


class ProductDetail(ProductRead):
    ad_count: int = 0
    active_ad_count: int = 0
    advertiser_count: int = 0
    cluster_id: Optional[str] = None
    emergence_score: Optional[float] = None
    evidence_confidence: Optional[float] = None
    bundle_potential: Optional[float] = None
    commercial_model: Optional[str] = "MODEL_A_SINGLE_PRODUCT"
    core_opportunity_score: Optional[float] = None
    bundle_upside_score: Optional[float] = None
    why_it_ranks_high: Optional[str] = None
    why_it_might_fail: Optional[str] = None
    what_evidence_supports_it: Optional[str] = None
    what_remains_unknown: Optional[str] = None
    next_validation_action: Optional[str] = None
    bundle_offers: list[BundleOfferRead] = []
    product_offers: list[ProductOfferRead] = []
    data_gaps: list[str] = []


# ─── Bundle Offer ────────────────────────────────────────────────────────────

class BundleOfferCreate(BaseModel):
    product_id: str
    advertiser_id: Optional[str] = None
    source_url: Optional[str] = None
    quantity: int
    bundle_price_usd: Optional[float] = None
    unit_price_usd: Optional[float] = None
    discount_claim: Optional[str] = None
    estimated_order_value_usd: Optional[float] = None
    bundle_mechanism: BundleMechanism = BundleMechanism.UNKNOWN
    mechanism_evidence: Optional[str] = None
    bundle_status: str = "offered"
    is_natural_bundle: Optional[bool] = None
    natural_bundle_reasoning: Optional[str] = None


class ProductOfferRead(BaseSchema):
    id: str
    product_id: str
    advertiser_id: Optional[str] = None
    source_url: Optional[str] = None
    price_usd: Optional[float] = None
    compare_at_price_usd: Optional[float] = None
    currency: str = "USD"
    quantity: int = 1
    is_bundle: bool = False
    evidence_type: str = "observed_fact"
    price_evidence_type: Optional[str] = None
    observed_at: datetime
    raw_data: Optional[dict] = None


class BundleOfferRead(BaseSchema):
    id: str
    product_id: str
    advertiser_id: Optional[str]
    source_url: Optional[str]
    quantity: int
    bundle_price_usd: Optional[float]
    unit_price_usd: Optional[float]
    discount_claim: Optional[str]
    estimated_order_value_usd: Optional[float]
    bundle_mechanism: BundleMechanism
    bundle_status: str
    is_natural_bundle: Optional[bool]
    natural_bundle_reasoning: Optional[str]
    evidence_type: Optional[str] = "observed_fact"
    price_evidence_type: Optional[str] = None
    observed_at: datetime


# ─── Pain Cluster ────────────────────────────────────────────────────────────

class PainClusterRead(BaseSchema):
    id: str
    name: str
    core_problem: str
    category: Optional[str]
    distinct_source_count: int
    distinct_author_count: int
    frequency_score: Optional[float]
    recency_score: Optional[float]
    repeated_frustrations: Optional[str]
    existing_solutions: Optional[str]
    solution_shortcomings: Optional[str]
    product_hypotheses: Optional[dict]
    search_keywords: Optional[dict]
    us_relevance_confidence: ConfidenceLevel
    created_at: datetime


class PainEvidenceRead(BaseSchema):
    id: str
    cluster_id: str
    source_type: DataSourceType
    language_group: PainLanguageGroup
    source_url: Optional[str]
    content_excerpt: str
    original_date: Optional[datetime]
    geographic_context: Optional[str]
    evidence_type: EvidenceType
    created_at: datetime


# ─── Opportunity Score ───────────────────────────────────────────────────────

class OpportunityScoreRead(BaseSchema):
    id: str
    product_id: str
    score_date: str
    emergence_score: float
    emergence_components: Optional[dict]
    discovery_signal_score: Optional[float] = 0.0
    functional_benefit_score: Optional[float] = 0.0
    observed_momentum: Optional[float] = None
    opportunity_status: Optional[str] = "DISCOVERED"
    status_reason: Optional[str] = None
    natural_bundle_quantity: Optional[int] = None
    independent_advertisers_count: Optional[int] = 1
    observed_single_price_usd: Optional[float] = None
    observed_bundle_price_usd: Optional[float] = None
    estimated_bundle_scenario: Optional[str] = None
    customer_aov_usd: Optional[float] = None
    natural_quantity_rationale: Optional[str] = None
    ad_activity_observations: Optional[dict] = None
    evidence_confidence: float
    confidence_components: Optional[dict]
    bundle_potential: float
    bundle_components: Optional[dict]
    composite_score: float
    commercial_model: Optional[str] = "MODEL_A_SINGLE_PRODUCT"
    core_opportunity_score: Optional[float] = 0.0
    bundle_upside_score: Optional[float] = 0.0
    why_it_ranks_high: Optional[str] = None
    why_it_might_fail: Optional[str] = None
    what_evidence_supports_it: Optional[str] = None
    what_remains_unknown: Optional[str] = None
    next_validation_action: Optional[str] = None
    requires_verification: bool
    verification_reason: Optional[str]
    weights_version: str
    created_at: datetime


# ─── Analyst Review ──────────────────────────────────────────────────────────

class AnalystReviewCreate(BaseModel):
    product_id: str
    verdict: str  # promising, rejected, needs_more_data, testing
    notes: Optional[str] = None
    bundle_assessment: Optional[str] = None
    target_aov: Optional[float] = None
    target_bundle_qty: Optional[int] = None
    action_items: Optional[dict] = None


class AnalystReviewRead(BaseSchema):
    id: str
    product_id: str
    reviewer: str
    verdict: str
    notes: Optional[str]
    bundle_assessment: Optional[str]
    target_aov: Optional[float]
    target_bundle_qty: Optional[int]
    action_items: Optional[dict]
    created_at: datetime
    updated_at: datetime


# ─── Product Intelligence Report ────────────────────────────────────────────

class ProductIntelligenceReport(BaseModel):
    """Complete intelligence report for a single product."""
    # Section 1-4: Basic Info
    product: ProductRead
    customer_pain: Optional[str] = None
    us_market_verified: bool = False
    us_verification_evidence: Optional[str] = None

    # Section 5-11: Advertising Intelligence
    first_observed: Optional[datetime] = None
    observed_advertiser_count: int = 0
    observed_active_ad_count: int = 0
    new_ads_7d: int = 0
    new_ads_14d: int = 0
    new_ads_30d: int = 0
    creative_clusters: list[dict] = []
    ad_persistence_days: Optional[int] = None
    momentum_data: list[dict] = []  # [{date, ads, advertisers, creatives}]

    # Section 12-13: Competitor
    competitor_domains: list[str] = []
    advertiser_evidence: list[dict] = []

    # Section 14-16: Bundle & Offers
    bundle_types: list[str] = []
    bundle_offers: list[BundleOfferRead] = []
    product_offers: list[ProductOfferRead] = []
    multi_unit_evidence: Optional[str] = None
    bundle_order_value_scenarios: list[dict] = []

    # Section 17-19: Scores
    emergence_score: Optional[float] = None
    evidence_confidence: Optional[float] = None
    bundle_potential: Optional[float] = None
    discovery_signal_score: Optional[float] = None
    functional_benefit_score: Optional[float] = None
    observed_momentum: Optional[float] = None
    opportunity_status: Optional[str] = "DISCOVERED"
    status_reason: Optional[str] = None
    natural_bundle_quantity: Optional[int] = None
    commercial_model: Optional[str] = "MODEL_A_SINGLE_PRODUCT"
    core_opportunity_score: Optional[float] = None
    bundle_upside_score: Optional[float] = None
    why_it_ranks_high: Optional[str] = None
    why_it_might_fail: Optional[str] = None
    what_evidence_supports_it: Optional[str] = None
    what_remains_unknown: Optional[str] = None
    next_validation_action: Optional[str] = None
    observed_single_price_usd: Optional[float] = None
    observed_bundle_price_usd: Optional[float] = None
    estimated_bundle_scenario: Optional[str] = None
    customer_aov_usd: Optional[float] = None
    natural_quantity_rationale: Optional[str] = None
    score_components: Optional[dict] = None

    # Section 20-22: Provenance
    source_urls: list[dict] = []  # [{url, type, timestamp}]
    data_gaps: list[str] = []
    ai_assessment: Optional[str] = None


# ─── Pagination ──────────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int
    pages: int


# ─── Data Health ─────────────────────────────────────────────────────────────

class DataHealthReport(BaseModel):
    sources: list[DataSourceRead]
    recent_runs: list[CollectionRunRead]
    total_advertisers: int = 0
    total_advertisements: int = 0
    total_products: int = 0
    total_clusters: int = 0
    stale_sources: list[str] = []
    failed_jobs_24h: int = 0
    integration_errors: list[dict] = []


# ─── Import ──────────────────────────────────────────────────────────────────

class ImportRequest(BaseModel):
    """Request to import data from a file or dataset."""
    source_type: DataSourceType
    file_path: Optional[str] = None
    data: Optional[list[dict]] = None
    options: Optional[dict] = None


class ImportResult(BaseModel):
    """Result of a data import operation."""
    success: bool
    records_processed: int = 0
    records_new: int = 0
    records_updated: int = 0
    records_duplicate: int = 0
    records_failed: int = 0
    errors: list[str] = []
    collection_run_id: Optional[str] = None


# Forward reference resolution
ProductDetail.model_rebuild()

