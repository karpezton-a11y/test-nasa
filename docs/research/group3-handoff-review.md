# Group 3 research handoff review

> **Update 14 November 2026 (challenge-readiness review).** The deck in `research data/` was edited: outdated "statistics pending" statements on slides 2, 12, 14, 26, 27, 30 and the closing slide were corrected, and four slides were inserted before the closing slide: 32 (trend tests on the real annual series), 33 (real findings across regions, added later on 14 Nov), 34 (years-to-detect and step changes) and 35 (challenge mapping). Slides 1–31 keep their numbers; the closing slide is now 36. The statements below about missing executable functions describe the state before `analysis/trendlib` was added; see docs/decisions.md TT-01..TT-09.

Reviewed 14 November 2026 for Adrian's backend integration. Research documents are source material; their checklists, proposals and example values do not constitute completed code, data delivery or team approval.

## Sources and review scope

- **Aadarsh:** `TrendTrace-2.pdf`, 42-page *Team Scientific Research Handbook*, dated 13 November 2026. Method and interface details below refer to the printed page numbers. SHA-256: `b717b918ff2396b2b20cbc007543f8b225bf77d456a9cf614c32c8ceb245e834`.
- **Sritharan:** `Sritharan_Observed_Research.pptx`, 32-slide *Observed rainfall and aerosol research* briefing. All slide text, speaker notes and eight embedded XLSX workbooks were inspected. References below use slide numbers. SHA-256: `8e1b1ffd19b671bcf393925b13e7c9066d34ebad3ad72f40933f10f8e5546e22`.

The PDF is a methods handbook, not a completed statistical-results package. Its p26 coverage, confidence-interval and p/q numbers are labelled display examples. Page 31 says results should be populated after validation. Those values must never become API results or reference fixtures.

The slides report an executed observed-data workflow, but repeatedly state that independent scientific review is pending. Slide 26 and its notes explicitly say the supplied PDF contains no executable Aadarsh functions or completed statistical analysis. The deck names an accompanying data/code package; that package is not embedded in the presentation.

## What can be integrated from these materials

Adrian can document the exact reported products, fields, analysis boxes, period, definitions, limitations and remaining interface decisions. These are suitable inputs to a methods/data-source draft, a handoff checklist and integration validation rules. They do not authorise changing frozen API fields or declaring scientific sign-off complete.

| Topic | Material actually supplied | Integration consequence |
|---|---|---|
| Study design | PDF pp13–14; slides 3–5 | Proposed IGP box `[76,24,88,30]`, TN box `[76.5,8,80.5,13.5]`; Jan 2003–Dec 2024. Preserve analysis-box wording, not administrative boundaries. |
| Product identity | PDF pp8–12; slide 7 and notes | IMERG Final V07 monthly/daily precipitation; Aqua MYD08_M3/MYD08_D3 C6.1 combined AOD at 550 nm. Optional Terra and MERRA-2 remain separate sources. |
| Exact AOD fields | Slide 7 notes | Monthly `AOD_550_Dark_Target_Deep_Blue_Combined_Mean_Mean`; daily `AOD_550_Dark_Target_Deep_Blue_Combined_Mean`. Actual export headers/scale metadata still require the package. |
| Unit treatment | Slide 9; PDF pp9–11,17 | Group 3 converts monthly mm/hr using 24 × calendar days to mm/month; daily rainfall stays mm/day; AOD is dimensionless (`1`). Backend must not repeat conversion. |
| Methods and limitations | PDF pp21–30; slides 15,20,27 | Can populate a source-qualified methods draft; statistical execution and peer review remain separate. |
| Observed descriptive findings | Slides 10–24 | May be cited as Sritharan-reported findings with stated methods; not independently verified backend outputs. |
| Software checks | Slide 28 and notes | Reported 22 isolated implementation tests are Group 3's reported checks, not the backend suite or independent retrieval validation. |

## Reported observations and counts

The following are **reported by Sritharan's deck**, not independently reproduced from supplied raw/processed files:

