# TrendTrace data contract — sections G, H, I, J (v1.0 candidate)

Status: **v1.0 candidate for the H3 freeze (IM3, Fri 20:15 IST).** Presented as v0.1 at IM2 (Fri 15:30): no changes requested.
Nothing here is approved until IM3 freezes it; the open decisions below still need their sign-off there (or at H7/H9 for science items).
Labels: [RULE] existing team rule · [PROVISIONAL] draft choice · [RECOMMENDATION] G1 M2 proposal ·
[OPEN QUESTION] decision needed. Decision IDs and their sign-off status: [handoff/contract_decisions.md](handoff/contract_decisions.md)
(nothing there is approved until the named owner signs it off).

Owner of G–J: Karnish (G1 Member 2). Sections A–F are owned by Adrian (G1 Member 1) and are **not changed here**;
they are documented below from Group 1 DOCX section 6 and the existing models. Where G–J needs something from A–F, it is listed as a
proposed extension for Adrian. Group 3 signs off science: Sritharan (anomaly/indicator definitions, units,
thresholds) and Aadarsh (interaction and statistics). Group 2 signs off that the fields cover the screens:
Kavin (Anomaly Radar, report) and Sri Prasath (Interaction screen, downloads).

Every example below exists as a file in [docs/examples/](examples/) and is checked by
`backend/tests/test_contract_examples.py` against the Pydantic models in `backend/app/advanced_schemas.py`.
All example numbers are **illustrative MOCK values**, not results.

## A. Conventions

Success: `{data_status,data_version,contract_version,generated_at,result}`. Errors retain section I's bare shape. Monthly dates are YYYY-MM-01; daily dates YYYY-MM-DD; period parameters YYYY-MM. Missing values are JSON null / empty CSV cells, qc_flag="missing". A real zero stays zero. No backend conversion, interpolation, smoothing or scientific calculation. ISO timestamps include timezone. Numbers remain full precision until UI/report formatting. Bounding boxes use [min_lon,min_lat,max_lon,max_lat]. Seasons: all, JF, MAM, JJAS, OND. Every mock result is labelled mock. Production refuses mock assets. Data and contract versions come from loaded provenance.

### Envelope
| Field | Type / format | Required |
|---|---|---|
| `data_status` | `Literal['real', 'mock']` | yes |
| `data_version` | `<class 'str'>` | yes |
| `contract_version` | `<class 'str'>` | yes |
| `generated_at` | `<class 'pydantic.types.AwareDatetime'>` | yes |
| `result` | `~T` | yes |

## B. Variables and sources

Core IDs: rainfall and aod; optional aod_terra and aod_merra2. Canonical units: monthly rainfall mm/month, daily rainfall mm/day, AOD "1" (UI: unitless); slopes add "per decade". VariableInfo.unit describes monthly data; frequency-specific rainfall units are preserved on TimeSeries. SourceInfo's nullable provenance fields retain existing M-2; Group 3 supplies genuine provenance.

### VariableInfo
| Field | Type / format | Required |
|---|---|---|
| `variable` | `<class 'str'>` | yes |
| `label` | `<class 'str'>` | yes |
| `unit` | `<class 'str'>` | yes |
| `unit_label` | `<class 'str'>` | yes |
| `sources` | `list[str]` | yes |
| `description` | `<class 'str'>` | yes |
| `caveat` | `str \| None` | yes |
### SourceInfo
| Field | Type / format | Required |
|---|---|---|
| `source_id` | `<class 'str'>` | yes |
| `product` | `<class 'str'>` | yes |
| `short_name` | `<class 'str'>` | yes |
| `version` | `<class 'str'>` | yes |
| `doi` | `str \| None` | yes |
| `access_method` | `<class 'str'>` | yes |
| `access_date` | `datetime.date \| None` | yes |
| `variable_name` | `<class 'str'>` | yes |
| `citation` | `str \| None` | yes |

## C. Regions

Region boxes are analysis boxes, not administrative boundaries. RegionsResult retains `{regions,geojson}` with a FeatureCollection and feature IDs equal to region_id. `period_available` is inclusive. Geographic boundaries and lists come from Group 3.

### Region
| Field | Type / format | Required |
|---|---|---|
| `region_id` | `<class 'str'>` | yes |
| `name` | `<class 'str'>` | yes |
| `bbox` | `tuple[float, float, float, float]` | yes |
| `status` | `<class 'str'>` | yes |
| `description` | `<class 'str'>` | yes |
| `variables` | `list[str]` | yes |
| `period_available` | `<class 'app.schemas.Period'>` | yes |

