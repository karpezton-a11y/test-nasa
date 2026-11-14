# Test plan (Group 1 DOCX section 11)

Status on Sat 14 Nov 2026 (branch `karnish/phase2-advanced-endpoints`): **373 passed, 8 skipped** (`python -m pytest`; also on every push via GitHub Actions, `.github/workflows/tests.yml`); the 8 skipped are the 4 real-data acceptance tests (run once `real_store.py` and `data/processed/` exist) and the 4 store-conformance tests for Adrian's loader (run once `real_store.py` exists).
"Automated" names the pytest file; ✅ = covered today, ⏳ = pending, with its owner and handoff.

## 1. Section 11 checklist

| # | DOCX §11 area | What is checked | Status / where | Owner |
|---|---|---|---|---|
| 1 | Contract tests | Envelope fields on every success response; typed Pydantic validation of each result | ✅ `test_setup`, `test_light_endpoints`, `test_contract_examples`, `test_report` | M2 (M1 for A–F endpoints) |
| 2 | Contract tests | Every `docs/examples/*.json` validates; error examples use the bare section-I shape; JSON in `contract.md` equals the example files | ✅ `test_contract_examples` | Karnish |
| 3 | Reference test | `/analyze` equals G3's `trend_results_reference.json` (slope, p, CI within 1e-6); `/anomalies`, `/interaction`, `/rainfall/indicators` equal `data/processed/reference/*.json` | ⏳ `/analyze`: Adrian. Advanced endpoints: ✅ checker built and self-tested (`test_real_data_acceptance`), ⏳ runs at H9 | Adrian / Karnish |
| 4 | Invalid input | Unknown region → `INVALID_REGION` | ✅ `test_csv_export`, `test_report` | Karnish |
| 5 | Invalid input | start > end, bad `YYYY-MM`, outside the available period → `INVALID_PERIOD` | ✅ `test_csv_export`, `test_report` | Karnish |
| 6 | Invalid input | 5–9-year period for a trend → `PERIOD_TOO_SHORT` | ✅ `test_csv_export`, `test_report`, `test_mock_generator` (short scenario) | Karnish |
| 7 | Invalid input | Season `XYZ` → `INVALID_SEASON` | ✅ `test_report` | Karnish |
| 8 | Invalid input | Daily request of more than 10 years → `INVALID_PERIOD` (`daily_limit_exceeded`) | ✅ `test_csv_export` | Karnish |
| 9 | Invalid input | `alpha=0.2` → `VALIDATION_ERROR` | ⏳ `/analyze` not built | Adrian |
| 10 | Invalid input | Unknown export type, malformed or unknown report ID, missing fields, extra body fields | ✅ `test_csv_export`, `test_report`, `test_setup` | Karnish |
| 11 | Missing data | ~40% nulls → `INSUFFICIENT_DATA`; 70% boundary passes, 60% fails | ✅ `test_csv_export`, `test_report`, `test_mock_generator` | Karnish |
| 12 | Missing data | Nulls stay `null` in JSON and empty in CSV; real zeros stay 0; no -9999 | ✅ `test_mock_generator`, `test_csv_export`, `test_csv_codec`, `test_contract_examples` | Karnish |
| 13 | Missing data | Charts draw gaps for nulls and for absent months; no fabricated CI band | ✅ `test_report` | Karnish |
| 14 | Report accuracy | PDF text (pypdf) equals the source numbers, formatted; units, data_version and MOCK printed on every page | ✅ `test_report` | Karnish |
| 15 | Report accuracy | No result printed under dates it was not computed for | ✅ `test_report` | Karnish |
| 16 | Report accuracy | Download returns the identical saved bytes; page count is real | ✅ `test_report` | Karnish |
| 17 | CSV | Loads with `pandas.read_csv(comment="#")`; exact float round-trip; special characters decode exactly with `csv_codec.read_export` | ✅ `test_csv_export`, `test_csv_codec` | Karnish |
| 18 | AI guardrails | Causal phrase rejected; invented number rejected; timeout or missing key → template | ⏳ `/explain` | Adrian |
| 19 | Security | No keys in the repo; `.env.example` has no secrets | ✅ `test_deploy_config` (+ `git grep` scan before release) | Karnish |
| 20 | Security | CORS limited to `ALLOWED_ORIGIN`; no wildcard | ✅ `test_setup` | Karnish |
| 21 | Security | Debug off in every environment; 500s carry no traceback or path | ✅ `test_setup`, `test_light_endpoints`, `test_csv_export` | Karnish |
| 22 | Security | Request-body size limit (declared and streamed) | ✅ `test_setup` | Karnish |
| 23 | Security | Rate limit on `/explain` (✅ on `POST /report`: 2 at once → `REPORT_BUSY`, 10/min/client → `RATE_LIMITED`, `Retry-After`; old reports deleted after 1 h / beyond 200) | ⏳ `/explain` (reuse `RequestLimiter`); ✅ `/report`: `test_report_limits` | Adrian / Karnish |
| 24 | Security | Dependencies pinned | ✅ `test_deploy_config` | Karnish |
| 25 | Safety | prod + mock refused; prod + real refuses any non-real loaded asset; no silent mock fallback | ✅ `test_setup`, `test_mock_generator` | Karnish |
| 26 | Mock data | Deterministic (byte-identical); never written to `data/processed/`; no real-looking DOIs | ✅ `test_mock_generator` | Karnish |
| 27 | Performance | PDF under 10 s (local: about 0.35 s; Render free staging: 4.3 s for `POST /report`) | ✅ `test_report` + `scripts/smoke_test.py` | Karnish |
| 28 | Performance | `/analyze` under 2 s on the host | ⏳ smoke test once `/analyze` exists | Adrian |
| 29 | Integration | Full user journey on the deployed URL (desktop and phone) | ⏳ manual, Sat 21:00 and Sun 14:00 | Adrian + G2 + G3 |
| 31 | Advanced endpoints | `/anomalies` (single, `both`, window, `detrended`), `/interaction` (0/6/9/≥10 events, guardrail), `/rainfall/indicators` (3 × 3 × 2), every invalid input, `DATA_NOT_AVAILABLE`, live response = example shape, store result for another request never served | ✅ `test_advanced_endpoints` | Karnish |
| 32 | Report = API | PDF sections are the objects the API serves; G3 methods/limitations hook; AI labels by source; real mode refuses mock/placeholder text; a broken AI module (missing dependency, syntax error, import failure) is logged and never breaks the PDF; a real-mode AI summary containing "mock"/"TODO"/… is dropped, not fatal | ✅ `test_report_hooks` | Karnish |
| 33 | CSV = API | anomalies CSV = `/anomalies`; series/trend CSV = served objects; CSV works when the PDF stack fails | ✅ `test_csv_fidelity` | Karnish |
| 34 | Fallback | snapshot covers every selection, lists unavailable ones, serves from a plain static server, refuses mock with `--require-real`; a 500 or failed PDF fails the run (exit 1, every failure listed) and keeps the previous snapshot; a new snapshot replaces the old one only when complete | ✅ `test_snapshot` | Karnish |
| 35 | Real data | expected file layout (a stray file is not a delivery), dates, units, source IDs, valid_fraction, qc_flag, real provenance, no mock text, at least one reference per endpoint and region, references within 1e-6 | ⏳ skipped until H5/H7/H9 (`test_real_data_acceptance`) | Karnish + Adrian |
| 36 | API consistency | a wrong value of any length gets its own `INVALID_*` code (never 422); `/openapi.json` shows `{"error":{...}}` for every 4xx/5xx with one example per code; CORS exposes `Content-Disposition` and `Retry-After`; an overridden store labels and serves the same data | ✅ `test_api_consistency` | Karnish |
| 37 | Store rules | any store: info complete, unknown selections raise only `ApiError`, repeated calls read no files, 40 parallel calls agree; the checker catches a re-reading store and a raw `KeyError` | ✅ mock + dev stub, ⏳ real store (`test_store_conformance`) | Karnish + Adrian |
| 38 | Smoke script | the script itself passes against the mock app, fails a non-PDF download, a changed guardrail and wrong `data_status`; `DATA_NOT_AVAILABLE` is SKIP only with the flag; missing route fails | ✅ `test_smoke_script` | Karnish |
| 39 | Hardening (audit LOW) | value lists defined once; G–J results frozen; lock file pins every runtime package and Render uses it; `ALLOWED_ORIGIN` format; `nosniff`/`no-referrer` on every response; unexpected 500 keeps CORS headers; typed dev stub; importing `app.main` builds no app; monthly `valid_fraction` always a number, daily null | ✅ `test_low_fixes` | Karnish |
| 30 | Deploy | `smoke_test.py` passes against the URL (18 checks since the advanced endpoints; 12 before) (`--expect-status mock` today, `real` after H5) | ✅ locally; ✅ Render staging 12/12 (Fri 19:34 IST, `--expect-status mock`); ⏳ `real` after H5 | Karnish |

