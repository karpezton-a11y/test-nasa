# Actual acquisition update — 14 November 2026

The primary and comparison exports have now been retrieved. The earlier access notes below describe the initial unauthenticated state; they are historical. Use inputs.json, results/provenance.json and docs/research_findings.md for current exact fields, source units and findings. Aqua monthly SDS is AOD_550_Dark_Target_Deep_Blue_Combined_Mean_Mean; Aqua daily SDS ends in Combined_Mean. Terra uses the matching monthly SDS and MERRA-2 uses TOTEXTTAU.

# Sritharan dataset research notes

Prepared 13 November 2026 IST for G3 Member 1. This is a preparation and source-review record, not analysis results. No observations have been downloaded or validated in this session. Product facts below are distinguished from proposed team choices and items needing inspection of an actual export.

## First objective

Understand the primary rainfall and aerosol products and establish access. The first scientific handoff during the permitted project period will be four monthly regional series: IGP rainfall, TN rainfall, IGP Aqua AOD, and TN Aqua AOD. Aadharsh reviews those files and uses them for trends and evidence. Daily series follow for indicators and interaction.

## Event timing

An official Space Apps team answer allows topic research and resource review before the hackathon, with project work starting Saturday 14 November at 09:00 in the Local Event time zone (or the Team Owner's residence for the Universal Event). Confirm your event's time zone. Do not treat preparation notes as permission to build submission code early.

Source: https://github.com/nasa/spaceapps/discussions/1827

## Primary rainfall

### Monthly IMERG Final

- Proposed product: GPM_3IMERGM, version 07; NASA's catalogue describes V07B.
- NASA describes a 0.1 degree grid, monthly gauge-informed estimates, and recommends the complete calibrated precipitation field, `precipitation`, for most users.
- DOI: https://doi.org/10.5067/GPM/IMERG/3B-MONTH/07
- Final Run suits retrospective research when rapid delivery is unnecessary. NASA cautions that output formats can express rainfall as a rate or an accumulation.
- Before processing: inspect the exact selected variable, displayed version, units, fill values, date range, and export header. Do not assume a portal export is identical to a raw product.
- Conversion decision: if the exported monthly mean rate is mm/hour, multiply by 24 and the calendar days in that month. If already accumulated, do not convert again.

Sources:
https://data.nasa.gov/dataset/gpm-imerg-final-precipitation-l3-1-month-0-1-degree-x-0-1-degree-v07-gpm-3imergm-at-ges-di-75e72
https://gpm.nasa.gov/data/imerg
https://disc.gsfc.nasa.gov/datasets/GPM_3IMERGM_07/summary

### Daily IMERG Final

- Product: GPM_3IMERGDF, version 07; daily, 0.1 degree grid.
- NASA documents `precipitation` in mm/day, derived from the mean of valid half-hourly rates multiplied by 24.
- `precipitation_cnt` records valid half-hourly samples; zero rainfall is a valid observation.
- DOI: https://doi.org/10.5067/GPM/IMERGDF/DAY/07
- Limitations include weaker performance in complex terrain, coastal areas, and frozen conditions, and possible long-term artefacts from changing satellite inputs.
- Do not multiply this daily variable by another 24. Retain the product's day convention for alignment.

Sources:
https://data.nasa.gov/dataset/gpm-imerg-final-precipitation-l3-1-day-0-1-degree-x-0-1-degree-v07-gpm-3imergdf-at-ges-dis-13ed8
https://disc.gsfc.nasa.gov/datasets/GPM_3IMERGDF_07/summary

## Primary aerosol optical depth

### Aqua MODIS Collection 6.1

- Monthly product: MYD08_M3; daily companion: MYD08_D3.
- Monthly product resolution: 1 degree by 1 degree; statistics derive from the daily product.
- Monthly combined 550 nm AOD scientific dataset: `AOD_550_Dark_Target_Deep_Blue_Combined_Mean_Mean`.
- Daily counterpart: `AOD_550_Dark_Target_Deep_Blue_Combined_Mean`.
- AOD is dimensionless. NASA describes the monthly statistic as a mean of daily means.
- Monthly DOI: https://doi.org/10.5067/MODIS/MYD08_M3.061
- NASA describes the combined field as joining Dark Target and Deep Blue land and ocean retrievals. For coastal analysis boxes, document the ocean component or agree on a land mask; a rectangle is not an administrative state boundary.
- NASA notes Level 3 inputs have passed the relevant quality selection; still inspect fill values, metadata and sampling. Giovanni may not contain the latest source version.
- AOD describes light extinction by the atmospheric particle column, not a direct surface PM2.5 measurement. Cloud-related missingness limits rainfall comparisons.

Sources:
https://ladsweb.modaps.eosdis.nasa.gov/missions-and-measurements/products/MYD08_M3
https://earth.gsfc.nasa.gov/climate/data/deep-blue/data

## Proposed scope from the team plan

These are proposals until checked with Aadharsh, not newly confirmed decisions.

| Setting | Proposal |
| --- | --- |
| Period | January 2003 to December 2024 |
| Monthly timestamps | 264 per series, including missing observations |
| IGP box W S E N | 76, 24, 88, 30 |
| TN box W S E N | 76.5, 8, 80.5, 13.5 |
| Seasons | JF, MAM, JJAS, OND |
| Primary products | IMERG Final V07 and Aqua MODIS C6.1 |
| Later checks | Separate Terra monthly and MERRA-2 series if needed |

## Access check

1. Create or sign into your own Earthdata account: https://urs.earthdata.nasa.gov/
2. Open Giovanni: https://giovanni.gsfc.nasa.gov/giovanni/
3. Check login works; authorise NASA GESDISC DATA ARCHIVE if prompted.
4. Find Time Series, Area-Averaged and search GPM_3IMERGM.
5. Record the available version, precipitation label, units, and available dates without assuming the documentation proves portal availability.
6. Search MYD08_M3 and confirm the combined 550 nm AOD statistic and collection.
7. During permitted project work, start with one short regional export. Inspect metadata before requesting the full period.

Giovanni guide: https://giovanni.gsfc.nasa.gov/giovanni/doc/UsersManualworkingdocument.docx.html

## Questions to resolve before a full download

- Has Aadharsh changed the proposed scope or already acquired data?
- Are the selected product and version available for the entire planned period?
- What are the exact Giovanni labels, identifiers, units, and fill values?
- Are the two boxes agreed, including coastal/ocean cells?
- Does the time series export include any quality information, or must it be acquired separately?
- What input format do Aadharsh's functions accept?

## Later data checks and handoff

Use the shared contract once agreed: date, region_id, variable, frequency, value, unit, source_id, valid_fraction, qc_flag.

Preserve originals and real zeros. Missing CSV values remain empty. Use YYYY-MM-01 for monthly dates. Check duplicates and complete date indexing. Record source, version, variable, box, period, units, service, filename and download time for each export.

Do not invent coverage: monthly AOD alone does not reveal the number of valid days. Derive temporal coverage from the daily series and distinguish it from spatial coverage. A valid regional daily value does not imply every cell was observed. Keep unknown coverage empty until measured.

Aadharsh independently reviews prepared files before statistical use. Sritharan owns data validation, anomaly and indicator implementation; Aadharsh owns trends, evidence and interaction. Neither member's findings should be written before running and validating real observations.
