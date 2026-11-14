# Observed research findings — Sritharan, G3 M1

Analysis period: January 2003–December 2024. Downloaded through the authenticated NASA Giovanni session on 14 November 2026. These are actual regional observation/model exports; no synthetic fixtures enter this analysis. Independent scientific review is pending.

## What was acquired

Twelve original regional CSV exports: monthly and daily IMERG Final V07 precipitation and Aqua MODIS C6.1 combined 550 nm AOD for IGP and TN; monthly Terra MODIS C6.1 combined AOD and MERRA-2 M2TMNXAER v5.12.4 TOTEXTTAU for both boxes.

The IGP rectangle is [76,24,88,30]; TN is [76.5,8,80.5,13.5], in west/south/east/north order. These are analysis boxes, not exact administrative or physiographic boundaries. Raw headers retain the actual included grid centres. MERRA-2 and MODIS have different included grid centres and resolutions.

## Availability and QC

| Series | IGP | TN |
|---|---:|---:|
| Monthly rainfall | 264/264 | 264/264 |
| Monthly Aqua AOD | 264/264 | 264/264 |
| Daily rainfall | 8,036/8,036 | 8,036/8,036 |
| Daily Aqua AOD | 7,907/8,036 | 7,473/8,036 |

Daily AOD missingness is 1.61% (IGP) and 7.01% (TN). All monthly primary values are present. Monthly temporal availability is measured from the matched daily series; daily spatial valid-cell coverage was not supplied and remains unknown. A regional mean existing does not prove sufficient area was observed.

One TN daily AOD value is non-positive. It is retained transparently pending retrieval-range review. It is not a monthly log-baseline input. All primary monthly AOD values are positive.

## Seasonal and annual observations

| Metric | IGP box | TN box |
|---|---:|---:|
| Mean annual rainfall from monthly product | 1,081.1 mm | 1,231.0 mm |
| Calendar-month rainfall peak | July | November |
| JJAS share of mean annual rainfall | 81.8% | 36.2% |
| OND share of mean annual rainfall | 5.2% | 44.4% |
| Mean of 264 monthly Aqua AOD values | 0.530 | 0.309 |

Seasonal shares divide the sum of the relevant calendar-month climatology by the full-year climatology. Annual rainfall uses the sum of monthly amounts. Annual AOD charts average the twelve regional monthly means without weighting months by day count. These descriptive summaries are not trend significance tests.

## Monthly anomalies

| Box / variable | Wet or high | Dry or low | Typical |
|---|---:|---:|---:|
| IGP rainfall | 36 | 30 | 198 |
| TN rainfall | 36 | 33 | 195 |
| IGP Aqua AOD | 4 | 4 | 256 |
| TN Aqua AOD | 5 | 4 | 255 |

The rainfall baseline is the same calendar month during 2003–2024, with interpolated P10/P90, daily temporal availability ≥90%, and suppression of dry flags when the baseline median is below 10 mm/month. Aqua AOD uses a same-calendar-month log z score with sample SD and ±2 thresholds. Baseline minimum is 15 eligible values. The baseline includes the evaluated observation. Exact dates, values, scores, eligible baseline counts, coverage and notes are in anomalies_monthly_primary.csv. Counts are consequences of these rules; they do not demonstrate increasing event frequency.

## Regional rainfall indicators

| Indicator | IGP | TN |
|---|---|---|
| Maximum annual longest dry spell | 84 days, 2008 | 73 days, 2024 |
| Highest annual heavy-rain share | 28.8%, 2012 | 42.2%, 2005 |

These use regional daily means. A wet day is ≥1 mm/day; a dry day is <1 mm/day. Heavy-rain share is rainfall on wet days strictly above the regional baseline wet-day P95 divided by all wet-day rainfall, expressed as a percentage. It is an adaptation of extreme-rainfall concepts, not unchanged ETCCDI R95p. Dry spells stop at year/season boundaries; missing days interrupt a spell. Annual and JJAS/OND outputs require ≥95% expected dates. Regional means smooth local extremes.

## Aqua–Terra–MERRA-2 comparison

