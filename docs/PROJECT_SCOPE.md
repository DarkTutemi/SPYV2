# Project Scope — US WIN HUNTER

Private internal tool for one dropshipping operator. It discovers emerging **physical** products in the **US market** that have **natural multi-unit bundle demand** and a plausible **\$30–\$90 AOV**, using evidence rather than generic "winning product" lists.

## In scope
- Advertiser graph discovery (Engine A), creative/product fingerprinting (B), temporal ad intelligence (C), pain discovery (D), reverse competitor spy (E), bundle intelligence (F).
- Persistent storage with provenance, historical snapshots, explainable scoring (Emergence, Evidence Confidence, Bundle Potential).
- Internal research dashboard.

## Out of scope
Store creation, landing pages, ad campaign management/launching, fulfillment, email, support, non-US geographies, automated purchasing.

## Principles
- US only. USD pricing alone is never US evidence.
- Observed facts, derived metrics, AI inferences and hypotheses are stored and displayed separately (`EvidenceType`).
- Unknown is displayed as "Unknown" / "Insufficient evidence". No fabricated data, charts or collector runs.
- Ad count ≠ sales. `first_seen_at` ≠ launch date. Bundle offered ≠ bundle purchased.

