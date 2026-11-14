# Challenge-readiness audit — 14 November 2026

A full review of the repository (backend, tests, scripts, data, docs) and the research deck against the NASA Space Apps 2026 challenge **"Be An Earth System Trend Detective!"**. This page records what was wrong, what was changed, what was added and why, and what the team still has to do.

Test suite after the changes: **618 passed, 5 skipped** (the skips are real-data acceptance tests waiting for Group 3 files). Security audit: no findings. Live smoke test: 26/26.

## 1. Requirements coverage

| Challenge element | Before | Now |
|---|---|---|
| Identify variables that could show trends | 2 variables (rainfall, AOD) with placeholder "MOCK description" text | 21-variable catalogue across MODIS, OMI, AIRS, GPM, MERRA-2, GLDAS, GRACE with plain definitions, why it trends, caveat, product/field and Giovanni ID (`GET /catalog`) |
| Acquire data for a region | Group 3 files only (not in repo); real store refused any other variable | NASA POWER fetcher (real data, no login), Giovanni CSV parser and importer, region presets, real store accepts catalogue variables |
| Generate and visualise a time series | `/timeseries` only; no trend line (decision R-4 open) | `/analyze/detail` returns the series plus fitted Theil–Sen line and uncertainty band for the chart |
| Rate of change | **Not computed.** Fixed fixtures; adapter waiting for an undelivered package | Theil–Sen per decade with interval; OLS slope; % change per decade; change over period |
| Significance (t-test, Mann–Kendall, CI) | **Not computed** | Hamed–Rao modified Mann–Kendall, OLS t-test, confidence intervals, sensitivity runs, evidence label |
| What / where / how much | Region compare (2–4) only | `/scan`: all regions × variables, FDR q-values, ranked headlines |
| Same process, opposite trends in different regions | Not addressed | `/scan.opposite_directions` and `/compare` |
| Simple definitions for students | Placeholder text | Catalogue definitions and plain-language result summaries |
| Short series of questions | Not present | `/discover/questions` + `/discover` with reasons |
| Demonstration examples | Not present | `/demos` (5) + `scripts/run_demo.py`; 2 demos use real NASA-derived data |
| Data with trend potential from region characteristics | Not present | Recommender scores by place type (desert, rain forest, estuary, city, mountain snow, ocean, farmland) and everyday keywords |
| Trend not significant yet / longer record | Not addressed | Years-to-detect (Weatherhead 1998) in every detail/series result |
| Seasonal cycle removal | Planned in handbook only | Implemented (deseasonalised all-month, complete-season means) |
| Non-linear / step changes | Not addressed | Pettitt change-point test on detrended residuals |

## 2. Issues found and fixed

| # | Severity | Issue | Where | Fix |
|---|---|---|---|---|
| 1 | Critical | The backend computed no statistics. `science.py` only forwarded to a `trendlib` package that Group 3 never delivered (the deck says so on slide 26), so real mode could not produce a single trend | `backend/app/services/science.py` | Wrote `analysis/trendlib` 1.0.0 implementing the handbook protocol; imported automatically from the repo |
| 2 | Critical | Mock trends were hand-written fixtures that did not match the mock series (IGP AOD fixture 0.021/decade; plotted series trends at 0.056/decade) | `data/mock/normal/trend/*` | Mock mode now computes with trendlib on the mock series; fixtures only as fallback |
| 3 | Critical | Only 4 fixtures existed, so any season other than `all`, any shorter period, alpha ≠ 0.05 or exclude_low_coverage returned 404 DATA_NOT_AVAILABLE: most of the UI's options failed in a live demo | `services/core.py` | Any valid selection is computed |
| 4 | High | Real store hard-coded units for rainfall/AOD only and rejected every other variable at startup | `services/real_store.py` | Catalogue variables accepted with their declared unit; frozen units unchanged |
| 5 | High | Same `result_id` for alpha 0.05 and 0.10 (and exclude_low_coverage) made `/explain` report the ID as ambiguous | trend result IDs | `_a0.10` / `_xlc` suffixes |
| 6 | Medium | Omitted dates used the region's widest span, so a variable with a shorter record (e.g. OMI from 2004) would fail the coverage gate | `services/core.py` | Default to the variable's own observed span |
| 7 | Medium | Explanation numbers formatted as 1 d.p. (rainfall) or 3 d.p. (everything else): a 0.0004/decade slope would read "0.000", NO2 slopes as 15-digit numbers | `ai/facts.py` | Rainfall 1 d.p., AOD 3 d.p. (contract), others 3 significant figures |
| 8 | Medium | No multiple-testing control although the deck lists "multiple comparisons" as a limitation | — | Benjamini–Hochberg FDR in `/scan` |
| 9 | Medium | Interval treatment undecided (INT-03): a plain Sen interval disagrees with a corrected p-value | — | Interval built from the Hamed–Rao-corrected variance (TT-04) |
| 10 | Medium | Excluding low-coverage months could remove a whole calendar month, crashing deseasonalisation | trendlib | Such months are left out and named in the limitations |
| 11 | Low | `/health.trendlib_version` was always null | `routers/health.py` | Reports the bundled version |
| 12 | Low | README opened with team-internal blockers instead of what the tool does | `README.md` | New challenge-mapping opening, statistics and data sections |
| 13 | Deck | Slides 2, 12, 14, 26, 27, 30 and the closing slide said trend statistics were unavailable or pending | `research data/*.pptx` | Corrected; added slides 32–34 with real trend results, years-to-detect and the challenge mapping |