| Box | Comparison versus Aqua | Paired months | Mean bias | Pearson r | RMSE |
|---|---|---:|---:|---:|---:|
| IGP | Terra | 264 | +0.024 | 0.960 | 0.048 |
| IGP | MERRA-2 | 264 | -0.147 | 0.561 | 0.189 |
| TN | Terra | 264 | +0.018 | 0.945 | 0.032 |
| TN | MERRA-2 | 264 | -0.051 | 0.735 | 0.074 |

Bias is comparison minus Aqua; bias and RMSE are in dimensionless AOD units. Pairing is by calendar month. Raw correlations partly reflect common seasonality and are descriptive only. Different overpass, grids, included area, retrieval screening and averaging limit comparability. MERRA-2 assimilates observations and is not independent ground truth. No trend agreement or statistical p-value follows from these correlations.

## Daily–monthly rainfall consistency

| Box | Complete paired months | Mean absolute difference | Maximum absolute difference | Aggregate daily-minus-monthly difference |
|---|---:|---:|---:|---:|
| IGP | 264 | 1.71 mm/month | 12.04 mm/month | -1.83% |
| TN | 264 | 1.00 mm/month | 7.37 mm/month | -0.97% |

Aggregate percentage compares total daily-derived rainfall with total monthly-product rainfall over all paired months; it is not average monthly percentage error. The products remain separate. No arbitrary agreement tolerance or correction is imposed. NASA describes approximate matching of short-interval and monthly estimates with ratio controls; that is general context, not a verified explanation for each discrepancy here. The exact differences and their scientific importance require peer review. [NASA GPM FAQ](https://gpm.nasa.gov/data/faq).

## April 2020 context check

Aqua AOD in calendar April 2020 was 21.6% below the April 2016–2019 mean in IGP and 32.8% below it in TN. The corresponding means were 0.379 versus 0.483 (IGP), and 0.250 versus 0.372 (TN). These are descriptive comparisons. They do not identify a cause.

The published NASA Earth Observatory example uses Terra and the March 31–April 5 period and its map footprint. Therefore this calendar-April Aqua calculation is context, not an exact replication. Weather, humidity, sampling and emissions can all affect interpretation. [NASA published case](https://science.nasa.gov/earth/earth-observatory/airborne-particle-levels-plummet-in-northern-india-146596/).

## Limits and outstanding work

Aadarsh must independently review the data and methods and supply his executable trend/evidence/interaction functions. No Theil–Sen slope, corrected Mann–Kendall p-value, confidence label, lag correlation or event composite has been invented. run_reference.py can produce a hashed reference result only once his actual adapter is supplied. The team’s working app, screenshots and recording are separate integration outputs; they are not fabricated by this package.

The numerical results are reproducible exploratory findings for the specified boxes and baseline. They have not received independent peer review. No causal claim, surface PM2.5 inference, local extreme-event statement or validated long-term trend is justified by this package alone.

## Reproduce

Run python run_pipeline.py --manifest inputs.json --output results --figures, then python -m analysis.research_summary --results results. The original files and their hashes are preserved. Filter source_id before analysis; use timeseries_monthly_primary.csv for the four primary monthly series.

## Six-day window sensitivity check

The published NASA map compares March 31–April 5. An additional calculation uses our daily Aqua series for those same six calendar days in 2016–2020. It remains a platform/footprint sensitivity check, not a Terra replication. Each year’s valid-day regional mean is computed first; the baseline is the equal-weight mean of the four 2016–2019 yearly means.

| Box | 2020 six-day Aqua mean | 2016–2019 window mean | Difference |
|---|---:|---:|---:|
| IGP | 0.216 | 0.509 | -57.6% |
| TN | 0.230 | 0.389 | -40.8% |

Valid-day counts for every window are in results/aod_2020_six_day_context.csv. Window choice and retrieval sampling matter; these comparisons do not establish lockdown causation.

IMERG’s variable is total precipitation in liquid-water-equivalent units; rainfall is the team’s shorthand in the data contract. Frozen precipitation can contribute.

Chart workbook snapshots round plotted values to six decimal places for portable PowerPoint/Excel editing. Original CSVs and analysis JSON retain their recorded precision.