## D. Time series

TimeSeries has one region, variable, frequency, unit and source_id, with points in ascending date order without duplicates. Each point has date, value, valid_fraction and qc_flag. qc_flag: ok | low_coverage | missing | suspect. valid_fraction: [0,1] or null. Value is null exactly when qc_flag="missing". No scientific values are repaired.

### TimeSeries
| Field | Type / format | Required |
|---|---|---|
| `region_id` | `<class 'str'>` | yes |
| `variable` | `<class 'str'>` | yes |
| `frequency` | `Literal['month', 'day']` | yes |
| `unit` | `<class 'str'>` | yes |
| `source_id` | `<class 'str'>` | yes |
| `points` | `list[app.schemas.SeriesPoint]` | yes |
### SeriesPoint
| Field | Type / format | Required |
|---|---|---|
| `date` | `<class 'datetime.date'>` | yes |
| `value` | `float \| None` | yes |
| `valid_fraction` | `Annotated[float, FieldInfo(annotation=NoneType, required=True, metadata=[Ge(ge=0.0), Le(le=1.0)])] \| None` | yes |
| `qc_flag` | `Literal['ok', 'low_coverage', 'missing', 'suspect']` | yes |

## E. Trend result

All fields below are required. TrendResult is returned by Group 3 and validated before serving. Direction: if p_value < method.alpha, follow the sen_slope sign; otherwise no_significant_trend. slope_sign: positive | negative | zero. significant must equal p_value < alpha. The existing `season: annual` indicator extension (J-2) is preserved as [PROVISIONAL]; it is not added to the core season choices. Method identifiers and series_type remain Group 3's strings. All statistics, including OLS, counts and confidence limits, are supplied by trendlib.

### TrendResult
| Field | Type / format | Required |
|---|---|---|
| `result_id` | `<class 'str'>` | yes |
| `region_id` | `<class 'str'>` | yes |
| `variable` | `<class 'str'>` | yes |
| `source_id` | `<class 'str'>` | yes |
| `period` | `<class 'app.schemas.Period'>` | yes |
| `season` | `Literal['all', 'JF', 'MAM', 'JJAS', 'OND'] \| Literal['annual']` | yes |
| `series_type` | `<class 'str'>` | yes |
| `method` | `<class 'app.schemas.TrendMethod'>` | yes |
| `direction` | `Literal['increasing', 'decreasing', 'no_significant_trend']` | yes |
| `slope_sign` | `Literal['positive', 'negative', 'zero']` | yes |
| `sen_slope` | `<class 'float'>` | yes |
| `slope_unit` | `<class 'str'>` | yes |
| `slope_ci` | `tuple[float, float]` | yes |
| `p_value` | `<class 'float'>` | yes |
| `significant` | `<class 'bool'>` | yes |
| `ols_slope` | `<class 'float'>` | yes |
| `ols_ci` | `tuple[float, float]` | yes |
| `change_over_period` | `<class 'float'>` | yes |
| `baseline_mean` | `<class 'float'>` | yes |
| `percent_change_per_decade` | `<class 'float'>` | yes |
| `n_expected` | `<class 'int'>` | yes |
| `n_valid` | `<class 'int'>` | yes |
| `missing_pct` | `<class 'float'>` | yes |
| `record_years` | `<class 'float'>` | yes |
| `lag1_autocorrelation` | `<class 'float'>` | yes |
| `limitations` | `list[str]` | yes |
| `evidence` | `<class 'app.schemas.Evidence'>` | yes |
| `trendlib_version` | `<class 'str'>` | yes |
| `computed_at` | `<class 'pydantic.types.AwareDatetime'>` | yes |
### TrendMethod
| Field | Type / format | Required |
|---|---|---|
| `test` | `<class 'str'>` | yes |
| `slope` | `<class 'str'>` | yes |
| `alpha` | `<class 'float'>` | yes |
| `ci_level` | `<class 'float'>` | yes |

## F. Evidence

evidence_label: strong | moderate | weak | insufficient_data. These are the existing team labels, not an official NASA score. Display "Label rule defined by the team; see Methods" with the supporting numbers. Group 3 implements the label rules: insufficient_data for <10 years or <70% valid observations; strong/moderate depend on significance, CI and sensitivity agreement; weak otherwise (see DOCX §6F). Backend validates fields, never computes the label. The spec's pre-H7 not_assessed fallback is outside the frozen enum: see SCI-03; no new enum is silently added.