## 2. Manual end-to-end script (Sat 21:00, Sun 14:00)

Run it on the deployed URL, once on a laptop and once on a phone. Write each result in the team chat.

1. `GET /api/v1/health`: `status ok`; `data_status` as expected (`mock` before H5, `real` after).
2. Explorer: regions load and the IGP/TN boxes match their bbox.
3. Trend Lab: IGP AOD 2003-01..2024-12 shows a trend, its CI and p-value. A non-significant result never says "increasing".
4. Anomaly Radar (after H10): the heatmap shows all months, missing months are grey, and the baseline box shows 2003–2024.
5. Interaction (after H10): the guardrail sentence is visible. TN OND or JJAS shows the "too few events" note with no p-value.
6. Report: create the PDF, open it, and check that every page footer says MOCK (staging) or the NASA footer (real), and that the summary numbers match the Trend Lab.
7. CSV: download a series and decode it with `python scripts/decode_csv.py file.csv`. Values match the chart.
8. Errors: choose a period under 10 years → the UI shows "Choose at least 10 years", never a blank screen.

## 3. Pending handoffs that unlock tests

| Handoff | Unlocks rows |
|---|---|
| H5 (Sat 14:30): real monthly series + Member 1's `real_store.py` | 25 (real-mode run), 30 (`--expect-status real`) |
| Member 1's `/analyze`, `/explain` | 3, 9, 18, 23, 28 |
| H9 (Sun 11:00): `trend_results_reference.json`, methods text | 3, report methods section |
| Deployed URL + G2 frontend | 29 |
