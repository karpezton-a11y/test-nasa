# Frontend guide to Karnish's endpoints (Kavin, Sri Prasath)

Base path `/api/v1`. Staging (MOCK data): `https://trendtrace-api-staging.onrender.com` (open `/api/v1/health`
a minute before use; the free host sleeps). Local: `http://localhost:8000`.
Full success JSON for every endpoint: [docs/examples/](../examples/). Error JSON below is copied from a live
local server (mock mode).

## Rules for every screen

- **Success** = `{data_status, data_version, contract_version, generated_at, result}`. **Error** = `{"error":
  {code, message, details}}`. Branch on `error.code` only; `message` is display text and may change.
- **MOCK label:** whenever `data_status === "mock"`, show a visible "MOCK DATA: illustrative values" banner on
  every screen that shows numbers, and next to downloads. Never show it when `data_status` is `real`.
- **Missing values** are `null`: draw gaps, grey cells or "n/a"; **never 0**. A real `0` is a real zero.
- **Empty states:** `404 DATA_NOT_AVAILABLE` = "This analysis is being validated" (not an error page).
  An empty list (`anomalies: []`, `combined_flags: []`) = "No months met the threshold".
- **Loading:** the first request to a sleeping free host can take up to about 60 s; show a spinner, not an error.

## GET /anomalies (Anomaly Radar: Kavin)

| Param | Required | Values |
|---|---|---|
| `region_id` | yes | from `/regions` |
| `variable` | yes | `rainfall` \| `aod` \| `both` |
| `start`, `end` | no (default: full available period) | `YYYY-MM` |
| `detrended` | no (default `false`) | `true` \| `false` |

Request: `GET /api/v1/anomalies?region_id=IGP&variable=both&start=2024-01&end=2024-12`.
Success: single variable [anomaly_rainfall.json](../examples/anomaly_rainfall.json),
[anomaly_aod.json](../examples/anomaly_aod.json); `both` [anomaly_both.json](../examples/anomaly_both.json)
(`results[0]` is rainfall, `results[1]` is AOD, plus `combined_flags`).

- Heatmap: one cell per `anomalies[]` entry (every month of the window is listed). Colour by `category`;
  `category: null` = not flagged; `value: null` = grey "missing"; show `note` as the tooltip.
- Always show `baseline.start`–`baseline.end` and `baseline.statistic` near the heatmap.
- AOD is "unitless" (`unit: "1"`); rainfall is `mm/month`. AOD is a column measure, not ground-level PM2.5.

## GET /interaction (Interaction screen: Sri Prasath)

| Param | Required | Values |
|---|---|---|
| `region_id` | yes | from `/regions` |
| `season` | yes | `all` \| `JF` \| `MAM` \| `JJAS` \| `OND` |

Request: `GET /api/v1/interaction?region_id=IGP&season=JJAS`.
Success: [interaction_ok.json](../examples/interaction_ok.json),
[interaction_too_few_events.json](../examples/interaction_too_few_events.json).

- **Always show `guardrail`** under the result, unchanged: "Association only. AOD is retrieved in clear skies,
  so rainy days are under-sampled." Never write "caused", "leads to" or "because of".
- `status: "too_few_events"` → show `note` ("too few events for a reliable comparison") instead of a p-value;
  still show counts, sampling % (`valid_aod_pct_before/after`), medians (may be `null`) and the monthly
  association (its own `rho`, `n`, `p_value`).
- `status: "ok"` → show `median_change` with `median_change_ci` and `p_value`.
- Today `MAM` and `JF` return `DATA_NOT_AVAILABLE` (no Group 3 result yet).

## GET /rainfall/indicators (rainfall extremes card)

| Param | Required | Values |
|---|---|---|
| `region_id` | yes | from `/regions` |
| `indicator` | yes | `heavy_rain_share` (%) \| `longest_dry_spell` (days) \| `rx5day` (mm) |
| `season` | yes | `annual` \| `JJAS` \| `OND` (`annual` is not `all`) |

Request: `GET /api/v1/rainfall/indicators?region_id=IGP&indicator=heavy_rain_share&season=annual`.
Success: [rainfall_indicator_heavy_rain_share.json](../examples/rainfall_indicator_heavy_rain_share.json).

- One bar/point per `values[]` year; `value: null` = "year below 95% valid days", drawn as a gap.
- Show `definition` and `unit` as given. `trend` may be `null` → show `trend_note` instead.
- `direction: "no_significant_trend"` must never be worded as increasing or decreasing.

## Errors you will see (live responses)

| When | HTTP | Body |
|---|---|---|
| unknown region | 400 | `{"error":{"code":"INVALID_REGION","message":"Unknown region_id. Choose one of: IGP, TN.","details":{"param":"region_id","allowed":["IGP","TN"]}}}` |
| unknown variable (anomalies) | 400 | `{"error":{"code":"INVALID_VARIABLE","message":"Unknown variable. Choose one of: rainfall, aod, both.","details":{"param":"variable","allowed":["rainfall","aod","both"]}}}` |
| start after end, bad `YYYY-MM`, outside the data | 400 | `{"error":{"code":"INVALID_PERIOD","message":"The start month is after the end month.","details":{"param":"start","reason":"start_after_end","available":{"start":"2003-01","end":"2024-12"}}}}` (`reason`: `bad_format` \| `start_after_end` \| `outside_available`) |
| `detrended=maybe`, missing required parameter | 422 | `{"error":{"code":"VALIDATION_ERROR","message":"The request is missing a field or has a value in the wrong format.","details":{"fields":[{"loc":["query","detrended"],"msg":"Input should be a valid boolean, unable to interpret input","type":"bool_parsing"}]}}}` |
| unknown season (interaction) | 400 | `{"error":{"code":"INVALID_SEASON","message":"Unknown season. Choose one of: all, JF, MAM, JJAS, OND.","details":{"param":"season","allowed":["all","JF","MAM","JJAS","OND"]}}}` |
| unknown season (indicators) | 400 | `{"error":{"code":"INVALID_SEASON","message":"Unknown season. Choose one of: annual, JJAS, OND.","details":{"param":"season","allowed":["annual","JJAS","OND"]}}}` |
| unknown indicator | 400 | `{"error":{"code":"INVALID_INDICATOR","message":"Unknown indicator. Choose one of: heavy_rain_share, longest_dry_spell, rx5day.","details":{"param":"indicator","allowed":["heavy_rain_share","longest_dry_spell","rx5day"]}}}` |
| result not produced yet | 404 | `{"error":{"code":"DATA_NOT_AVAILABLE","message":"This data is not available yet.","details":{"dataset":"interaction_summary","region_id":"IGP","season":"MAM"}}}` |
| server bug | 500 | `{"error":{"code":"INTERNAL_ERROR","message":"Something went wrong on the server. Please try again.","details":{}}}` |

