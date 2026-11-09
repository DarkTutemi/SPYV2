"""
US WIN HUNTER — Data Import Service

Handles ingestion of legitimately obtained datasets into the system.
Supports Meta Ad Library data (via Apify), manual CSV/JSON imports,
and other structured data sources.

Implements idempotent upserts and duplicate detection.
"""

from __future__ import annotations

import csv
import json
import logging
import re
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.models import (
    Advertisement,
    Advertiser,
    BundleOffer,
    BundleMechanism,
    CollectionJob,
    CollectionJobStatus,
    CollectionRun,
    ConfidenceLevel,
    DataSource,
    DataSourceType,
    EvidenceType,
    Product,
    SourceRecord,
)
from app.schemas.schemas import ImportResult

logger = logging.getLogger(__name__)


class ImportService:
    """Service for importing data from various sources."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Entry Point ──────────────────────────────────────────────────────

    async def import_data(
        self,
        source_type: DataSourceType,
        data: Optional[list[dict]] = None,
        file_path: Optional[str] = None,
        options: Optional[dict] = None,
    ) -> ImportResult:
        """Import data from a list of records or a file path."""
        options = options or {}

        # Load data from file if needed
        if data is None and file_path:
            data = self._load_file(file_path)

        if not data:
            return ImportResult(success=False, errors=["No data provided"])

        # Ensure data source exists (synthetic/demo data is registered under a separate, labeled source)
        source = await self._ensure_data_source(source_type, synthetic=bool(options.get("is_synthetic")))

        # Create collection job + run
        job = CollectionJob(
            data_source_id=source.id,
            name=f"import_{source_type.value}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
            job_type="manual_import",
        )
        self.db.add(job)
        await self.db.flush()

        run = CollectionRun(
            job_id=job.id,
            status=CollectionJobStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(run)
        await self.db.flush()

        # Dispatch to handler
        try:
            if source_type == DataSourceType.META_AD_LIBRARY:
                result = await self._import_meta_ads(data, run, options)
            elif source_type == DataSourceType.MANUAL_IMPORT:
                result = await self._import_generic(data, run, options)
            else:
                result = await self._import_generic(data, run, options)

            run.status = CollectionJobStatus.COMPLETED
            run.completed_at = datetime.now(timezone.utc)
            run.records_fetched = result.records_processed
            run.records_new = result.records_new
            run.records_updated = result.records_updated
            run.records_duplicate = result.records_duplicate

            source.last_successful_collection = datetime.now(timezone.utc)

            result.collection_run_id = run.id
            return result

        except Exception as e:
            logger.exception("Import failed: %s", e)
            run.status = CollectionJobStatus.FAILED
            run.completed_at = datetime.now(timezone.utc)
            run.errors = {"error": str(e)}
            return ImportResult(success=False, errors=[str(e)])

    # ── Meta Ad Library Import ───────────────────────────────────────────

    async def _import_meta_ads(
        self, records: list[dict], run: CollectionRun, options: dict
    ) -> ImportResult:
        """Import Meta Ad Library data (typically from Apify scraper output)."""
        result = ImportResult(success=True)

        for record in records:
            result.records_processed += 1
            try:
                # Store raw source record
                source_record = SourceRecord(
                    collection_run_id=run.id,
                    source_type=DataSourceType.META_AD_LIBRARY,
                    external_id=record.get("id") or record.get("adArchiveID"),
                    raw_data=record,
                    geographic_context=self._extract_geo_context(record),
                    geo_confidence=self._assess_geo_confidence(record),
                )

                # Check for duplicate
                ext_id = source_record.external_id
                if ext_id:
                    existing = await self.db.execute(
                        select(SourceRecord).where(
                            SourceRecord.source_type == DataSourceType.META_AD_LIBRARY,
                            SourceRecord.external_id == ext_id,
                        ).limit(1)
                    )
                    if existing.scalar_one_or_none():
                        source_record.is_duplicate = True
                        result.records_duplicate += 1
                        self.db.add(source_record)
                        continue

                self.db.add(source_record)

                # Extract and upsert advertiser
                advertiser = await self._upsert_advertiser_from_meta(record)

                # Extract and upsert advertisement
                ad = await self._upsert_advertisement_from_meta(record, advertiser)

                # Extract product if identifiable
                product = await self._extract_product_from_meta_ad(record, ad, advertiser)

                result.records_new += 1
                source_record.is_processed = True

            except Exception as e:
                logger.warning("Failed to process record: %s", e)
                result.records_failed += 1
                result.errors.append(str(e))

        return result

    async def _upsert_advertiser_from_meta(self, record: dict) -> Advertiser:
        """Extract or update advertiser from a Meta ad record."""
        page_id = str(record.get("pageId") or record.get("page_id") or "")
        page_name = record.get("pageName") or record.get("page_name") or "Unknown"

        if page_id:
            existing = await self.db.execute(
                select(Advertiser).where(Advertiser.facebook_page_id == page_id).limit(1)
            )
            advertiser = existing.scalar_one_or_none()
            if advertiser:
                advertiser.last_seen_at = datetime.now(timezone.utc)
                if page_name and page_name != "Unknown":
                    advertiser.name = page_name
                return advertiser

        # Lookup by normalized name as fallback
        norm = page_name.lower().strip()
        existing = await self.db.execute(
            select(Advertiser).where(
                Advertiser.normalized_name == norm,
                Advertiser.source_type == DataSourceType.META_AD_LIBRARY,
            ).limit(1)
        )
        advertiser = existing.scalar_one_or_none()
        if advertiser:
            advertiser.last_seen_at = datetime.now(timezone.utc)
            if page_id and not advertiser.facebook_page_id:
                advertiser.facebook_page_id = page_id
            return advertiser

        # Create new
        # Try to extract domain from ad links
        domain = None
        link_url = record.get("linkUrl") or record.get("link_url") or ""
        if link_url:
            try:
                parsed = urlparse(link_url)
                domain = parsed.netloc.lower().replace("www.", "")
            except Exception:
                pass

        advertiser = Advertiser(
            name=page_name,
            normalized_name=norm,
            facebook_page_id=page_id if page_id else None,
            domain=domain,
            source_type=DataSourceType.META_AD_LIBRARY,
            external_id=page_id if page_id else None,
            country="US",
        )
        self.db.add(advertiser)
        await self.db.flush()
        return advertiser

    async def _upsert_advertisement_from_meta(
        self, record: dict, advertiser: Advertiser
    ) -> Advertisement:
        """Extract or update advertisement from a Meta ad record."""
        ext_id = str(record.get("id") or record.get("adArchiveID") or "")

        # Parse dates
        start_date = self._parse_date(
            record.get("startDate") or record.get("ad_delivery_start_time")
        )

        if ext_id:
            existing = await self.db.execute(
                select(Advertisement).where(
                    Advertisement.source_type == DataSourceType.META_AD_LIBRARY,
                    Advertisement.external_id == ext_id,
                ).limit(1)
            )
            ad = existing.scalar_one_or_none()
            if ad:
                ad.last_seen_at = datetime.now(timezone.utc)
                ad.is_active = record.get("isActive", record.get("is_active", True))
                if not ad.advertiser_start_date and start_date:
                    ad.advertiser_start_date = start_date
                return ad

        # Build ad URL
        ad_url = record.get("snapshotUrl") or record.get("ad_snapshot_url") or ""
        if not ad_url and ext_id:
            ad_url = f"https://www.facebook.com/ads/library/?id={ext_id}"

        # Creative URL
        creative_url = None
        images = record.get("images") or record.get("ad_creative_link_images") or []
        if isinstance(images, list) and images:
            creative_url = images[0] if isinstance(images[0], str) else images[0].get("url", "")
        elif isinstance(images, str):
            creative_url = images

        # Creative type
        creative_type = "image"
        if record.get("videos") or record.get("ad_creative_videos"):
            creative_type = "video"

        # Landing page
        landing_url = record.get("linkUrl") or record.get("link_url") or ""

        # Body text
        body = ""
        bodies = record.get("bodies") or record.get("ad_creative_bodies") or []
        if isinstance(bodies, list):
            body = " ".join(str(b) for b in bodies)
        elif isinstance(bodies, str):
            body = bodies

        title = record.get("title") or record.get("ad_creative_link_titles") or ""
        if isinstance(title, list):
            title = " | ".join(str(t) for t in title)

        # Determine target country
        target_countries = record.get("targetCountries") or record.get("delivery_by_region") or []
        target_country = "US"
        if isinstance(target_countries, list):
            if target_countries and isinstance(target_countries[0], str):
                target_country = target_countries[0] if "US" in target_countries else target_countries[0]
            elif not target_countries:
                target_country = "US"  # default assumption

        ad = Advertisement(
            external_id=ext_id or f"unknown_{datetime.now(timezone.utc).timestamp()}",
            source_type=DataSourceType.META_AD_LIBRARY,
            advertiser_id=advertiser.id,
            title=title,
            body=body,
            creative_url=creative_url,
            landing_page_url=landing_url,
            ad_url=ad_url,
            creative_type=creative_type,
            target_country=target_country,
            is_active=record.get("isActive", record.get("is_active", True)),
            advertiser_start_date=start_date,
            raw_data=record,
        )
        self.db.add(ad)
        await self.db.flush()
        return ad

    async def _extract_product_from_meta_ad(
        self, record: dict, ad: Advertisement, advertiser: Advertiser
    ) -> Optional[Product]:
        """Try to extract product information from ad content."""
        title = ad.title or ""
        body = ad.body or ""
        landing_url = ad.landing_page_url or ""

        # Simple product name extraction: use title if meaningful
        product_name = title.strip()
        if not product_name or len(product_name) < 3:
            # Try to extract from body first sentence
            if body:
                first_line = body.split("\n")[0].strip()
                if len(first_line) > 5:
                    product_name = first_line[:200]

        if not product_name or len(product_name) < 3:
            return None

        # Normalize name
        norm_name = re.sub(r'[^\w\s]', '', product_name.lower()).strip()
        norm_name = re.sub(r'\s+', ' ', norm_name)

        # Check for existing product by normalized name
        existing = await self.db.execute(
            select(Product).where(Product.normalized_name == norm_name).limit(1)
        )
        product = existing.scalar_one_or_none()
        if product:
            product.last_seen_at = datetime.now(timezone.utc)
            ad.product_id = product.id
            return product

        # Create new product
        geo_confidence = self._assess_geo_confidence(record)
        product = Product(
            name=product_name[:500],
            normalized_name=norm_name[:500],
            description=body[:2000] if body else None,
            image_url=ad.creative_url,
            source_url=landing_url or ad.ad_url,
            target_country="US",
            us_relevance_confidence=geo_confidence,
            source_type=DataSourceType.META_AD_LIBRARY,
            functional_use_case=None,
            customer_pain=None,
        )
        self.db.add(product)
        await self.db.flush()

        ad.product_id = product.id
        return product

    # ── Generic Import ───────────────────────────────────────────────────

    async def _import_generic(
        self, records: list[dict], run: CollectionRun, options: dict
    ) -> ImportResult:
        """Generic import for structured data with flexible field mapping."""
        result = ImportResult(success=True)
        entity_type = options.get("entity_type", "auto")

        for record in records:
            result.records_processed += 1
            try:
                # Store raw source record
                source_record = SourceRecord(
                    collection_run_id=run.id,
                    source_type=DataSourceType.MANUAL_IMPORT,
                    external_id=record.get("id") or record.get("external_id"),
                    raw_data=record,
                    geographic_context=record.get("country", "US"),
                    geo_confidence=ConfidenceLevel.MEDIUM,
                )
                self.db.add(source_record)

                if entity_type == "product" or "product_name" in record:
                    await self._import_product_record(record)
                elif entity_type == "advertiser" or "page_id" in record:
                    await self._import_advertiser_record(record)

                result.records_new += 1
                source_record.is_processed = True

            except Exception as e:
                logger.warning("Failed to process generic record: %s", e)
                result.records_failed += 1
                result.errors.append(str(e))

        return result

    async def _import_product_record(self, record: dict) -> Product:
        """Import a single product record."""
        name = record.get("product_name") or record.get("name") or "Unknown"
        norm_name = re.sub(r'[^\w\s]', '', name.lower()).strip()
        norm_name = re.sub(r'\s+', ' ', norm_name)

        existing = await self.db.execute(
            select(Product).where(Product.normalized_name == norm_name).limit(1)
        )
        product = existing.scalar_one_or_none()
        if product:
            product.last_seen_at = datetime.now(timezone.utc)
            return product

        product = Product(
            name=name[:500],
            normalized_name=norm_name[:500],
            description=record.get("description"),
            category=record.get("category"),
            image_url=record.get("image_url"),
            source_url=record.get("source_url") or record.get("url"),
            min_price_usd=record.get("min_price") or record.get("price"),
            max_price_usd=record.get("max_price") or record.get("price"),
            target_country=record.get("country", "US"),
            source_type=DataSourceType.MANUAL_IMPORT,
            external_id=record.get("id") or record.get("external_id"),
            raw_data=record,
        )
        self.db.add(product)
        await self.db.flush()
        return product

    async def _import_advertiser_record(self, record: dict) -> Advertiser:
        """Import a single advertiser record."""
        page_id = str(record.get("page_id", ""))
        name = record.get("name") or record.get("page_name") or "Unknown"
        norm = name.lower().strip()

        if page_id:
            existing = await self.db.execute(
                select(Advertiser).where(Advertiser.facebook_page_id == page_id).limit(1)
            )
            adv = existing.scalar_one_or_none()
            if adv:
                adv.last_seen_at = datetime.now(timezone.utc)
                return adv

        adv = Advertiser(
            name=name,
            normalized_name=norm,
            facebook_page_id=page_id if page_id else None,
            domain=record.get("domain"),
            source_type=DataSourceType.MANUAL_IMPORT,
            external_id=page_id or record.get("id"),
            country=record.get("country", "US"),
        )
        self.db.add(adv)
        await self.db.flush()
        return adv

    # ── Helpers ──────────────────────────────────────────────────────────

    async def _ensure_data_source(self, source_type: DataSourceType, synthetic: bool = False) -> DataSource:
        """Get or create the DataSource registry row for this source type."""
        name = f"{source_type.value}_import" + ("_SYNTHETIC_DEMO" if synthetic else "")
        res = await self.db.execute(select(DataSource).where(DataSource.name == name))
        source = res.scalar_one_or_none()
        if source is None:
            source = DataSource(name=name, source_type=source_type, geographic_coverage="US",
                                config={"is_synthetic": synthetic},
                                notes=("SYNTHETIC DEMO DATA — not real market evidence" if synthetic
                                       else "Created automatically by file/JSON import"))
            self.db.add(source)
            await self.db.flush()
        return source

    def _load_file(self, file_path: str) -> list[dict]:
        """Load data from a JSON or CSV file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if path.suffix.lower() == ".json":
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    # Could be wrapped in a results key
                    for key in ("results", "data", "items", "records", "ads"):
                        if key in data and isinstance(data[key], list):
                            return data[key]
                    return [data]
                return data

        elif path.suffix.lower() in (".csv", ".tsv"):
            delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=delimiter)
                return list(reader)

        elif path.suffix.lower() == ".jsonl":
            records = []
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
            return records

        else:
            raise ValueError(f"Unsupported file format: {path.suffix}")

    def _extract_geo_context(self, record: dict) -> str:
        """Extract geographic context from a record."""
        geo_evidence = record.get("geo_evidence_type")
        if geo_evidence == "EXPLICIT_US_TARGETING":
            return "US (Explicit Targeting)"
        elif geo_evidence == "OBSERVED_US_DELIVERY":
            return "US (Observed Regional Delivery)"
        elif geo_evidence == "US_SEARCH_FILTER":
            return "US (Search Filter - Not Confirmed Targeting)"
        elif geo_evidence == "NON_US_TARGETING":
            countries = record.get("targetCountries") or []
            return f"Non-US: {countries}"

        countries = record.get("targetCountries") or record.get("delivery_by_region") or []
        if isinstance(countries, list):
            if "US" in countries:
                return "US"
            if countries:
                return str(countries[0])
        # Check currency
        currency = record.get("currency", "")
        if currency == "USD":
            return "US (Currency USD)"  # But not definitive evidence
        return "unknown"

    def _assess_geo_confidence(self, record: dict) -> ConfidenceLevel:
        """Assess confidence of US geographic targeting."""
        geo_conf = record.get("geo_confidence")
        if geo_conf == "HIGH":
            return ConfidenceLevel.HIGH
        elif geo_conf == "MEDIUM":
            return ConfidenceLevel.MEDIUM
        elif geo_conf == "LOW":
            return ConfidenceLevel.LOW

        geo_evidence = record.get("geo_evidence_type")
        if geo_evidence in ("EXPLICIT_US_TARGETING", "OBSERVED_US_DELIVERY"):
            return ConfidenceLevel.HIGH
        elif geo_evidence == "US_SEARCH_FILTER":
            return ConfidenceLevel.MEDIUM

        countries = record.get("targetCountries") or record.get("delivery_by_region") or []
        if isinstance(countries, list) and "US" in countries:
            return ConfidenceLevel.HIGH

        # Explicit US targeting in impressions
        impressions = record.get("impressionsByRegion") or {}
        if isinstance(impressions, dict) and any("US" in str(k) or "United States" in str(k) for k in impressions):
            return ConfidenceLevel.HIGH

        # Currency alone is not sufficient
        currency = record.get("currency", "")
        if currency == "USD":
            return ConfidenceLevel.LOW  # As per spec: USD alone is not evidence

        return ConfidenceLevel.UNKNOWN

    def _parse_date(self, value: Any) -> Optional[datetime]:
        """Parse a date from various formats."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(value, tz=timezone.utc)
            except (OSError, ValueError):
                return None

        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%d/%m/%Y",
        ):
            try:
                dt = datetime.strptime(str(value), fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
        return None

