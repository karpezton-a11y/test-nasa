# Real data integration (Phases A–B)

[PROVISIONAL] DS-03 / DS-04, owner Adrian; Sritharan and Aadarsh confirm before H5/H7.
Public A–J response fields are unchanged. No science is computed by this loader.

## Startup inputs

All files live under `PROCESSED_DIR` (default `data/processed/`). The loader reads them once when the existing app starts. Restart after a Group 3 data release. Missing optional files raise DATA_NOT_AVAILABLE when requested. Empty dev real mode starts without mock fallback; production requires variables, regions, sources and monthly CSV. Corrupt/mixed-version/mock-labelled loaded inputs fail startup in every environment.

- `variables.json`: existing envelope, result is list[VariableInfo].
- `regions.geojson`: existing envelope, result is `{regions: [...], geojson: FeatureCollection}` (the existing RegionsResult). This preserves the API's region metadata and polygon shapes together.
- `sources.json`: existing envelope, result is list[SourceInfo].
- `timeseries_monthly.csv`, optional `timeseries_daily.csv`: exactly `date,region_id,variable,frequency,value,unit,source_id,valid_fraction,qc_flag` (column order need not match). Optional data_version and method metadata columns are accepted: version values must match the manifest and methods must be nonempty. They are retained internally, not added to the public response. Empty cells only for nullable fields. Dates explicit ISO day strings; monthly first day only. Source IDs must appear in variables and sources, region/variable combinations must be allowed. Duplicate/out-of-order points are rejected. Units are mm/month, mm/day or 1. No conversions. Monthly valid_fraction must be numeric temporal availability; daily valid_fraction remains empty/null because spatial fractions were not exported. Identifiers retain strings such as NA rather than being parsed as missing.
- `manifest.json`: CSV provenance; group-wide versions must match every loaded JSON envelope. Group 3 computes the file hashes **after** exporting the CSV. Hash checks bind the provenance statement to the bytes that were actually loaded; they do not independently verify scientific authenticity.

```json
{
  "data_status": "real",
  "data_version": "<Group 3 export version>",
  "contract_version": "1.0",
  "assets": {
    "timeseries_monthly.csv": {
      "data_status": "real",
      "sha256": "<64-character SHA-256 of this CSV>"
    }
  }
}
```

Every JSON file uses `{data_status,data_version,contract_version,generated_at,result}`. generated_at is a timezone-aware ISO timestamp. Never reuse mock JSON by merely changing its data_status. No mock marker is accepted anywhere in loaded input content.

## Later result files (optional until H7/H9)

- `anomalies/*.json`: enveloped AnomalyResult or AnomalyBothResult. Full stored results are sliced, never recomputed. Each file's variable field selects its model, not a request-supplied path.
- `interaction_summary.json`: enveloped list[InteractionResult]; alternatively `interaction/*.json` with one enveloped result each. Seasons without a result return DATA_NOT_AVAILABLE.
- `indicators/*.json`: one enveloped IndicatorResult each; alternatively `rainfall_indicators_annual.csv` with columns `region_id,indicator,season,year,value,valid_fraction` plus enveloped list[IndicatorResult] in `rainfall_indicators_metadata.json`. Metadata carries Group 3 definitions, periods and optional computed trends; its values must exactly match CSV rows. A CSV alone cannot supply the required scientific definitions. Duplicate result selections are rejected.
- Live store.trend always uses the science adapter, so reports and /analyze share one path. Unused standalone trend/*.json loading was removed in Phase E; reference files are test inputs, not a substitute science implementation.
- `reference/*.json` and `trend_results_reference.json`: validation inputs for tests, not a replacement for the live science implementation.

## Science boundary

`services/science.py` calls `trendlib.compute_trend(frame, season=..., alpha=...)` and, when available, `compute_evidence(frame, result, sensitivity=True)`. Frame columns: date/value/valid_fraction/qc_flag; frame.attrs carries region_id, variable, source_id, unit, frequency and requested period. G3 confirms this adapter payload (SCI-01).

Only G3's named InsufficientDataError/DataQualityError classes map to INSUFFICIENT_DATA (SCI-02). Programming and output-contract errors propagate to the existing INTERNAL_ERROR handler. Missing trendlib yields DATA_NOT_AVAILABLE and a server log. No package is created under analysis/ to pretend that trendlib exists.

Existing mock fixtures are returned through the adapter's explicit mock_lookup path. No real call ever uses this path. RealStore caches successful analyses with hashable keys including period, season, alpha and options; every caller receives a deep copy.

Before H7: if compute_trend already includes schema-valid evidence, preserve it. Otherwise evidence absence yields DATA_NOT_AVAILABLE (SCI-03). This explicitly leaves the H6 evidence fallback decision open instead of fabricating a score or adding not_assessed to the frozen enum. exclude_low_coverage=True is also pending the G3 signature agreement (SCI-04).