Use `details.allowed` to rebuild a selector, and `details.available` to clamp the period picker.
A wrong value always gets its own `INVALID_*` code, however long it is (e.g. a full date `2003-01-01` →
`INVALID_PERIOD`, a 40-character region → `INVALID_REGION`); `VALIDATION_ERROR` only means a missing or
wrongly typed field. The live `/docs` page now shows this `{"error":{...}}` shape for every error.

## Downloads

**CSV:** `GET /api/v1/export/csv?region_id=IGP&variable=aod&what=series|trend|anomalies&start=YYYY-MM&end=YYYY-MM`
→ `text/csv` attachment (filename in `Content-Disposition`, readable from the browser: CORS exposes it). Lines starting with `#` are metadata (MOCK/REAL,
source, DOI, data_version, units). Errors are always JSON, never a CSV. `what=series` needs ≥ 70% valid values
in the period (`INSUFFICIENT_DATA` otherwise: show "Too many missing values in this period").

**PDF:** `POST /api/v1/report` with
`{"region_id":"IGP","variables":["rainfall","aod"],"start":"2003-01","end":"2024-12","season":"all","include":["trend","anomalies","interaction","indicators"],"include_ai_summary":false}`
→ `{result:{report_id,url,pages,generated_at}}`; then open `url` (`GET /api/v1/report/{id}`, `application/pdf`).
Disable the button while waiting (target < 10 s; a cold host adds up to 60 s).
**Download the PDF straight away** (decision R-5): saved reports are deleted after **1 hour**, when more than
200 are stored, and whenever the free host restarts or sleeps. Never store the `url` for later.
The server makes at most **2 PDFs at once** and **10 per device per minute**.

| PDF outcome | UI |
|---|---|
| `400`/`422` (`INVALID_*`, `PERIOD_TOO_SHORT`, `INSUFFICIENT_DATA`) | show the message next to the form (same ≥ 10-year rule as Trend Lab) |
| `500 REPORT_FAILED` | "The PDF could not be created" + offer the **printable report screen** (browser print of the current results) and the **CSV download** |
| `404 REPORT_NOT_FOUND` on download | the report expired (1 hour) or the host restarted; call `POST /report` again silently (once) |
| `503 REPORT_BUSY` | "The server is busy making other reports"; retry once after the `Retry-After` header (seconds) |
| `429 RATE_LIMITED` | "Too many reports in a minute"; keep the button disabled for `Retry-After` seconds |

## Static fallback (if the backend is down)

`python scripts/export_static_snapshot.py` writes `snapshot/` (use `--require-real` for the judged version;
it refuses mock data). Host the folder next to the built frontend and read `snapshot/manifest.json`:

- `files["/api/v1/interaction?region_id=IGP&season=JJAS"].file` → path of the saved response (same JSON as live).
  Build the key with the parameters in the order used in this guide; snapshot anomalies use the full period
  (`/api/v1/anomalies?region_id=IGP&variable=both`).
- `unavailable[url]` → the error code the live API gave (show the same empty state).
- `selections` → which region/variable/season/indicator combinations exist; disable the others.
- `selections.reports` → ready-made PDFs (`reports/IGP.pdf`) for the report button.
- `data_status` → the MOCK banner rule still applies.


## New discovery and insight routes (14 Nov; trendlib)

Same envelope, error and MOCK-banner rules as above.

| Screen idea | Call | Use |
|---|---|---|
| "Start investigating" wizard | `GET /discover/questions` then `POST /discover {theme, place_type, question, region_id}` | Render `questions[]`; show `suggestions[]` cards with `plain_definition`, `reasons[]`, `caveat`; button from `next_step` (analyse now vs. "get this data from Giovanni") |
| Variable glossary | `GET /catalog` | `variables[]` with `available_now`; `region_presets[]` boxes for the map |
| Trend chart | `POST /analyze/detail` (same body as `/analyze`) | Plot `analysis.fit[]`: `value` (points), `fitted` (line), `lower`/`upper` (band); show `plain_language`; `analysis.detection` and `analysis.change_point` as callouts |
| "What is changing?" dashboard | `GET /scan?season=all` | Table of `rows[].headline`, coloured by `status`; banner for `opposite_directions[]` |
| Upload your own data | `POST /analyze/series {giovanni_csv, conversion}` | Same output as research series; show `input_origin` and `input_provenance` |
| Real-data demo | `GET /demos`, `POST /analyze/series {research_id}` | Step-through player; `data: "real"` demos need no store data |

Seasons for `/analyze/detail`: `all` (seasonal cycle removed) or `JF/MAM/JJAS/OND` (one complete-season mean per year, so `fit[]` has at most one point per year).
