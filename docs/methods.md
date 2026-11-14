# Scientific methods and current evidence status

## Source and execution status

This document records the analysis protocol and the observation-processing definitions described by Group 3. **Update 14 November 2026:** the trend protocol below is now implemented and executed by `analysis/trendlib` 1.0.0 (see "Implemented trend engine"). It is not a record that the statistical analysis has been independently validated. Sources are Aadarsh Praveen Kumar's scientific handbook v2.0, dated 13 November 2026, and Sritharan's 32-slide observed-research briefing, including its notes.

Sritharan reports executed acquisition, descriptive summaries, anomaly flags and two rainfall indicators. The deck also states that independent review is pending and that Aadarsh's executable functions, statistical evidence and reference trends have not been supplied (slides 2, 25–28). The separately referenced data/code package, full-precision observations, provenance and validation files were not included in these two documents. Rounded chart snapshots cannot replace those files. Consequently this text supplies methods and caveats for report integration; it does not establish a slope, p-value, confidence label or causal finding.

## Products, regions, period and canonical conventions

The reported primary products are IMERG Final V07 monthly/daily precipitation and Aqua MODIS MYD08_M3/MYD08_D3 Collection 6.1 AOD at 550 nm. Sritharan identifies the monthly combined AOD SDS as AOD_550_Dark_Target_Deep_Blue_Combined_Mean_Mean and the daily SDS as AOD_550_Dark_Target_Deep_Blue_Combined_Mean (slide 7 and notes). Terra monthly MODIS and MERRA-2 TOTEXTTAU are separate optional comparisons; they are not blended into Aqua observations or used to fill its gaps.

The intended common period is January 2003 through December 2024. IGP uses [76, 24, 88, 30] and TN [76.5, 8, 80.5, 13.5], ordered west, south, east, north. These are proposed rectangular analysis boxes, not administrative boundaries (handbook pp13–14; slides 3–5).

The public API retains variable IDs rainfall and aod, core seasons all, JF, MAM, JJAS and OND, and annual for annual indicator outputs. Rainfall units remain mm/month or mm/day; AOD uses 1 (dimensionless), displayed as unitless. Source IDs remain the frozen registry IDs, including IMERG_V07_FINAL_DAILY; differently ordered labels in source examples are not silently substituted. Group 3 and Adrian must confirm any source-label and ALL-to-all/annual mappings before import. Version and processing-method metadata remain in sidecars, preserving the nine-column series contract described on slide 25, despite the handbook's broader suggested CSV table on pp16–17.

## Observation processing and coverage

Sritharan reports converting the monthly IMERG rate in mm/hr to mm/month using 24 times the number of calendar days, retaining daily mm/day values, decoding documented fill values, rejecting duplicate dates and preserving missing observations (slides 7–10). These operations belong to Group 3's processing pipeline; the backend does not repeat them. Exact headers, scale/offset interpretation, source hashes, dates, export requests and aggregation methods require the referenced provenance and original files.

Daily spatial valid-cell fractions were not exported and remain unknown rather than being labelled complete. Monthly temporal availability is derived from matched daily products; it must not be presented as spatial coverage. Missing AOD is never zero, interpolated or replaced by a reanalysis value. One non-positive daily TN AOD retrieval is retained explicitly for review and cannot enter a logarithm (slides 9–10 and notes). Primary and comparison source series must be selected explicitly and kept separate.

## Planned trend and evidence analysis

Aadarsh proposes removing the calendar-month seasonal cycle for all-month trends, using Hamed–Rao modified Mann–Kendall for autocorrelation-aware significance, and Theil–Sen for a slope in canonical units per decade. Actual decimal-year timestamps must be retained so gaps do not compress time. A conventional Theil–Sen confidence interval is not automatically autocorrelation-corrected merely because the Mann–Kendall p-value is corrected (handbook pp22–26).

The backend's existing ten-year record and 70% selected-season valid-observation gates remain in place. Statistical calculations, gap handling, valid/expected counts and sensitivity outputs belong to Group 3. A result below the selected alpha follows the slope sign; otherwise its direction is no_significant_trend. Non-significance does not demonstrate no change.

