# API change log

Every change to an endpoint, field, enum, unit or error code goes here.
After the H3 freeze (Fri 20:15 IST), a change also needs agreement from all
three groups and a `contract_version` bump.

| Date (IST) | contract_version | Change | Author | Agreed by |
|---|---|---|---|---|
| 2026-11-13 | 1.0 (draft) | Skeleton: `/api/v1` base path, success envelope, section 6-I error shape, `GET /health`. | G1 M2 | pending |
| 2026-11-13 | 1.0 (draft) | Proposed starter error codes: `VALIDATION_ERROR` 422, `NOT_FOUND` 404, `METHOD_NOT_ALLOWED` 405, `PAYLOAD_TOO_LARGE` 413 (decision D-02). | G1 M2 | pending |
| 2026-11-13 | 1.0 (draft) | Contract G, H, I draft + new section J (rainfall indicators); examples in `docs/examples/` (decisions G-*, H-*, J-*). | G1 M2 | pending (IM2/IM3) |
| 2026-11-13 | 1.0 (draft) | `GET /variables`, `GET /regions` (list + GeoJSON, feature `id = region_id`), `GET /meta/sources` (nullable `doi`, `access_date`, `citation`). | G1 M2 | pending |
| 2026-11-13 | 1.0 (draft) | `GET /export/csv` (`what` default `series`; 70% coverage gate; nested trend fields as JSON cells; `#` escaped in text cells); new code `INVALID_EXPORT_TYPE` 400. | G1 M2 | pending |
| 2026-11-13 | 1.0 (draft) | `POST /report` (200, envelope `{report_id, url, pages, generated_at}`), `GET /report/{id}` (application/pdf); new codes `INVALID_REPORT_ID` 400, `REPORT_NOT_FOUND` 404; `INVALID_INDICATOR` 400 reserved for `/rainfall/indicators`. | G1 M2 | pending |
| 2026-11-13 | 1.0 (candidate) | IM2: contract v0.1 (G–J) presented, no changes requested; becomes the v1.0 candidate for the IM3 freeze. No field changes. | G1 M2 | IM2 (all groups) |
| 2026-11-13 | 1.0 (draft) | Fix: PDF reports no longer print trend/anomaly/interaction/indicator results computed for a different period or season than requested (shown as "Not available" with the real period); every printed result states its own period. | G1 M2 | n/a (bug fix) |
| 2026-11-13 | 1.0 (draft) | CSV decoder: `csv_codec.read_export` + `scripts/decode_csv.py` restore special characters (`#`, `\`, quotes, newlines, Unicode), `None`, numbers, booleans and JSON cells; header values are escaped per field so `|` cannot split metadata. Wire format unchanged. | G1 M2 | n/a (no wire change) |
| 2026-11-13 | 1.0 (draft) | `GET /anomalies`, `GET /interaction`, `GET /rainfall/indicators` implemented on the store (mock now, real store later, same route). Shapes unchanged from G/H/J. Request rules made explicit: anomalies `start`/`end` optional (default `period_available`, G-9), interaction `season` required (H-7), indicator params all required. | Karnish | pending (contract_decisions.md) |
| 2026-11-13 | 1.0 (draft) | Serving rule for G/H/J: a store object that does not match the request (region, variable/indicator, season, period, detrended) is never served → `INTERNAL_ERROR`. No wire change for correct stores. | Karnish | n/a (safety) |
| 2026-11-13 | 1.0 (draft) | Shared foundation, additive only: `main.py` registers `routers/advanced.py`; new `services/advanced.py` (selection used by API, PDF, CSV). | Karnish | Adrian (FYI, handoff walkthrough) |
| 2026-11-13 | 1.0 (draft) | Fix: trend CSV cells use the API's JSON serialisation (`computed_at` was written as `2026-11-13 12:00:00+05:30`, now ISO `2026-11-13T12:00:00+05:30`). | Karnish | n/a (bug fix) |
| 2026-11-13 | 1.0 (draft) | Shared foundation, behaviour change in dev only: `DATA_MODE=real` without `services/real_store.py` now starts with a marked stub (`services/unavailable_store.py`) that answers `DATA_NOT_AVAILABLE` everywhere; prod still refuses (decision DS-1). | Karnish | Adrian (pending) |
| 2026-11-13 | 1.0 (draft) | PDF: Group 3 `docs/methods.md` hook (methods + `## Limitations` bullets), Adrian's `app.ai.report_summary.summarize` hook (labels "AI-generated explanation of computed results" / "Automatic summary"), real-mode refusal of mock/placeholder text → `REPORT_FAILED` (R-6, R-7). No wire change. | Karnish | pending |
| 2026-11-13 | 1.0 (draft) | Snapshot `manifest.json` format: `{data_status, data_version, contract_version, generated_at, files, unavailable, selections}` (was a flat URL → file map; no consumer yet); `--require-real`. | Karnish | Kavin, Sri Prasath (FYI) |
| 2026-11-14 | 1.0 (draft) | Audit M2: a wrong value of any length gets its domain code. Before, an overlong `region_id`/`variable`/`season`/`indicator`/`what` or a full date (`2003-01-01`) for `start`/`end` gave 422 `VALIDATION_ERROR` (query `max_length` limits); now 400 `INVALID_REGION`/`INVALID_VARIABLE`/`INVALID_SEASON`/`INVALID_INDICATOR`/`INVALID_EXPORT_TYPE`/`INVALID_PERIOD`, as already documented in section I. Same error shape; no echo of the input. | Karnish | pending (Group 2 FYI) |
| 2026-11-14 | 1.0 (draft) | Audit M1: `POST /report` limits. New code `REPORT_BUSY` 503 (2 PDFs already being made); `RATE_LIMITED` 429 (was reserved for `/explain`) now also for `POST /report`, 10 per client per minute. Both send `details.retry_after_s` and a `Retry-After` header. Saved reports older than 1 hour or beyond the newest 200 are deleted (download → `REPORT_NOT_FOUND`, R-5). Examples: `error_REPORT_BUSY.json`, `error_RATE_LIMITED.json`. | Karnish | pending (Group 2: handle 429/503) |
| 2026-11-14 | 1.0 (draft) | Audit M3/M7: `/openapi.json` and `/docs` show the section-I error shape (`ErrorResponse`) with one example per code for every 4xx/5xx; FastAPI's `{"detail": [...]}` schema is gone. CORS exposes `Content-Disposition` and `Retry-After`. Shared `main.py`, additive only. No wire change. | Karnish | n/a (docs/headers) |
| 2026-11-14 | 1.0 (draft) | Audit M6/M8: rules for any `DataStore` written in its docstring and checked by `test_store_conformance.py`; routes label the envelope from the same store that served the data (`envelope(..., store=store)`, optional argument). Shared `services/store.py` docstring and `routers/common.py`, additive only. No wire change. | Karnish | Adrian (FYI) |
| 2026-11-14 | 1.0 (draft) | Audit LOW: every response carries `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`; an unexpected 500 now carries CORS headers (the browser can read `INTERNAL_ERROR`); `ALLOWED_ORIGIN` must be exactly `scheme://host[:port]` (a trailing `/`, path or list now stops startup with a clear message instead of silently blocking the frontend); G–J result objects are frozen. No body/shape change. | Karnish | n/a (headers/config) |


## Adrian integration — 2026-11-14

- Combined current main be2457d with Adrian's final backend implementation, preserving its later audit fixes, dependency lock and CI.
- Added core routes, real loader, science adapter and guarded explanation/PDF hook to the same app. No public scientific field/enum change.
- /explain reuses shared RequestLimiter/Retry-After; core errors are explicitly documented in OpenAPI.
- Loaded no real observations from the research documents. Added source-qualified methods/limitations and a handoff review; actual full-precision files and executable statistical outputs remain missing.
- Real CSV loader accepts optional data_version/method metadata with validation; source IDs/season labels are not silently renamed.
- Existing report/snapshot tests were adapted only where earlier feature absence or missing methods was their assumption. Karnish production modules remain intact.
- Research questions (15/10 baseline eligibility, coverage meaning, raw-p/FDR, seasonal counts, signatures) are recorded in decisions.md, not promoted to scientific approval.

## 2026-11-14 — combined backend release review

- Shared date validation defaults only omitted dates; explicit blank dates now return INVALID_PERIOD across core, anomaly, export and report callers. Exact YYYY-MM matching is enforced.
- `/explain` keeps its admission slot through result resolution and generation. Four concurrent requests per process, existing ten-per-minute quota and Retry-After responses; overload wording refers to explanations.
- Guardrails recognize signed leading-decimal numbers (for example `.123`), preventing unrecognized invented numeric literals from passing checks.
- Karnish report fixes: coverage is calculated for the requested season, matching `/analyze`; a cleanup-directory scan failure is logged without failing a successfully saved PDF.
- Added regression tests for these cases. Refined README setup, mock/real readiness, request validation, limits, report retention and contribution guidance. Public fields/enums and dependency pins are unchanged.

## 2026-11-14 — large daily CSV acceptance coverage

- Added 48,216 deterministic, labelled MOCK daily records plus their checksum manifest for large-file API/export acceptance tests; no application endpoint or public schema changes.
- Added test-only source selection and store injection covering six series, three non-overlapping request windows, leap days, full precision, missing cells, zeros, QC states and production rejection.
- Existing mock generator equality now checks its own scenarios, excluding only qa_large; the separate QA generator owns and verifies that directory. Changing the shared registry requires regenerating both sets of fixtures.
- Generated data is disclosed separately from authored application code; no teammate commit attribution changes.

## 2026-11-14 — sparse daily QA and explanation relation checks

- Added 32,144 explicitly generated MOCK daily inputs for four primary series with recurrent gaps and a complete 2020–2021 outage. The previous 48,216-row normal CSV is byte-for-byte unchanged.
- Test-only selection preserves null slots and real zeros; sparse CSV downloads return INSUFFICIENT_DATA as JSON; missing alternate sources never fall back; outage charts retain gaps; production rejects the QA store.
- Explanation guardrails now compare p-value operators/labels as well as numeric literals. Changed operators, Unicode variants and noncanonical prose claims cause safe template fallback. Markdown/reference links and recognized HTTP/data/JavaScript URI text are rejected, including zero-width obfuscation.
- No public schema/enum, scientific statistic, dependency pin, runtime data scenario or teammate attribution changed. Direct main publication is explicitly authorized by Adrian.


## 2026-11-14 — trend engine, discovery and insight routes (additive)

- New `analysis/trendlib` 1.0.0 drives `/analyze` and `/compare` in both data modes. Responses keep the frozen TrendResult shape; values are now computed. Mock results add a leading "MOCK series" limitation.
- `result_id` gains `_aX.XX` / `_xlc` suffixes for non-default alpha / exclude_low_coverage.
- Omitted analyze dates default to the variable's own observed span.
- New routes: `GET /catalog`, `GET /discover/questions`, `POST /discover`, `GET /demos`, `GET /research/series`, `GET /research/series/{research_id}`, `POST /analyze/detail`, `POST /analyze/series`, `GET /scan`. All use the standard envelope and error shape.
- `/health.trendlib_version` reports the bundled version ("1.0.0") instead of null.
- New scripts: `fetch_nasa_power.py`, `import_giovanni.py`, `run_demo.py`. The smoke test adds five checks (26 total).

## 15 November 2026

- `GET /api/v1/rainfall/indicators?indicator=rx5day` now returns data for IGP and TN (annual, JJAS, OND), unit mm.
- `POST /api/v1/analyze/series` with empty `dates`/`values`, or dates that cannot be parsed, returns 422 `VALIDATION_ERROR` (previously 500 `INTERNAL_ERROR`).

