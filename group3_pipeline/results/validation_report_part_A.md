# Validation report Part A

Run: 2026-11-14T06:13:02.097691+00:00

Automated data checks executed. Independent scientific review remains pending.

| Region | Variable | Source | Frequency | Valid / expected | Missing % | Coverage known |
|---|---|---|---|---|---|---|
| IGP | aod | MODIS_AQUA_C61_DAILY | day | 7907/8036 | 1.61 | 0 |
| IGP | aod | MERRA2_MONTHLY_TOTEXTTAU | month | 264/264 | 0.00 | 0 |
| IGP | aod | MODIS_AQUA_C61_MONTHLY | month | 264/264 | 0.00 | 264 |
| IGP | aod | MODIS_TERRA_C61_MONTHLY | month | 264/264 | 0.00 | 0 |
| IGP | rainfall | IMERG_V07_FINAL_DAILY | day | 8036/8036 | 0.00 | 0 |
| IGP | rainfall | IMERG_V07_FINAL_MONTHLY | month | 264/264 | 0.00 | 264 |
| TN | aod | MODIS_AQUA_C61_DAILY | day | 7473/8036 | 7.01 | 0 |
| TN | aod | MERRA2_MONTHLY_TOTEXTTAU | month | 264/264 | 0.00 | 0 |
| TN | aod | MODIS_AQUA_C61_MONTHLY | month | 264/264 | 0.00 | 264 |
| TN | aod | MODIS_TERRA_C61_MONTHLY | month | 264/264 | 0.00 | 0 |
| TN | rainfall | IMERG_V07_FINAL_DAILY | day | 8036/8036 | 0.00 | 0 |
| TN | rainfall | IMERG_V07_FINAL_MONTHLY | month | 264/264 | 0.00 | 264 |

## Checks executed
- Exact date/value columns required by manifest.
- Duplicate source timestamps rejected.
- Units converted only through explicit rules.
- Missing timestamps indexed without filling values.
- Source metadata and SHA256 retained.
- Suspect observations excluded with counts and original values retained in provenance.

## Review still needed
- Confirm selected field, version, scale/offset and actual geographic mask.
- Review seasonal climatology and daily/monthly differences; no arbitrary discrepancy tolerance is imposed.
- Review low-coverage AOD flags and anomaly eligibility.
- Confirm P95, missing-day and minimum-baseline conventions with Aadarsh.
- Verify resulting files against Group 1 contract before integration.