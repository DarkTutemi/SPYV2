import asyncio
import os
import sys
import json
import hashlib
from datetime import datetime, timezone
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.database import async_session_factory
from app.models.models import (
    Advertisement,
    AdvertisementSnapshot,
    Advertiser,
    CollectionRun,
    DataSourceType,
    Product,
    SourceRecord,
    SnapshotObservationQuality,
)

async def establish_baseline():
    async with async_session_factory() as db:
        print("Gathering authentic ads for T0 longitudinal baseline...")
        ads_stmt = select(Advertisement).where(Advertisement.is_synthetic == False)
        ads = list((await db.execute(ads_stmt)).scalars().all())

        advs = {a.id: a for a in (await db.execute(select(Advertiser))).scalars().all()}
        prods = {p.id: p for p in (await db.execute(select(Product))).scalars().all()}
        runs = {r.id: r for r in (await db.execute(select(CollectionRun))).scalars().all()}
        srecs = {r.external_id: r for r in (await db.execute(select(SourceRecord).where(SourceRecord.is_synthetic == False))).scalars().all()}

        baseline_records = []
        snapshots_created = 0

        for ad in ads:
            adv = advs.get(ad.advertiser_id)
            prod = prods.get(ad.product_id)
            srec = srecs.get(ad.external_id)

            # Generate creative fingerprint
            creative_content = f"{ad.creative_url or ''}|{ad.title or ''}|{(ad.body or '')[:100]}"
            fingerprint = hashlib.sha256(creative_content.encode("utf-8")).hexdigest()[:16]

            # Determine collection run id
            c_run_id = srec.collection_run_id if srec else None
            c_run_apify_id = runs.get(c_run_id).errors.get("apify_run_id") if (c_run_id and c_run_id in runs and runs[c_run_id].errors) else None

            # T0 date
            t0_date = "2026-11-09"
            t14_target = "2026-11-23"

            baseline_entry = {
                "ad_archive_id": ad.external_id,
                "facebook_page_id": adv.facebook_page_id if adv else None,
                "advertiser_name": adv.name if adv else "Unknown",
                "product_id": ad.product_id,
                "product_name": prod.name if prod else "Unassociated",
                "product_category": prod.category if prod else "General",
                "first_observed_date": ad.first_seen_at.strftime("%Y-%m-%d %H:%M:%S UTC") if ad.first_seen_at else "2026-11-09",
                "original_ad_start_date": ad.advertiser_start_date.strftime("%Y-%m-%d") if ad.advertiser_start_date else None,
                "original_active_status": "ACTIVE" if ad.is_active else "INACTIVE",
                "original_creative_fingerprint": fingerprint,
                "original_landing_page": ad.landing_page_url,
                "original_title": ad.title,
                "original_body_snippet": (ad.body or "")[:120],
                "baseline_collection_run_id": c_run_id,
                "baseline_apify_run_id": c_run_apify_id,
                "t0_snapshot_date": t0_date,
                "t14_followup_date": t14_target,
                "t14_followup_protocol": {
                    "method": "PUBLIC_META_AD_LIBRARY_LOOKUP",
                    "url": ad.ad_url or f"https://www.facebook.com/ads/library/?id={ad.external_id}",
                    "allowed_statuses": [
                        "OBSERVED_ACTIVE",
                        "OBSERVED_INACTIVE",
                        "NOT_FOUND",
                        "ACCESS_ERROR",
                        "UNKNOWN"
                    ],
                    "interpretation_rules": [
                        "NOT_FOUND or ACCESS_ERROR must NOT be classified as ad stopped.",
                        "Campaign survival does NOT imply ROAS or profit."
                    ]
                }
            }
            baseline_records.append(baseline_entry)

            # Insert/update AdvertisementSnapshot in database
            snap_stmt = select(AdvertisementSnapshot).where(
                AdvertisementSnapshot.advertisement_id == ad.id,
                AdvertisementSnapshot.snapshot_date == t0_date
            )
            existing_snap = (await db.execute(snap_stmt)).scalars().first()
            if not existing_snap:
                new_snap = AdvertisementSnapshot(
                    advertisement_id=ad.id,
                    snapshot_date=t0_date,
                    is_active=bool(ad.is_active),
                    source_type=DataSourceType.META_AD_LIBRARY,
                    collection_run_id=c_run_id,
                    observation_quality=SnapshotObservationQuality.GENUINE_SOURCE_OBSERVATION.value,
                    raw_snapshot={
                        "creative_fingerprint": fingerprint,
                        "ad_archive_id": ad.external_id,
                        "t0_status": "ACTIVE" if ad.is_active else "INACTIVE",
                        "baseline_run": c_run_apify_id
                    }
                )
                db.add(new_snap)
                snapshots_created += 1

        await db.commit()
        print(f"Committed {snapshots_created} new T0 snapshots to AdvertisementSnapshot table.")

        output_file = os.path.join(os.path.dirname(__file__), "t0_longitudinal_baseline.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(baseline_records, f, indent=2, ensure_ascii=False)
        print(f"Exported {len(baseline_records)} baseline records to {output_file}.")

if __name__ == "__main__":
    asyncio.run(establish_baseline())