## 3. Features added (each with its purpose)

| Feature | Purpose |
|---|---|
| `analysis/trendlib` | The core of the challenge: rate of change and significance, done the way the team's handbook specified, verified against pymannkendall and SciPy |
| `POST /analyze/detail` | Gives the frontend everything a trend chart needs (points, line, band) plus a sentence a student can read |
| `GET /scan` | Answers "what, where, how much, significant?" in one call, with FDR so many tests do not produce false discoveries |
| Opposite-direction flags | Makes the challenge's key idea (one process, opposite regional trends) visible |
| `GET /catalog` | Simple definitions of each variable for high-school and college users |
| `/discover` questions + recommender | The "short series of questions" the brief suggests, with reasons shown so it teaches rather than hides logic |
| `POST /analyze/series` + Giovanni parser | Lets anyone test any NASA variable for any region today, with no code |
| `fetch_nasa_power.py` | Real NASA data for any box without an Earthdata login |
| `import_giovanni.py` | Turns downloads into real-mode data with provenance and SHA-256 manifest |
| Real research series + demos | Demos that use real NASA-derived data even before the full real store is loaded |
| Years-to-detect | Turns "not significant" into a useful answer: how many more years are needed |
| Pettitt step change | Warns when a series jumps (sensor change, sudden event) rather than trending |
| `run_demo.py` | A watchable demo in the terminal for recording before the UI exists |

## 4. Real results now available (Group 3 annual export, 2003–2024)

| Box | Series | Theil–Sen per decade | p (Hamed–Rao) | Result |
|---|---|---|---|---|
| IGP | Annual mean AOD | +0.079 (+14.9%) | < 0.001 | Increasing |
| TN | Annual mean AOD | +0.052 (+16.9%) | < 0.001 | Increasing |
| IGP | Annual rainfall | +20 mm/year | 0.652 | No significant trend (~70 years needed) |
| TN | Annual rainfall | −4 mm/year | 0.955 | No significant trend |
| TN | Heavy-rain share | −4.7 percentage points | 0.143 | No significant trend (~29 years needed) |

These come from chart workbook values rounded to six decimals. They are statistical patterns in box averages, not causes, and AOD is not PM2.5.

## 5. Still open (team actions)

1. ~~Commit Group 3's data package.~~ **Done (later on 14 Nov):** `group3_pipeline/` is in the repo, `data/processed/` is built from it and the live site serves real data.
2. ~~Fetch more real variables~~ **Partly done:** a GitHub Actions workflow fetched NASA POWER temperature and rainfall for 6 regions, now served. Still worth adding by hand from Giovanni (needs an Earthdata login): OMI NO₂ for Delhi and Los Angeles, GLDAS soil moisture.
3. ~~Interaction composites~~ **Done:** implemented in `trendlib.interaction` and served with real data; Aadarsh should review it.
4. **Independent review** of trendlib by Aadarsh; reconcile the anomaly baseline minimum (15 vs 10, INT-02).
5. **Submission deck.** The research deck is an internal briefing (slides 29–30 discuss role splits). The compressed competition deck is still missing; slides 32–34 can be reused in it.
6. **Frontend** (`frontend/` is empty) — planned after the core, as agreed. Use docs/handoff/frontend_endpoints.md.
7. PDF reports still accept at most two variables and show the trend as text rather than a fitted line (R-4); `/analyze/detail` already provides the line for the web chart.