- Slides 2 and 25: 12 NASA regional exports, comprising eight primary monthly/daily exports and four monthly Terra/MERRA-2 comparison exports. The all-source monthly CSV is reported to have 2,112 rows; the primary monthly subset 1,056 rows; daily CSV 32,144 rows. Source IDs must distinguish each product.
- Slides 3 and 10: the period contains 264 expected monthly timestamps and 8,036 expected daily dates per series. Both regions reportedly have 264/264 monthly rainfall and Aqua AOD values and 8,036/8,036 daily rainfall values. Daily Aqua AOD is reported as IGP 7,907/8,036 (1.61% missing) and TN 7,473/8,036 (7.01% missing).
- Slides 11–14: IGP rainfall share in JJAS is reported as 81.8%; TN shares are 44.4% OND and 36.2% JJAS. Mean annual rainfall from monthly-product sums is reported as IGP 1,081 mm/year and TN 1,231 mm/year. Mean of regional monthly Aqua AOD is reported as IGP 0.530 and TN 0.309.
- Slide 16: reported unusually-high/wet, unusually-low/dry and typical month counts are IGP rainfall 36/30/198; TN rainfall 36/33/195; IGP AOD 4/4/256; TN AOD 5/4/255. Tail flags depend on the baseline and rule; these counts do not establish a changing climate or trend significance.
- Slides 21–22: maximum annual dry spells are reported as IGP 84 days in 2008 and TN 73 days in 2024. Highest annual wet-day rainfall shares above baseline P95 are reported as IGP 28.8% in 2012 and TN 42.2% in 2005. These are regional-mean indicators, not station extremes or causal findings.

Slides 18–19 distinguish Sritharan's Aqua April comparison from the published NASA Terra six-day case. Slide 23's product comparisons are descriptive, and MERRA-2 is not independent truth. Slide 24 reports differences between daily-summed and monthly-product rainfall and instructs the team to keep the products separate. None supplies a reviewed long-term slope, p-value, confidence interval or interaction result.

## Scientific definitions and unresolved compatibility

### Time, seasons and source identity

- PDF pp14,24 and37 use `ALL`; backend core season is `all`. Sritharan's annual indicator source notes (slides 21–22) use season `ALL`; backend indicator season is `annual`. These need an explicit, reviewed ingestion mapping appropriate to the object. Do not rename public enums or interpret all-month monthly trends as annual indicators.
- PDF p17 includes `data_version` and `method` in a proposed CSV presentation; slide 25 explicitly retains the original nine-column series contract with version/method information in metadata sidecars. Confirm actual delivered headers instead of inventing extra columns.
- The handbook's example source ID `IMERG_FINAL_V07_DAILY` differs from the backend's `IMERG_V07_FINAL_DAILY`. The real source registry and an approved identity mapping must resolve this; do not silently blend or relabel sources.
- PDF pp24–25 describe time-indexed numeric series and context requirements, not executable Python signatures. The adapter's concrete frame/keyword/exception conventions still need agreement with the actual Group 3 package.

### Coverage and missing values

- PDF p17's AOD low-coverage threshold 0.30 is provisional; pp37–38 list its definition as an open decision. Do not adopt it as approved solely because it appears in the handbook.
- Slide 9–10 notes distinguish **temporal availability** from **spatial valid-cell fraction**. Daily spatial fractions were not exported and remain unknown/null, never 100%. Monthly temporal availability is derived from matched daily products. Existing `valid_fraction` semantics must be confirmed before ingesting these fields.
- Slide 9 reports one non-positive TN daily AOD retrieval. It remains explicit and needs review before logarithmic analysis. The backend must not replace it, take its logarithm, fill a gap or silently convert it to zero.
- PDF pp24–26 require preservation of true date spacing and gaps. Dropping missing months and treating remaining observations as adjacent is not an approved autocorrelation treatment.

### Anomalies

- PDF pp21–22 and slide 15 use the same-calendar-month 2003–2024 baseline. The baseline includes the observation under test; disclose this limitation.
- Rainfall: linear P10/P90 thresholds, temporal coverage at least 90%, dry flag suppressed when same-month median is below 10 mm/month. Slide 15 adds suppression when lower/upper thresholds tie. The dry suppression threshold remains a team-defined rule requiring review.
- AOD: positive monthly values, logarithmic transformation, sample-standard-deviation z-score, flag z ≤−2 or z ≥2. Low-coverage cautions must remain visible.
- **Slide 15 sets a minimum of 15 eligible same-calendar-month values.** Earlier backend draft text proposes 10. The handbook does not settle that minimum. Sritharan/Aadarsh must approve the scientific choice and contract/version consequences before implementation; the backend must not calculate a new baseline to settle the disagreement.

### Rainfall indicators

PDF pp20–21 and slide 20 define adapted regional-mean metrics:

