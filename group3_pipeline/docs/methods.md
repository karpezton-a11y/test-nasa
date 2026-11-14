# Data processing and methods

## Study design

TrendTrace compares rainfall and aerosol optical depth in two proposed analysis boxes over 1 January 2003 to 31 December 2024. IGP uses [76,24,88,30] and TN uses [76.5,8,80.5,13.5], ordered west, south, east, north. These rectangles include land outside the named regions and coastal water. The boundaries remain proposals until the team agrees them.

There are 264 expected monthly timestamps and 8,036 expected daily dates per region-variable series. Expected dates are a calendar property, not proof of observed coverage.

## Inputs and provenance

Primary products are IMERG Final V07 monthly GPM_3IMERGM and daily GPM_3IMERGDF, and Aqua MODIS Collection 6.1 MYD08_M3 and MYD08_D3 combined 550 nm AOD. Keep platform, version, processing run, variable, units, date bounds, fill values, scale/offset, spatial mask and aggregation in the manifest. Preserve originals. The pipeline records raw SHA256 hashes and processing metadata. Never expose authentication tokens in provenance or the repository.

Giovanni area-averaged time series are the primary route. The adapter requires exact header column names from the actual export. The source's documented metadata determines units and decoding. A raw netCDF/HDF file requires a separately verified extraction adapter; downloading such a global file alone does not produce a regional series.

## Unit conversion and quality control

For a monthly mean precipitation rate in mm/hour, multiply by 24 and calendar days in the corresponding month. Preserve a monthly accumulation without repeating the conversion. Keep daily mm/day unchanged. AOD remains dimensionless. Documented fill values become missing before decoding. Explicit scale/offset rules apply only once. Negative rainfall and nonfinite values are suspect. Additional validity ranges require source-specific metadata, not a universal AOD cutoff.

The code rejects duplicate timestamps after normalising monthly dates to month starts. It retains expected dates without filling observations. Genuine precipitation zero remains valid. Synthetic inputs exist only in tests and never enter scientific handoff files.

## Spatial aggregation and coverage

The region and averaging definition follow each recorded Giovanni export. For native gridded processing, use cell-area weights, with cosine-latitude weighting an approximation for regular latitude/longitude cells. Record valid-cell area and any land/sea mask. Do not equate pixel count with area without checking grid geometry.

Monthly temporal valid_fraction means the number of days with a valid regional daily value divided by calendar days. Derive it only from the explicitly matched daily product. Daily valid_fraction means spatial valid-cell coverage if available, otherwise unknown. A monthly mean cannot establish temporal availability by itself. Temporal availability does not prove spatial representativeness or eliminate clear-sky sampling bias. Low temporal coverage below 0.30 receives a warning under the provisional team rule.

## Monthly anomalies

The baseline consists of the same calendar month in 2003–2024 and includes the tested observation. Rainfall anomalies require measured daily temporal availability >=0.90. Eligible same-month observations determine the linear-interpolated P10 and P90 thresholds. Values at or above P90 receive unusually_wet and values at or below P10 receive unusually_dry, except that dry flags are suppressed when the baseline median is below 10 mm/month. A tied baseline with identical lower and upper thresholds receives no unusual flag. The output additionally records an empirical midrank score, (number below + half number tied)/n. The score and interpolated threshold are related but distinct conventions.

AOD uses z = (log(value) - mean(log baseline))/sample_SD(log baseline), with ddof=1. Positive values only enter this log baseline. A non-positive observation receives an undefined_log status, not an invented logarithm. Absolute z >=2 yields a corresponding high/low flag. The implementation guards numerical zero variance. Low-coverage flags carry cautions.

The operational minimum of 15 eligible same-month values is an explicit implementation choice requiring Aadarsh's review. It is not an official NASA threshold. Detrended anomalies are not implemented here because they require a reviewed trend fit from Aadarsh. The current outputs clearly use the original, in-sample baseline.

Combined flags describe co-occurrence of rainfall and AOD anomalies on the same date. They are not causal explanations.

## Rainfall indicators

The first implementation uses daily regional means. It labels all indicators accordingly. A wet day has rainfall >=1 mm/day. For each region and reported season, calculate linear P95 from all eligible baseline wet days in that season during 2003–2024. Heavy-rain share equals 100 times rainfall on days strictly above P95 divided by rainfall on all wet days in the evaluated year/season. Return null for a zero wet-rain denominator. This percentage adapts ETCCDI concepts and is not an unchanged standard R95p amount.

Longest dry spell is the longest consecutive run below 1 mm/day within the specified calendar year or season. Missing observations interrupt counting. Spells stop at season boundaries. An indicator requires at least 95% of expected days for its year/season. Even an eligible but incomplete period can underestimate a dry-spell maximum, which remains stated in its notes. Regional averaging smooths local extremes.

## Validation and reference results

Automated checks cover source metadata, dates, duplicate handling, conversions, missingness, bounds, indicator eligibility and anomaly edge cases. Monthly IMERG versus daily-sum comparisons require complete daily months and matched products. Report differences without forcing an arbitrary agreement tolerance. Review seasonal climatologies and source masks before interpretation. Independent review remains Aadarsh's responsibility.

run_reference.py uses Aadarsh's explicitly supplied adapter analyze_series(series, metadata). It records input and adapter hashes and preserves actual dates. It does not fabricate a replacement trend implementation or invent p-values. Aadarsh must handle missing-time autocorrelation, slope interval assumptions and evidence-label rules. Statistical validation Part B and interaction outputs remain his work.

## Limits

MODIS samples sufficiently clear scenes and measures column optical depth rather than surface PM2.5. Humidity and sampling can affect AOD. IMERG has retrieval and observing-system limitations. Terra and Aqua differ in overpass and sampling; MERRA-2 assimilates observations and is not fully independent confirmation. Twenty-two annual values offer limited power. A non-significant result is not proof of no change.

References: https://gpm.nasa.gov/data/imerg ; https://earth.gsfc.nasa.gov/climate/data/deep-blue/data ; https://giovanni.gsfc.nasa.gov/giovanni/doc/UsersManualworkingdocument.docx.html ; https://etccdi.pacificclimate.org/list_27_indices.shtml ; https://doi.org/10.5194/acp-15-7557-2015 . Project definitions come from the supplied Group 3 assignment and Aadarsh's TrendTrace-2.pdf.



## Executed observation update — 14 November 2026

Twelve real exports are now processed. Read research_findings.md and ../results/validation_report_part_A.md. Primary monthly and daily products and the Terra/MERRA-2 monthly comparison fields were confirmed in the actual portal. Results include the original exact included grid centres; these differ across grids. Daily spatial valid-cell fractions remain unknown. Statistical functions, independent review and app demonstration remain team dependencies.
