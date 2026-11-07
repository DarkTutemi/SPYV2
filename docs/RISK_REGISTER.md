# Risk Register

| ID | Risk | Impact | Mitigation |
|---|---|---|---|
| R1 | No official US commercial-ad API | High | Import pipeline; Apify adapter with explicit approval for paid runs |
| R2 | ToS/legal risk of third-party scraped Meta data | High | Operator decision; provenance stored per record; no in-house scraping/CAPTCHA bypass |
| R3 | Ad count misread as sales | High | Labeling in API/UI; scores described as activity signals |
| R4 | False merges of different products | Medium | No auto-merge on semantic similarity; reversible merge history; test enforces |
| R5 | Coverage gaps create false momentum | High | coverage fields on runs/metrics; confidence score penalizes low coverage |
| R6 | Heuristic weights not validated | Medium | Configurable weights, weight snapshot stored with each score, recalibration planned |
| R7 | Reddit/Amazon access not approved | Medium | Sources disabled; file import |
| R8 | Unofficial Trends libs break | Low | Adapter isolation; label as unofficial |
| R9 | SQLite concurrency limits | Low | Single operator; PostgreSQL URL supported |

