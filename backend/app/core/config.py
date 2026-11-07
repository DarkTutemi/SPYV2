"""
US WIN HUNTER — Core Configuration

Environment-variable driven configuration with Pydantic Settings.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


PROJECT_ROOT = Path(__file__).resolve().parents[2]  # backend/app/core -> backend
REPO_ROOT = PROJECT_ROOT.parent
(REPO_ROOT / "data").mkdir(exist_ok=True)


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    # ── Application ──────────────────────────────────────────────────────
    app_name: str = "us-win-hunter"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = True
    log_level: str = "INFO"
    secret_key: str = "change-me-to-a-random-string-in-production"

    # ── Database ─────────────────────────────────────────────────────────
    database_url: str = f"sqlite+aiosqlite:///{(REPO_ROOT / 'data' / 'winhunter.db').as_posix()}"

    # ── Meta Ad Library ──────────────────────────────────────────────────
    meta_access_token: str = ""
    meta_app_id: str = ""
    meta_app_secret: str = ""

    # ── Reddit ───────────────────────────────────────────────────────────
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "USWinHunter/1.0"

    # ── Apify ────────────────────────────────────────────────────────────
    apify_api_token: str = ""
    apify_primary_actor: str = "automation-lab/facebook-ads-library"
    apify_fallback_actor: str = "curious_coder/facebook-ads-library-scraper"
    apify_daily_budget_usd: float = 5.0
    apify_monthly_budget_usd: float = 50.0
    apify_max_ads_per_query: int = 100
    apify_request_timeout_seconds: int = 120
    apify_auto_collection_enabled: bool = False

    # ── LLM ──────────────────────────────────────────────────────────────
    llm_provider: str = "google"
    llm_api_key: str = ""
    llm_model: str = "gemini-2.0-flash"

    # ── Collection ───────────────────────────────────────────────────────
    max_concurrent_jobs: int = 3
    default_collection_interval_minutes: int = 360
    default_rate_limit_rpm: int = 30

    # ── Emergence Score Weights ──────────────────────────────────────────
    emergence_w_advertiser_accel: float = 0.30
    emergence_w_creative_accel: float = 0.25
    emergence_w_ad_persistence: float = 0.20
    emergence_w_signal_recency: float = 0.15
    emergence_w_demand_confirm: float = 0.10

    # ── Evidence Confidence Weights ──────────────────────────────────────
    confidence_w_coverage: float = 0.30
    confidence_w_independent_sources: float = 0.25
    confidence_w_product_identity: float = 0.20
    confidence_w_advertiser_independence: float = 0.15
    confidence_w_evidence_links: float = 0.10

    # ── Bundle Potential Weights ─────────────────────────────────────────
    bundle_w_multi_unit_necessity: float = 0.30
    bundle_w_functional_benefit: float = 0.25
    bundle_w_aov_fit: float = 0.20
    bundle_w_usage_frequency: float = 0.15
    bundle_w_decision_simplicity: float = 0.10

    model_config = {
        "env_file": str(PROJECT_ROOT.parent / ".env"),
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }

    @property
    def is_sqlite(self) -> bool:
        return "sqlite" in self.database_url

    @property
    def emergence_weights(self) -> dict[str, float]:
        return {
            "advertiser_accel": self.emergence_w_advertiser_accel,
            "creative_accel": self.emergence_w_creative_accel,
            "ad_persistence": self.emergence_w_ad_persistence,
            "signal_recency": self.emergence_w_signal_recency,
            "demand_confirm": self.emergence_w_demand_confirm,
        }

    @property
    def confidence_weights(self) -> dict[str, float]:
        return {
            "coverage": self.confidence_w_coverage,
            "independent_sources": self.confidence_w_independent_sources,
            "product_identity": self.confidence_w_product_identity,
            "advertiser_independence": self.confidence_w_advertiser_independence,
            "evidence_links": self.confidence_w_evidence_links,
        }

    @property
    def bundle_weights(self) -> dict[str, float]:
        return {
            "multi_unit_necessity": self.bundle_w_multi_unit_necessity,
            "functional_benefit": self.bundle_w_functional_benefit,
            "aov_fit": self.bundle_w_aov_fit,
            "usage_frequency": self.bundle_w_usage_frequency,
            "decision_simplicity": self.bundle_w_decision_simplicity,
        }


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