The documented team evidence rule retains strong, moderate, weak and insufficient_data. Strong requires p < 0.05, an interval excluding zero, all sensitivity runs sharing the sign, at least two-thirds significant and at least 90% valid observations. Moderate requires p < 0.05, an interval excluding zero and at least two-thirds sharing the sign. Short or poorly covered records are insufficient_data; other results are weak. These labels are team conventions shown with their metrics, not an official NASA score (handbook pp26–27). Sensitivities proposed include low-coverage exclusion, ending the record in 2021, Seasonal Kendall, OLS, Terra and separate MERRA-2 comparisons. Their execution and sign-off are not established by the supplied documents.

## Implemented trend engine (analysis/trendlib 1.0.0)

The backend's science adapter calls `trendlib.compute_trend` for every `/analyze`, `/compare`, `/analyze/detail` and `/scan` request, in both data modes. Implementation choices, each traceable to the handbook:

- **All-month trends:** each calendar month's mean over the selected period is subtracted (deseasonalised anomalies). A calendar month with fewer than three valid values is left out and named in the limitations, rather than given an invented baseline; more than four such months raise InsufficientDataError.
- **Seasonal trends (JF, MAM, JJAS, OND):** one mean per year, using only years in which every month of the season is valid (handbook p14). Partial seasons are skipped, never averaged.
- **Time:** decimal years at mid-month or mid-season; missing slots are not compressed.
- **Significance:** Mann–Kendall S with tie-corrected variance, multiplied by the Hamed–Rao (1998) factor computed from rank autocorrelations of the Sen-detrended series that exceed the 95% bound (gap-aware: lags only pair observed slots). Output agrees with pymannkendall's `hamed_rao_modification_test` to 1e-9.
- **Slope and interval:** Theil–Sen median of pairwise slopes per decade. The Gilbert (1987) rank interval uses the **corrected** variance at confidence 1 − alpha, so the interval excludes zero exactly when the corrected p-value is below alpha (this answers the handbook's caution that a conventional Sen interval is not autocorrelation-corrected).
- **Parametric cross-check:** OLS slope, two-sided t-test and t interval.
- **Sensitivity runs:** exclude_low_coverage (when low-coverage months exist), end_2021 (when at least ten years remain), Seasonal Kendall (all-month only), OLS. MERRA-2/Terra comparison runs need those series and are not yet included.
- **Evidence rule v1:** insufficient_data if record < 10 years or valid observations < 70%; strong if p < alpha, interval excludes zero, at least two sensitivity runs all share the sign, at least two-thirds are significant and valid observations ≥ 90%; moderate if p < alpha, interval excludes zero and at least two-thirds share the sign; otherwise weak.
- **Extras:** Pettitt (1979) change-point test on Sen-detrended residuals (abrupt shifts beyond the trend); Weatherhead et al. (1998) years needed to detect the current rate with 90% probability; Benjamini–Hochberg FDR q-values across the series tested by `/scan`.
- **Exceptions:** only `InsufficientDataError` and `DataQualityError` map to INSUFFICIENT_DATA (decision SCI-02).

Real annual results (Group 3 export values, rounded to six decimals, 2003–2024): annual mean Aqua AOD rises by 0.079 per decade in the IGP box and 0.052 per decade in the TN box (Hamed–Rao p < 0.001 for both); annual rainfall, longest dry spell and heavy-rain share show no significant trend at alpha 0.05. These are statistical patterns in box averages, not causal findings.

## Real-data integration (Group 3 package, 14 November 2026)

`scripts/build_real_data.py` converts `group3_pipeline/results/` into the loader layout without changing any value. Served series, anomaly scores and indicator values are checked against Group 3's CSVs in `test_real_values_match_group3_csv`. Group 3 flags rainfall anomalies with linear P10/P90 *values*; the contract states thresholds on the score scale, so the served thresholds are the equivalent mid-rank cut-offs (39/44 and 5/44 with 22 baseline values), verified so that every unflagged month lies strictly between them except months whose dry flag is suppressed. Comparison products (Terra MODIS, MERRA-2) are never blended into the primary series; they appear only as the `terra_monthly` and `merra2` sensitivity runs of AOD trends. Indicator trends use one value per year (decision J-2).

**Rainfall–AOD interaction (trendlib.interaction):** events are days at or above the seasonal P90 of daily regional rainfall over 2003–2024, keeping the first day of any cluster with at least seven days' separation; AOD windows are days −3..−1 and +1..+3 with the event day excluded and at least one valid retrieval per window (non-positive AOD retrievals excluded). Outputs: paired Wilcoxon signed-rank p (tie-corrected normal approximation, agrees with SciPy), bootstrap 95% interval of the median change (5,000 resamples, seed 20261114), up to five random same-month control days per event at least three days from any event, and Spearman correlation of deseasonalised monthly anomalies (agrees with SciPy). Association only.

## Documented anomalies and rainfall indicators

Sritharan describes a same-calendar-month 2003–2024 anomaly baseline. Rainfall uses linear P10/P90, at least 90% temporal coverage, dry-flag suppression below a same-month median of 10 mm/month, and suppression when lower and upper thresholds tie. AOD uses positive monthly values, a logarithmic transformation and a sample-standard-deviation z-score, with flags at -2 and +2 (slide 15 and notes). These flags are defined unusual-month classifications, not trend significance tests.

The deck specifies at least 15 eligible baseline values; the earlier contract proposed 10. Sritharan and Aadarsh must reconcile this difference with Adrian before the backend changes an agreed rule. The source baseline includes the tested observation.

The documented dry-spell indicator is the longest consecutive run of regional daily mean rainfall below 1 mm/day, with missing days interrupting counting and year/season boundaries ending a run. Heavy-rain share uses region/season-specific baseline wet-day P95, wet days of at least 1 mm/day, and rainfall strictly above P95 divided by all wet-day rainfall, expressed as a percentage. At least 95% temporal availability is required (slides 20–22 and notes). These are regional-mean adaptations, not unchanged station-level climate indices. Rx5day remains an intended optional output; its execution is not demonstrated by the supplied briefing.

## Planned rainfall–AOD interaction

The handbook proposes events at or above seasonal regional daily rainfall P90, retaining the first qualifying event in a cluster with at least seven-day separation, and before/after AOD means over days -3 to -1 and +1 to +3, excluding the event day. At least one valid AOD day is required in each window. Proposed outputs include paired Wilcoxon results, a bootstrap 95% median-change interval, event and usable-pair counts, sampling percentages, and up to five same-month controls per event excluding dates within three days of events. A random seed and sampling strategy must be recorded. Monthly Spearman association uses aligned, deseasonalised series and requires a time-dependence caveat (handbook pp27–29). These are protocols, not executed interaction results in the supplied materials.

Association only. AOD is retrieved in clear skies, so rainy days are under-sampled.

## Decisions and statistical handoff still required

Sritharan and Aadarsh own confirmation of baseline eligibility, percentile ties, regional averaging/masks, temporal versus spatial coverage and annual indicator mappings. Aadarsh and Adrian own the executable function signature, gap-aware time index, seasonal annual aggregation and count definitions, confidence interval treatment, raw-p versus FDR-adjusted-q basis, and genuine reference outputs. The handbook explicitly leaves several choices open on pp37–38; the reported observation work does not constitute approval of those choices.

The API retains its frozen fields and enums. The handbook's ALL spelling and proposed raw/q reporting do not independently authorise new public values or fields. The pre-H7 evidence fallback also remains a joint Adrian/Aadarsh decision because not_assessed is outside the frozen evidence enum. Missing required scientific outputs remain unavailable rather than receiving a manufactured confidence label.

## Limitations

- trendlib implements the protocol but has not been independently reviewed; the full-precision input series and genuine reference outputs are still needed for monthly real-data validation.
- AOD measures atmospheric-column optical extinction and is not a direct ground-level PM2.5 or local air-quality measurement.
- MODIS clear-sky retrievals under-sample cloudy and rainy periods; unavailable AOD observations cannot be interpreted as low aerosol loading.
- Temporal availability and spatial valid-cell coverage are different quantities. Unknown spatial coverage must remain unknown.
- Regional boxes include heterogeneous land, neighbouring areas and coastal water. Box-average findings are not exact administrative or local-station findings.
- Regional averaging smooths local rainfall extremes; regional dry spells and heavy-rain shares are not local drought-severity or station-extreme measures.
- Only 22 annual values and 22 observations per calendar month are available in a complete 2003–2024 record; in-sample baselines, ties and threshold choices affect anomaly classification.
- Missing months alter time spacing and dependence. A conventional slope interval does not automatically account for serial dependence, and multiple testing can increase false-positive risk.
- Aqua, Terra and MERRA-2 have different sampling/product characteristics; MERRA-2 assimilates observations and is not an independent observational truth.
- Before/after differences and correlations describe associations. They do not establish that rainfall caused an AOD change.
