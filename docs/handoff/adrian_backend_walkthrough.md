# Backend walkthrough for Adrian (G1 M1)

From Karnish (G1 M2), branch `karnish/phase2-advanced-endpoints`. Goal: one app skeleton, one set of schemas,
one store interface. Nothing here is approved until you agree. Open items are listed in
[contract_decisions.md](contract_decisions.md) (sign-off "Adrian").

## 1. What exists (reuse it, do not rebuild)

| Area | File | What it does |
|---|---|---|
| App factory | `backend/app/main.py` | `create_app(settings=None, store=None)`; lifespan runs the startup guard, then `app.state.store`; `debug=False`; CORS = one origin; routers under `/api/v1`. Run: `uvicorn app.main:app --app-dir backend --port 8000`. |
| Config | `backend/app/config.py` | `load_settings(env=None, env_file=REPO_ROOT/".env") -> Settings` (frozen). `check_startup_rules(settings)` refuses `APP_ENV=prod` + `DATA_MODE=mock`. |
| Errors | `backend/app/errors.py` | `ApiError`, `api_error(code, message, details=None)` (looks the HTTP status up), `error_response(...)`, `register_error_handlers(app)`. Validation errors → `VALIDATION_ERROR` without echoing input; anything unexpected → logged + sanitised `INTERNAL_ERROR`. |
| Envelope | `backend/app/schemas.py`, `backend/app/routers/common.py` | `Envelope[T]`, `make_envelope(...)`, `now_ist()`; routers call `envelope(request, result)`: provenance comes from `store.info`, never from `DATA_MODE`. |
| Models A–F | `backend/app/schemas.py` | **Provisional transcription of your A–F** so my code could type-check. Yours to replace (keep field names, or tell me what changes). |
| Models G–J | `backend/app/advanced_schemas.py` | Mine: anomalies, interaction, indicators, report request/response, error models. |
| Store | `backend/app/services/store.py` | `DataStore` protocol (below), `MockStore`, `build_store`, `verify_store`, `get_store`. |
| Validation | `backend/app/services/validation.py` | Shared helpers (§4). |
| Selection (G/H/J) | `backend/app/services/advanced.py` | `anomalies_for`, `interaction_for`, `indicator_for`, `find_region`; refuses a store object that answers a different request. |
| Body limit | `backend/app/middleware.py` | `BodySizeLimitMiddleware` (declared and streamed bodies). |

Config keys (`.env.example`): `APP_NAME`, `APP_ENV` (dev\|prod), `DATA_MODE` (mock\|real), `MOCK_SCENARIO`
(normal\|sparse\|short), `DATA_VERSION` (optional pin), `CONTRACT_VERSION`, `PORT`, `LOG_LEVEL`, `ALLOWED_ORIGIN`
(one origin, no `*`), `REPORTS_DIR`, `MOCK_DIR`, `PROCESSED_DIR`, `MAX_BODY_BYTES`, `LLM_API_KEY`.
`LLM_PROVIDER`/`LLM_MODEL` are in `.env.example` for you but `config.py` does not read them yet: add them to
`DEFAULTS` + `Settings` when the AI module needs them.

## 2. Ownership

| Yours (replace or add) | Mine (please ask before editing) | Shared (additive changes only, logged in `docs/api-change-log.md`) |
|---|---|---|
| `schemas.py` A–F, `services/real_store.py`, routers for `/timeseries`, `/analyze`, `/compare`, `/explain`, `app/ai/`, `README.md`, `docs/decisions.md` | `advanced_schemas.py`, `routers/advanced.py`, `routers/export.py`, `routers/reports*.py`, `services/advanced.py`, `services/csv_*.py`, `services/unavailable_store.py`, `reports/`, `scripts/`, `docs/contract.md` G–J, `docs/examples/`, `docs/handoff/`, `.env.example`, `.gitignore`, `docs/api-change-log.md`, `docs/deploy.md` | `main.py` (register your routers next to mine), `config.py`, `errors.py`, `schemas.py` envelope, `services/store.py` (protocol), `services/validation.py` |