- Longest dry spell: daily regional mean below 1 mm/day; missing days interrupt a spell; season/year boundaries stop the count.
- Heavy-rain share: wet days at least 1 mm/day; region/season-specific baseline wet-day P95; rainfall **strictly above** that threshold divided by **all wet-day rainfall**, expressed as a percentage. It is not a rainy-day-count percentage or unchanged ETCCDI R95p.
- At least 95% of expected days must be valid for the year/season; otherwise the indicator is null. No missing value is replaced by zero.
- PDF p20 lists Rx5day as optional; the deck does not demonstrate a completed Rx5day result. Keep it unavailable until the actual output/definition is supplied.

### Trend, evidence and interaction

- PDF pp22–26 proposes all-month deseasonalisation, Hamed–Rao modified Mann–Kendall, actual-decimal-year Theil–Sen slopes, and gap-aware processing. Page 14 recommends one seasonal aggregate per year for seasonal trend analysis. Group 3 must identify the actual implemented series type, coverage/count conventions and function interface.
- A conventional Sen interval is not automatically autocorrelation-corrected when an MK p-value is corrected (PDF pp23–24; slide 27 notes). Preserve that limitation.
- PDF pp26–27 retains the four evidence labels and thresholds (ten-year record/70% validity gate; significance, interval and sensitivity agreement). PDF pp23–24,38 leave raw p versus FDR-adjusted q for evidence labels unresolved. Do not add q/interval-method fields to the frozen public contract or recompute evidence in the backend without the agreed contract process.
- PDF pp27–29 proposes seasonal rainfall P90 events (≥ threshold), at least seven-day separation, AOD windows D−3..D−1 and D+1..D+3 excluding day D, and at least one valid AOD day in each window. It proposes paired Wilcoxon, a bootstrap median-change interval and up to five same-month controls per event excluding ±3 days. Ties, sampling, random seed and time-dependence decisions still need an implemented, reviewed package. A methods description is not an interaction-summary file.

## What the embedded workbooks cannot supply

The eight PPTX workbooks are rounded snapshots: 12-row rainfall/AOD climatologies, 22-row annual rainfall/AOD/dry-spell/heavy-share summaries, a two-row April comparison and five test-category counts. Speaker notes explicitly state that workbook values are rounded to six decimal places while originals preserve recorded precision.

They cannot reconstruct the full 264-month or 8,036-day source series, point-level QC, source provenance, anomaly baseline records or statistical reference outputs. Do not interpolate, reverse-engineer or label reconstructed observations as real. They are presentation evidence, not replacements for the named CSV/JSON/code handoff.

## Required package for honest live integration

Sritharan/Aadarsh need to supply the actual files or a repository location containing them:

- [ ] Primary and comparison `timeseries_monthly.csv` (or explicit primary subset) and `timeseries_daily.csv`, with original nine columns, exact source IDs, canonical units, real dates, nulls and QC.
- [ ] Real variables, regions/GeoJSON and sources metadata; `provenance.json`/raw-hash log with exact export headers, product versions, SDS names, real citations/access dates and the loader's versioned provenance/manifest agreement.
- [ ] Full-precision anomaly results and rainfall-indicator outputs plus their definitions, baseline counts/thresholds, coverage semantics and the reviewed `ALL`/`all`/`annual` mapping. Rx5day only if actually implemented.
- [ ] Installable Group 3 `analysis/trendlib` code, dependency/version metadata, callable trend/evidence/interaction functions, actual input/keyword signatures and named data-quality exception classes.
- [ ] Genuine `trend_results_reference.json`, advanced endpoint references, validated interaction summary and independent statistical validation Part B. Values shown as examples in the PDF are not reference outputs.
- [ ] Actual `docs/methods.md`, limitations text and validation report Part A/B, with open scientific decisions clearly distinguished from approvals.
- [ ] Team sign-off for the minimum anomaly baseline, mask/coverage meaning, seasonal aggregation, interval treatment and raw-p/FDR evidence choice, including any required contract-version change.

Package absence currently blocks honest execution of the live statistical integration and real reference tests. Adrian can finish the software adapters, documentation and acceptance gates; he cannot manufacture Group 3's code, observations, scientific results or peer sign-off from these documents. Mock mode must remain visibly mock, real missing assets must remain unavailable, and production must continue to reject mock data. Final frontend screenshots, demo and deployment timing still require the actual integrated app and environment.