### Evidence
| Field | Type / format | Required |
|---|---|---|
| `record_years` | `<class 'float'>` | yes |
| `n_valid` | `<class 'int'>` | yes |
| `n_expected` | `<class 'int'>` | yes |
| `valid_obs_pct` | `<class 'float'>` | yes |
| `mean_valid_fraction` | `Annotated[float, FieldInfo(annotation=NoneType, required=True, metadata=[Ge(ge=0.0), Le(le=1.0)])] \| None` | yes |
| `low_coverage_months` | `<class 'int'>` | yes |
| `p_value` | `<class 'float'>` | yes |
| `slope_ci` | `tuple[float, float]` | yes |
| `ci_excludes_zero` | `<class 'bool'>` | yes |
| `sensitivity` | `list[app.schemas.SensitivityRun]` | yes |
| `evidence_label` | `Literal['strong', 'moderate', 'weak', 'insufficient_data']` | yes |
| `label_rule_version` | `<class 'str'>` | yes |
| `notes` | `list[str]` | yes |
### SensitivityRun
| Field | Type / format | Required |
|---|---|---|
| `name` | `<class 'str'>` | yes |
| `sen_slope` | `float \| None` | yes |
| `p_value` | `Annotated[float, FieldInfo(annotation=NoneType, required=True, metadata=[Ge(ge=0.0), Le(le=1.0)])] \| None` | yes |
| `same_sign` | `bool \| None` | yes |

---

## Conventions used by G–J (from A, unchanged)

- Success responses use the envelope `{data_status, data_version, contract_version, generated_at, result}`.
- Errors use the bare section I shape (see I). [RECOMMENDATION] D-01.
- Monthly dates `YYYY-MM-01`; daily `YYYY-MM-DD`; period parameters `YYYY-MM`.
- Missing = JSON `null`, CSV empty cell; never 0, never -9999, never interpolated. A measured zero stays 0.
- `valid_fraction` is a fraction 0–1; fields ending in `_pct` are percentages 0–100.
- Units: rainfall monthly `mm/month`, daily `mm/day`; AOD `"1"` (UI "unitless"); slopes per decade.
- **"Always present"**: every key listed in a table below is always present in the JSON. "Nullable" says when its value may be `null`. No key is ever omitted.

---

## G. Anomaly result — `GET /api/v1/anomalies`

Purpose: which months were unusual compared with the same calendar month in a stated baseline (Anomaly Radar).

