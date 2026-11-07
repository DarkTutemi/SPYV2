# Database Schema

Source of truth: [`backend/app/models/models.py`](../backend/app/models/models.py). All timestamps are UTC (`DateTime(timezone=True)`); snapshot/metric dates are `YYYY-MM-DD` UTC strings.

| Table | Purpose | Key constraints |
|---|---|---|
| data_sources | Source registry | unique name |
| collection_jobs / collection_runs | Job definition / execution with counts, errors, coverage notes | — |
| source_records | Raw payload + geo context + geo confidence; duplicate flag | idx (source_type, external_id) |
| advertisers | Page ID, domains, verification evidence | unique facebook_page_id |
| advertiser_relationships | Suspected vs verified links, evidence | unique (a, b, type) |
| advertisements | Ad with advertiser-reported start, first/last seen | unique (source_type, external_id) |
| advertisement_snapshots | Daily active status | unique (ad, date) |
| creatives / creative_fingerprints | Asset + hashes (sha256, phash, embedding) | — |
| products, product_clusters, product_cluster_members | Identity + typed relationships (identical creative / product / variant / category) | unique (cluster, product) |
| product_merge_history | Reversible merge/split audit | — |
| landing_pages, product_offers, bundle_offers | Observed offers; bundle status offered/promoted/purchased | — |
| pain_clusters, pain_evidence | Pain groups + language group + anonymized author | — |
| trend_observations | Keyword interest by date, US scope | — |
| product_daily_metrics | Derived daily counts + coverage completeness | unique (product, date) |
| opportunity_scores | 3 scores + components + weight snapshot | unique (product, date) |
| evidence_links | Typed evidence for any entity | — |
| analyst_reviews | Manual verdicts | — |

`EvidenceType` (observed_fact / derived_metric / ai_inference / unverified_hypothesis) is stored on offers, bundles, pain evidence, metrics and evidence links.