## 3. The store interface (exact signatures)

```python
class DataStore(Protocol):
    info: DatasetInfo                      # DatasetInfo(data_status, data_version, contract_version)
    def asset_statuses(self) -> dict[str, str | None]: ...   # {asset name: data_status read FROM the file}
    def variables(self) -> list[VariableInfo]: ...
    def regions(self) -> RegionsResult: ...
    def sources(self) -> list[SourceInfo]: ...
    def series(self, region_id: str, variable: str, frequency: str) -> TimeSeries: ...
    def trend(self, region_id: str, variable: str, period: Period, season: str) -> TrendResult: ...
    def anomalies(self, region_id: str, variable: str, period: Period,
                  detrended: bool) -> AnomalyResult | AnomalyBothResult: ...
    def interaction(self, region_id: str, season: str) -> InteractionResult: ...
    def indicator(self, region_id: str, indicator: str, season: str) -> IndicatorResult: ...
```

Rules for every method: return validated contract objects; raise `api_error("DATA_NOT_AVAILABLE", ...,
{"dataset": <logical name>, ...ids})` when the file/result does not exist; never fall back to mock; never
convert units, fill gaps or smooth. Logical dataset names already in use: `variables`, `regions`, `sources`,
`timeseries_monthly`, `timeseries_daily`, `trend`, `anomalies`, `interaction_summary`, `rainfall_indicators`.

**Selection:** `DATA_MODE=mock` → `MockStore(data/mock/<scenario>)`. `DATA_MODE=real` →
`app.services.real_store.create_store(settings)`. Until that module exists, `APP_ENV=dev` starts with
`UnavailableRealStore` (a marked stub: every data route says `DATA_NOT_AVAILABLE`, never mock data) and
`APP_ENV=prod` refuses to start.

**Startup guard (`verify_store`, please keep it):** the `DATA_VERSION` pin must match; `store.info.data_status` must
equal `DATA_MODE`; the contract version must match; in prod every `asset_statuses()` value must be `"real"`
and the dict must not be empty.

**Rules for your store (in the `DataStore` docstring, checked by `backend/tests/test_store_conformance.py`):**
load once (startup or first use, then from memory: `regions()`/`variables()`/`sources()` run on almost every
request); thread-safe and read-only (up to 40 requests at once); raise only `ApiError` (`DATA_NOT_AVAILABLE`
for anything unknown or missing; a `KeyError` would reach the user as an unexplained 500). The conformance test
runs on your store automatically as soon as `services/real_store.py` exists.

### What my endpoints need from your real store

| Method | Used by | Must return |
|---|---|---|
| `regions()`, `variables()`, `sources()` | everything | G3's regions/variables/sources as A–C models |
| `series(r, v, "month")` | CSV series/trend, PDF charts | monthly `TimeSeries`, `YYYY-MM-01`, units `mm/month` / `"1"` |
| `series(r, v, "day")` | daily CSV | daily `TimeSeries`, `mm/day` / `"1"` |
| `trend(r, v, period, season)` | CSV trend, PDF | the same `TrendResult` `/analyze` returns for that request (call trendlib or read a stored result) |
| `anomalies(r, v, period, detrended)` | `/anomalies`, CSV, PDF | the full result **sliced to `period`** (reuse `window_anomalies(full, period)` from `store.py`: slicing only); `v` may be `both` |
| `interaction(r, season)` | `/interaction`, PDF | Aadarsh's validated result for that season (H9) |
| `indicator(r, indicator, season)` | `/rainfall/indicators`, PDF | Sritharan's yearly values + the agreed `TrendResult` (`season: "annual"` extension, J-2) |

The DOCX names G3's deliverables as tables (`timeseries_monthly.csv`, `timeseries_daily.csv`,
`rainfall_indicators_annual.csv`, `interaction_summary.json`); the mock store uses one JSON envelope per result.
Your loader decides the real layout; my code only sees the methods above. Drop-in proposal for G3:
[real_data_dropin.md](real_data_dropin.md).

