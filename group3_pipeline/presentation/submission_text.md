# Submission text — scientific contribution draft

## Detailed description

TrendTrace investigates regional rainfall and atmospheric aerosol records using NASA data. The current empirical workflow covers January 2003–December 2024 in two rectangular analysis boxes: IGP [76,24,88,30] and TN [76.5,8,80.5,13.5], in west/south/east/north order. These boxes approximate regions and are not exact administrative boundaries.

Twelve original Giovanni exports were acquired: primary IMERG Final V07 and Aqua MODIS C6.1 monthly/daily series for each box, plus monthly Terra MODIS and MERRA-2 AOD comparison series. The workflow preserves raw files and hashes, audits units and fill values, indexes genuine missing dates, measures temporal availability, exports a documented data contract and computes descriptive climatologies, monthly anomalies and regional rainfall indicators.

The observed rainfall climatology peaks in July for IGP and November for TN. JJAS supplies 81.8% of mean annual rainfall in IGP; OND supplies 44.4% in TN. Mean annual rainfall from the monthly product is 1,081 mm and 1,231 mm respectively. These are descriptive findings for the chosen boxes. They are not significance tests or causal evidence.

Defined anomaly outputs and their full dates, thresholds, baseline counts, scores and coverage are supplied. Rainfall indicators include longest dry spell and the share of wet-day rainfall above a baseline P95, calculated from regional daily means. The latter is an adapted percentage indicator, not unchanged ETCCDI R95p.

## NASA data acknowledgement

We acknowledge NASA GES DISC and Giovanni, NASA/JAXA GPM IMERG Final V07, NASA Aqua/Terra MODIS Collection 6.1 combined 550 nm AOD, and NASA GMAO MERRA-2 M2TMNXAER v5.12.4 total aerosol extinction AOT. Exact raw headers, reproduction URLs, acquisition metadata and hashes accompany the data. Download date: 14 November 2026. Dataset research links and product details are recorded in docs/datasets.md and metadata/sources.json.

NASA mission illustrations, GIBS Blue Marble basemap and the published NASA Earth Observatory aerosol figure are credited in image_sources.json and slide notes. Published figures provide background and are not presented as newly computed project results.

## Methods and uncertainty

Rainfall monthly rates are converted using actual calendar-month duration. Monthly rainfall anomalies use same-calendar-month P10/P90 with coverage and dry-baseline controls. AOD anomalies use log-positive same-month z scores and ±2 thresholds. The common baseline includes each tested observation. The minimum eligible baseline sample count is an explicit operational choice requiring review.

MODIS AOD samples sufficiently clear conditions and is not surface PM2.5. Daily spatial coverage fractions were not exported. Daily Aqua AOD gaps and one non-positive TN retrieval remain explicit. Monthly and daily rainfall products do not agree exactly; paired differences are recorded without forced correction. Terra/MERRA-2 comparisons are descriptive and do not provide independent ground truth or trend validation.

## Current implementation boundary

Real data preparation, anomalies, rainfall indicators, descriptive comparisons and automated Part A checks have been executed. Independent peer review, Aadarsh’s executable trend/evidence/interaction functions and statistical validation Part B remain pending. Do not claim significance, confidence labels, lag relationships, causal attribution or a completed working app until the corresponding team work is completed and checked. Adapt the final submission to the actual integrated app and current event requirements.

## AI-use disclosure

AI assisted with reading the supplied role documents, researching NASA documentation, implementing and checking data-processing code, producing descriptive analyses, drafting methods/narration/submission text and preparing the presentation. One conceptual workflow illustration is AI-generated and labelled. Scientific charts derive from actual NASA exports. No observational values or statistical findings were generated as substitutes for measured data. The team must review the outputs and report the assistance according to event rules.