**Request** `region_id` (required), `variable = rainfall | aod | both` (required), `start`, `end` (`YYYY-MM`; [PROVISIONAL] G-9: optional, default = the region's `period_available`, same rule as `/export/csv`), `detrended` (bool, default `false`; anything other than true/false → `VALIDATION_ERROR`).

Example: `GET /api/v1/anomalies?region_id=IGP&variable=both&start=2024-01&end=2024-12&detrended=false`

- [RECOMMENDATION] G-2: the 10-year minimum applies to the **baseline** (fixed 2003-01..2024-12, at least 10 valid same-month values), not to the requested window. The window (`start`..`end`) only selects which months are listed and may be shorter than 10 years.
- Errors: `INVALID_REGION`, `INVALID_VARIABLE` (`allowed` = the region's variables plus `both`), `INVALID_PERIOD` (400); `INSUFFICIENT_DATA` (422) if a calendar month has fewer than 10 valid baseline values (raised by the store/trendlib, which hold the baseline counts; the router counts nothing); `DATA_NOT_AVAILABLE` (404, `details: {"dataset": "anomalies", "region_id", "variable", "detrended"}`) before H7 data exists.

**Shape** [PROVISIONAL] G-1: `variable=rainfall|aod` returns one `AnomalyResult`. `variable=both` returns `AnomalyBothResult`, which wraps the two single results (rainfall first, then AOD) plus `combined_flags`.

### G.1 AnomalyResult (single variable)

| Field | Type | Nullable | Unit / format | Meaning | Signs off |
|---|---|---|---|---|---|
| `result_id` | string | no | `anomalies_<region>_<variable>_<start>_<end>_<raw\|detrended>` | Stable ID for `/explain` and reports. **Added** (G-8). | G1 |
| `region_id` | string | no | contract C | Region. | G1 |
| `variable` | `rainfall` \| `aod` | no | | Variable. | G1 |
| `source_id` | string | no | contract B | Monthly source used. | G3 |
| `unit` | string | no | `mm/month` or `1` | Unit of `value` and `baseline_median`. **Added** (G-8). | G3 |
| `period` | `{start,end}` | no | `YYYY-MM` | The requested window that is listed. **Added** (G-8). | G1 |
| `baseline.start`, `baseline.end` | string | no | `YYYY-MM` | Baseline period, always shown. [PROVISIONAL] 2003-01..2024-12. | G3 |
| `baseline.method` | `same_calendar_month` | no | | Each month compared with the same calendar month in the baseline. | G3 |
| `baseline.statistic` | `empirical_percentile` \| `z_log` | no | | Rainfall: empirical percentile; AOD: z-score of log(AOD) (G3 §9). [OPEN QUESTION] G-4. | G3 |
| `baseline.detrended` | bool | no | | Sen trend removed before computing anomalies (G3 §9). | G3 |
| `thresholds.high` / `thresholds.low` | number | no | percentile fraction or z | Rainfall `0.90`/`0.10`; AOD `+2.0`/`-2.0`. Inclusive: flagged if `score >= high` or `score <= low` (G-6). | G3 |
| `thresholds.min_valid_fraction` | number | rainfall `0.9`; AOD `null` | 0–1 | Rainfall months below this are not assessed (score `null`). AOD low-coverage months are assessed with a note (G3 §9). **Added** (G-4). | G3 |
| `thresholds.dry_suppression_median` | number | AOD `null` | mm/month | [PROVISIONAL] `10.0`: no dry flag when the same-month baseline median is below this. **Added** (G-5). | G3 |
| `anomalies[]` | list | no (may be `[]`) | | [RECOMMENDATION] G-3: **every month of the window**, flagged or not, in date order (the Radar heatmap needs all months). | G2 |
| `anomalies[].date` | string | no | `YYYY-MM-01` | Month. | G1 |
| `anomalies[].value` | number | yes, when missing | `unit` | Stored monthly value, unchanged. | G3 |
| `anomalies[].baseline_median` | number | yes, if not computable | `unit` | Same-calendar-month baseline median. | G3 |
| `anomalies[].score` | number | yes: missing month, or not assessed | percentile fraction 0–1 or z | Anomaly score. | G3 |
| `anomalies[].score_type` | `percentile` \| `z_log` | no | | Always matches `baseline.statistic`. | G3 |
| `anomalies[].category` | enum | yes = not flagged | | `unusually_wet`/`unusually_dry` (rainfall), `unusually_high_aod`/`unusually_low_aod` (AOD). | G3 |
| `anomalies[].valid_fraction` | number | yes, if unknown | 0–1 | From the series (contract D). | G3 |
| `anomalies[].qc_flag` | enum | no | contract D enum | Copied from the series. **Added** (G-8). | G3 |
| `anomalies[].note` | string | no (`""` = none) | | Why a month is not assessed / not flaggable, e.g. low coverage, dry flag not applicable. | G3 |

Rules:

1. [RULE] `value` is `null` exactly when `qc_flag = "missing"`; then `score` and `category` are `null`.
2. A flagged month always has a `score`; `category` must agree with the inclusive thresholds (G-6).
3. Dry flags are not possible when `baseline_median < dry_suppression_median`; the note says so (G-5).
4. An empty flagged set is a valid result ("No months met the threshold"); it is not an error.
5. The backend copies these values from trendlib output (H7); it computes nothing.

Example (single variable, TN rainfall 2024, includes a real 0.0, a suppressed dry flag and a missing month): [examples/anomaly_rainfall.json](examples/anomaly_rainfall.json). AOD: [examples/anomaly_aod.json](examples/anomaly_aod.json). Low coverage / no flags: [examples/anomaly_low_coverage.json](examples/anomaly_low_coverage.json).

```json
{
  "data_status": "mock", "data_version": "MOCK-2026-11-13", "contract_version": "1.0",
  "generated_at": "2026-11-13T12:00:00+05:30",
  "result": {
    "result_id": "anomalies_TN_aod_2023-06_2023-09_raw", "region_id": "TN", "variable": "aod",
    "source_id": "MODIS_AQUA_C61_MONTHLY", "unit": "1",
    "period": {"start": "2023-06", "end": "2023-09"},
    "baseline": {"start": "2003-01", "end": "2024-12", "method": "same_calendar_month", "statistic": "z_log", "detrended": false},
    "thresholds": {"high": 2.0, "low": -2.0, "min_valid_fraction": null, "dry_suppression_median": null},
    "anomalies": [
      {"date": "2023-06-01", "value": 0.452, "baseline_median": 0.418, "score": 0.41, "score_type": "z_log", "category": null, "valid_fraction": 0.25, "qc_flag": "low_coverage", "note": "low coverage: 25% of days had a valid retrieval"},
      {"date": "2023-07-01", "value": null, "baseline_median": 0.437, "score": null, "score_type": "z_log", "category": null, "valid_fraction": 0.03, "qc_flag": "missing", "note": "missing month: too few valid days"},
      {"date": "2023-08-01", "value": null, "baseline_median": 0.429, "score": null, "score_type": "z_log", "category": null, "valid_fraction": 0.0, "qc_flag": "missing", "note": "missing month: no valid days"},
      {"date": "2023-09-01", "value": 0.371, "baseline_median": 0.402, "score": -0.7, "score_type": "z_log", "category": null, "valid_fraction": 0.47, "qc_flag": "ok", "note": ""}
    ]
  }
}
```

### G.2 AnomalyBothResult (`variable=both`)

| Field | Type | Nullable | Meaning |
|---|---|---|---|
| `result_id` | string | no | `anomalies_<region>_both_<start>_<end>_<raw\|detrended>` |
| `region_id`, `period`, `detrended` | as G.1 | no | Shared by both nested results. |
| `variable` | `both` | no | |
| `results` | `[AnomalyResult(rainfall), AnomalyResult(aod)]` | no | Exactly two, in this order; each keeps its own `source_id`, `unit`, baseline and thresholds. |
| `combined_flags[]` | list | no (may be `[]`) | One entry per month flagged in **both** variables. |
| `combined_flags[].date` | `YYYY-MM-01` | no | |
| `combined_flags[].category` | `dry_and_high_aod` \| `wet_and_high_aod` \| `unusual_combination` | no | [OPEN QUESTION] G-7: provisional reading — any other both-flagged pair (wet+low AOD, dry+low AOD) is `unusual_combination`. |
| `combined_flags[].rainfall_category`, `.aod_category` | enum | no | The two flags combined. **Added** so the reference is unambiguous. |

Example: [examples/anomaly_both.json](examples/anomaly_both.json) (IGP 2024: October is dry + high AOD → `dry_and_high_aod`).

---

## H. Interaction result — `GET /api/v1/interaction`

Purpose: how AOD before and after heavy-rain days compares, plus the monthly rainfall–AOD association. [RULE] Association only; never causation.

**Request** `region_id`, `season = all | JF | MAM | JJAS | OND` (both required; [PROVISIONAL] H-7: no default season). Example: `GET /api/v1/interaction?region_id=IGP&season=JJAS`. A season with no G3 result (today: `MAM`, `JF`) is `DATA_NOT_AVAILABLE`, never a guess. Errors: `INVALID_REGION`, `INVALID_SEASON` (400); `DATA_NOT_AVAILABLE` (404, `details: {"dataset": "interaction_summary", "region_id", "season"}`) until G3's daily series / H9 summary exist. G2 shows "Interaction analysis is being validated" for that 404 (H-6).

Definitions below are copied from **Group 3 DOCX §8.1** (source-resolved) and still need Aadarsh's sign-off.
When `status = too_few_events`, the descriptive counts, sampling percentages, medians, `control` and the separate
`monthly_association` are kept; only the inferential fields (`median_change_ci`, `p_value`) are `null`.

| Field | Type | Nullable | Unit / format | Meaning |
|---|---|---|---|---|
| `result_id` | string | no | `interaction_<region>_<season>_<start>_<end>` | **Added** (H-4). |
| `region_id`, `season` | string | no | | Request echo. |
| `period` | `{start,end}` | no | `YYYY-MM` | Analysis period. **Added** (H-4). |
| `source_ids.rainfall_daily`, `.aod_daily`, `.rainfall_monthly`, `.aod_monthly` | string | no | contract B | Provenance. **Added** (H-4). |
| `event_definition.rain_threshold` | `seasonal_p90_of_daily_regional_mean` | no | | Event day: daily regional-mean rain ≥ seasonal P90. |
| `event_definition.threshold_period` | `{start,end}` | no | `YYYY-MM` | Period used for the P90 (2003-01..2024-12). **Added**. |
| `event_definition.min_separation_days` | int | no | days | 7; keep the first event. |
| `event_definition.window_days` | int | no | days | 3: before = D−3..D−1, after = D+1..D+3. |
| `event_definition.event_day_excluded` | bool | no | | `true` (AOD mostly missing on rain days). **Added**. |
| `event_definition.min_valid_aod_days_per_window` | int | no | days | 1: an event is used only with ≥1 valid AOD day in both windows. **Added**. |
| `status` | `ok` \| `too_few_events` | no | | **Added** (H-1). `ok` iff `n_events_used >= 10`. |
| `note` | string | `null` when `ok` | | Exactly `"too few events for a reliable comparison"` when `too_few_events`. |
| `n_events` | int | no | count | Events found. |
| `n_events_used` | int | no | count | Events with valid AOD in both windows. `<= n_events`. |
| `valid_aod_pct_before`, `valid_aod_pct_after` | number | `null` when `n_events = 0` | % (0–100) | Valid AOD days ÷ possible days (`n_events × window_days`). |
| `aod_before_median`, `aod_after_median` | number | `null` when `n_events_used = 0` | `1` | Median of per-event window means. Descriptive. |
| `median_change` | number | `null` when `n_events_used = 0` | `1` | Median of per-event (after − before). Descriptive (H-2). |
| `median_change_ci` | `[low, high]` | `null` when `too_few_events` | `1` | Bootstrap CI of the median change. |
| `ci_level` | number | no | | 0.95. **Added**. |
| `ci_method` | `bootstrap` | no | | **Added**. |
| `test` | `wilcoxon_signed_rank` | no | | Test applied when `ok`. |
| `p_value` | number | `null` when `too_few_events` | 0–1 | |
| `control.method` | `random_non_event_days_same_month` | no | | Same steps on random non-event days (not within ±3 days of an event). |
| `control.n` | int | no | count | Number of control windows ([OPEN QUESTION] H-3: `n_events × 5` or `n_events_used × 5`). |
| `control.median_change` | number | `null` when `control.n = 0` | `1` | |
| `monthly_association.method` | `spearman_on_deseasonalised_anomalies` | no | | Independent of the event count (H-2). |
| `monthly_association.rho` | number | `null` if not computable | −1..1 | |
| `monthly_association.n` | int | no | months | |
| `monthly_association.p_value` | number | `null` if not computable | 0–1 | |
| `guardrail` | string | no | | Always exactly: `"Association only. AOD is retrieved in clear skies, so rainy days are under-sampled."` |

Boundary cases: 0 events → `status: too_few_events`, counts 0, percentages/medians/`median_change` `null`, CI and p `null`. 9 used events → `too_few_events` with descriptive medians. 10 used events → `ok` with test result. HTTP status is 200 in all three cases (H-1); this is a valid answer, not an error.

Examples: [examples/interaction_ok.json](examples/interaction_ok.json), [examples/interaction_too_few_events.json](examples/interaction_too_few_events.json).

```json
{
  "data_status": "mock", "data_version": "MOCK-2026-11-13", "contract_version": "1.0",
  "generated_at": "2026-11-13T12:00:00+05:30",
  "result": {
    "result_id": "interaction_IGP_OND_2003-01_2024-12", "region_id": "IGP", "season": "OND",
    "period": {"start": "2003-01", "end": "2024-12"},
    "source_ids": {"rainfall_daily": "IMERG_V07_FINAL_DAILY", "aod_daily": "MODIS_AQUA_C61_DAILY", "rainfall_monthly": "IMERG_V07_FINAL_MONTHLY", "aod_monthly": "MODIS_AQUA_C61_MONTHLY"},
    "event_definition": {"rain_threshold": "seasonal_p90_of_daily_regional_mean", "threshold_period": {"start": "2003-01", "end": "2024-12"}, "min_separation_days": 7, "window_days": 3, "event_day_excluded": true, "min_valid_aod_days_per_window": 1},
    "status": "too_few_events", "note": "too few events for a reliable comparison",
    "n_events": 14, "n_events_used": 6,
    "valid_aod_pct_before": 66.7, "valid_aod_pct_after": 61.9,
    "aod_before_median": 0.981, "aod_after_median": 0.874, "median_change": -0.072,
    "median_change_ci": null, "ci_level": 0.95, "ci_method": "bootstrap",
    "test": "wilcoxon_signed_rank", "p_value": null,
    "control": {"method": "random_non_event_days_same_month", "n": 30, "median_change": 0.011},
    "monthly_association": {"method": "spearman_on_deseasonalised_anomalies", "rho": 0.12, "n": 66, "p_value": 0.34},
    "guardrail": "Association only. AOD is retrieved in clear skies, so rainy days are under-sampled."
  }
}
```

[OPEN QUESTION] H-5: the Interaction screen (G2 §4.3) wants an event-composite chart (median + IQR by lag day, events vs control). H has no per-lag-day data. Either G3 adds a `composite` array by H9, or the screen shows the before/after summary only.

### Serving rule for G, H, J (all three endpoints)

The backend serves the store's object unchanged inside the envelope. Before serving, it checks that the object
answers **this** request (region, variable or indicator, season, period, detrended). A mismatch is a store bug:
it is logged and returned as `INTERNAL_ERROR`, never served under the wrong request. The PDF report and the CSV
export use the same selection code, so they print exactly what the API returns for the same request.

---

## I. Error format (all endpoints)

[RULE] One wire format for every error, every endpoint, every HTTP status:

```json
{ "error": { "code": "PERIOD_TOO_SHORT", "message": "Choose at least 10 years.", "details": {"min_years": 10, "requested_years": 6.0} } }
```

- `code`: one string from the table (each `INVALID_*` is its own code; no slash-joined codes).
- `message`: short, user-readable, safe to show as-is.
- `details`: object (may be `{}`); only parameter names, allowed values, counts and logical dataset names. **Never** stack traces, exception text, file paths, provider responses, secrets, or the raw submitted value.
- Errors are always `application/json`, also on CSV/PDF download routes (never an error row in a CSV, never a broken PDF).
- [RECOMMENDATION] D-01: errors do **not** carry `data_status`/`data_version` (they describe the request, not data). The example files use exactly this bare shape.

### I.1 Contract codes (source: DOCX §6-I)

| Code | HTTP | When | `details` |
|---|---|---|---|
| `INVALID_REGION` | 400 | Unknown `region_id`. | `{"param": "region_id", "allowed": [...]}` |
| `INVALID_VARIABLE` | 400 | Unknown `variable`. | `{"param": "variable", "allowed": [...]}` |
| `INVALID_SEASON` | 400 | Unknown `season`. | `{"param": "season", "allowed": [...]}` |
| `INVALID_PERIOD` | 400 | Bad `YYYY-MM`, start after end, outside `period_available`, or daily request longer than 10 years. | `{"param", "reason": "bad_format"\|"start_after_end"\|"outside_available"\|"daily_limit_exceeded", "available": {start,end}, "max_years"?}` |
| `PERIOD_TOO_SHORT` | 422 | Fewer than 10 years requested where a result needs 10 (trend; report). | `{"min_years": 10, "requested_years": n}` |
| `INSUFFICIENT_DATA` | 422 | Fewer than 70% valid values in the chosen period/season (trend rule; also CSV series export, C-2). | `{"min_valid_pct": 70.0, "valid_pct", "n_valid", "n_expected"}` |
| `DATA_NOT_AVAILABLE` | 404 | Combination is in the contract but its file/result is not produced yet. | `{"dataset": <logical name>, ...ids}` |
| `AI_UNAVAILABLE` | 503 | Only when even the template explanation fails (D-03). An LLM failure with a working template is a **200** with `source: "template"`. | `{}` |
| `REPORT_FAILED` | 500 | PDF creation/rendering/writing failed. | `{}` |
| `INTERNAL_ERROR` | 500 | Anything unexpected; logged server-side. | `{}` |

### I.2 Proposed additional codes [PROVISIONAL] D-02

| Code | HTTP | When | `details` |
|---|---|---|---|
| `VALIDATION_ERROR` | 422 | Missing/malformed parameter or body field without a domain code (a value with a domain code always gets that code, whatever its length) (e.g. `alpha` not in {0.01, 0.05, 0.10}, `frequency` not `month`/`day`, bad JSON). | `{"fields": [{"loc", "msg", "type"}]}` (no input echo) |
| `NOT_FOUND` | 404 | Unknown URL (including `GET /api/v1/report/` with no ID). | `{}` |
| `METHOD_NOT_ALLOWED` | 405 | Wrong HTTP method. | `{}` |
| `PAYLOAD_TOO_LARGE` | 413 | Body over `MAX_BODY_BYTES`. | `{"max_bytes"}` |
| `INVALID_EXPORT_TYPE` | 400 | `/export/csv?what=` not `series`/`trend`/`anomalies`. | `{"param": "what", "allowed": [...]}` |
| `INVALID_INDICATOR` | 400 | `/rainfall/indicators?indicator=` unknown. | `{"param": "indicator", "allowed": [...]}` |
| `INVALID_REPORT_ID` | 400 | Malformed report ID (not `rpt_` + 32 hex). | `{"param": "report_id"}` |
| `REPORT_NOT_FOUND` | 404 | Well-formed ID with no saved report (e.g. after a host restart). | `{"report_id"}` |
| `HTTP_ERROR` | 4xx | Any other framework HTTP error (fallback). | `{}` |
| `RATE_LIMITED` | 429 | Too many requests from one client: `POST /report` (10 per minute, implemented); `/explain` (Member 1). Also sent as a `Retry-After` header. | `{"retry_after_s", "limit", "window_s"}` |
| `REPORT_BUSY` | 503 | `POST /report` while 2 PDFs are already being made. Also sent as a `Retry-After` header. | `{"retry_after_s"}` |

Mapping rules:

- Daily request over 10 years → `INVALID_PERIOD` with `reason: "daily_limit_exceeded"` (reuses an existing code instead of a new one).
- [RECOMMENDATION] D-04: only trendlib's **known data-domain exceptions** (to be named by G3, e.g. `InsufficientDataError`) map to `INSUFFICIENT_DATA`; any other exception is a bug → `INTERNAL_ERROR` (DOCX §13 suggested mapping all trendlib errors to `INSUFFICIENT_DATA`, which would hide bugs).

One example file per code: `docs/examples/error_<CODE>.json`.

---

## J. Rainfall indicator result — `GET /api/v1/rainfall/indicators`

[PROVISIONAL] J-1: placed as a new section J so that A–I keep their numbers.

**Request** `region_id`, `indicator = heavy_rain_share | longest_dry_spell | rx5day`, `season = annual | JJAS | OND` (all required; `annual` is **not** `all`). Example: `GET /api/v1/rainfall/indicators?region_id=IGP&indicator=heavy_rain_share&season=annual`. Errors: `INVALID_REGION` (400), `INVALID_INDICATOR` (400, D-02), `INVALID_SEASON` (400), `DATA_NOT_AVAILABLE` (404) until `rainfall_indicators_annual.csv` exists (H7/H9).

Definitions and units from **Group 3 DOCX §6** (indicator table), still to be signed off by G3:

| indicator | unit | definition |
|---|---|---|
| `heavy_rain_share` | `%` | Percentage of the year's (season's) wet-day rainfall falling on days above the 95th percentile of wet-day rainfall in the 2003–2024 baseline. Wet day ≥ 1 mm. |
| `longest_dry_spell` | `days` | Maximum number of consecutive days with rainfall < 1 mm within the year (season). |
| `rx5day` | `mm` | Maximum 5-day accumulated rainfall in the year (season). Optional. |

| Field | Type | Nullable | Unit / format | Meaning |
|---|---|---|---|---|
| `result_id` | string | no | `indicator_<region>_<indicator>_<season>_<start>_<end>` | |
| `region_id`, `indicator`, `season` | string | no | | Request echo. |
| `period` | `{start,end}` | no | `YYYY-MM` | Years covered (Jan of first year .. Dec of last year). |
| `source_id` | string | no | | `IMERG_V07_FINAL_DAILY`. |
| `unit` | string | no | | From the table above. |
| `definition` | string | no | | G3 text, served unchanged. |
| `spatial_method` | `regional_mean` \| `point_median` \| `grid_mean` | no | | G3 Plan A / A+ / B. [RULE] regional-mean indicators are labelled as such. |
| `threshold_baseline` | `{start,end}` | `null` except `heavy_rain_share` | `YYYY-MM` | Baseline for the 95th percentile. |
| `min_valid_fraction` | number | no | 0–1 | 0.95: years below this have `value: null` (G3 rule). |
| `values[]` | list | no | | One entry per year of `period`, in order. |
| `values[].year` | int | no | `YYYY` | |
| `values[].value` | number | yes: `valid_fraction < min_valid_fraction` | `unit` | |
| `values[].valid_fraction` | number | yes, if unknown | 0–1 | Valid days ÷ days in the year (season). [OPEN QUESTION] J-1 denominator for seasons. |
| `trend` | TrendResult (contract E) | yes, with `trend_note` | | Full E/F object (no simplified copy). |
| `trend_note` | string | `null` when `trend` present | | Why there is no trend (e.g. fewer than 10 valid years). J-3. |

Proposed extension of E/F for annual indicators (Member 1 + G3 approve, J-2):

- `season: "annual"` added to E's season enum (indicator trends only).
- `series_type: "annual_indicator"` (one value per year).
- `slope_unit`: `% per decade`, `days per decade`, `mm per decade`.
- Evidence counts (`n_valid`, `n_expected`, `valid_obs_pct`) count **years**; `low_coverage_months` is `0` (low-coverage years are already `null`).
- `variable: "rainfall"`; the indicator identity is in `result_id` and the parent object.

Example: [examples/rainfall_indicator_heavy_rain_share.json](examples/rainfall_indicator_heavy_rain_share.json) (21 of 22 valid years; slope positive but **not significant** → `direction: "no_significant_trend"`, evidence `weak`).