## 4. Shared validation helpers (please agree before writing /timeseries and /analyze)

`services/validation.py`: `require_choice(value, allowed, code, param)`; `resolve_period(start, end, available) ->
Period` (defaults to `period_available`; reasons `bad_format` / `start_after_end` / `outside_available`);
`months_in`, `period_years`, `first_day`, `last_day`; `require_daily_limit(period)` (10 years,
`daily_limit_exceeded`); `require_min_years(period, 10)` → `PERIOD_TOO_SHORT`; `slice_series(series, period)`;
`coverage(series, period) -> Coverage`; `require_coverage(series, period, 70.0)` → `INSUFFICIENT_DATA` (C-2: null
and `suspect` count as invalid). `services/advanced.py`: `find_region(store, region_id)`.
Reusing these in `/timeseries`, `/analyze` and `/compare` gives the same error for the same input everywhere.
Yours to add: the `alpha` choice (`VALIDATION_ERROR`) and the trendlib exception mapping (D-04).

## 5. How your results and `/explain` enter my PDF

- **Trend results:** the report calls `store.trend(region, variable, period, season)` and prints it only if its
  own `period`/`season` equal the request (otherwise a "Not available" box). If `/analyze` computes trends live,
  make `store.trend` call the same function so that the PDF equals `/analyze` for the same request.
- **Explanation:** create `backend/app/ai/report_summary.py` with
  `summarize(results: Sequence[BaseModel]) -> tuple[str, Literal["llm", "template"]]`.
  `results` are exactly the objects printed (trend, anomaly, interaction, indicator results). The PDF labels
  `llm` as **"AI-generated explanation of computed results"** and `template` as **"Automatic summary"**.
  If the module is missing, raises, or returns another label, the PDF still builds and says that no summary is
  available. Hook: `backend/app/reports/hooks.py::ai_summary_for`.
- **Methods/limitations:** Group 3's `docs/methods.md` (H9) is read by `load_report_texts()`; its
  `## Limitations` bullets replace the team's generic limitations.
- **Real-mode check:** a real-data PDF that would print `MOCK`, `placeholder`, `TODO`, `YYYY`, etc. fails with
  `REPORT_FAILED` (the markers are logged). An AI summary containing those words is dropped and logged instead,
  and the PDF is still made; a `report_summary.py` that fails to import is logged the same way.

## 6. Integration checklist (both of us)

1. You replace A–F in `schemas.py` → `python -m pytest` (my tests type-check against A–F).
2. You add `services/real_store.py` → `python -m pytest backend/tests/test_store_conformance.py
   backend/tests/test_real_data_acceptance.py` (the acceptance tests stop skipping once `data/processed/` has
   files, and then require `variables.json`, `sources.json`, `regions.geojson` and one reference file per
   endpoint and region; change `REQUIRED_PROCESSED_FILES` there if DS-2 picks another layout).
3. You register your routers in `main.py` next to mine; keep `debug=False`, the lifespan order and the
   middleware order (security headers → CORS → body limit → unhandled-error handler). `app.main.app` is built
   on first access, not at import, so `from app.main import create_app` never reads `.env`.
   My G–J models are frozen (`FrozenContractModel`); consider `frozen=True` for A–F too, since the store's
   cached objects are shared by all requests (derive new ones with `model_copy(update=...)`).
   Please turn on branch protection for `main` (require the `backend tests` check; repo admin only).
   Add `responses=error_responses("INVALID_REGION", ...)` (`app/openapi_errors.py`) so `/docs` lists your
   codes; without it your routes still show the contract 422/500 shape. For the `/explain` rate limit, reuse
   `services/rate_limit.RequestLimiter` (it already returns `RATE_LIMITED` 429 with `Retry-After`).
4. `python scripts/smoke_test.py http://localhost:8000 --expect-status real --allow-unavailable` until H9.
