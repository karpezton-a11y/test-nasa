# Real data: what to drop where (Sritharan, Aadarsh; loader by Adrian)

Names come from the Group 1 DOCX §5.1/§6 and contract G–J. **Adrian's loader decides the final layout**
(decision DS-2); until he confirms, deliver the files below. Everything goes in `data/processed/` (never in
`data/mock/`), and every file says `data_status: "real"` and a `data_version` such as `2026-11-14a`
(never starting with `MOCK`). Production refuses to start if any loaded file is not labelled real.

| Deliverable (owner, handoff) | File (DOCX name) | Served by | Must contain |
|---|---|---|---|
| Regions, variables, sources (Sritharan, H2/H5) | `regions.geojson`, `variables.json`, `sources.json` | `/regions`, `/variables`, `/meta/sources` | contract B/C; real DOIs, access dates, citations |
| Monthly series (Sritharan, H5 Sat 14:30) | `timeseries_monthly.csv` | CSV, PDF, Adrian's `/timeseries` | `date,region_id,variable,frequency,value,unit,source_id,valid_fraction,qc_flag`; dates `YYYY-MM-01`; units `mm/month`, `1`; missing = empty cell; `valid_fraction` = share of the month's days with a valid retrieval (always a number, also when the value is empty: `0` when no day was valid) |
| Daily series (Sritharan, H7 Sat 19:30) | `timeseries_daily.csv` | daily CSV, interaction inputs | same columns; dates `YYYY-MM-DD`; units `mm/day`, `1`; `valid_fraction` empty (one day has no fraction; `qc_flag` says `ok`/`missing`) |
| Anomalies (Sritharan via `compute_anomalies`, H7) | stored results or computed by the loader | `/anomalies` | contract G per region × `rainfall`/`aod`/`both` × raw/detrended, full 2003-01..2024-12 (the API slices) |
| Rainfall indicators (Sritharan, H7/H9) | `rainfall_indicators_annual.csv` + definitions | `/rainfall/indicators` | contract J per region × indicator × `annual`/`JJAS`/`OND`; years with `valid_fraction < 0.95` empty; units `%`/`days`/`mm` |
| Interaction (Aadarsh, H9 Sun 11:00) | `interaction_summary.json` | `/interaction` | contract H per region × season; guardrail text exactly as in the contract |
| Methods + limitations text (Aadarsh/Sritharan, H9) | `docs/methods.md` | PDF sections 6–7 | Markdown; limitations as `- ` bullets under `## Limitations`; no "TODO"/"placeholder" wording |
| Reference results (Aadarsh, H9) | `data/processed/reference/<name>.json` | acceptance test | `{"endpoint": "/anomalies" \| "/interaction" \| "/rainfall/indicators", "params": {...}, "result": {...}}`; compared within 1e-6; `null` must stay `null` |

Checks that run automatically once the files and Adrian's `real_store.py` exist
(`python -m pytest backend/tests/test_real_data_acceptance.py`):

- monthly dates `YYYY-MM-01`; units per variable and frequency
- every `source_id` (series, anomalies, interaction `source_ids`, indicators, nested trends) is in `/meta/sources`
- `valid_fraction` in [0, 1] or null; `qc_flag` in `ok | low_coverage | missing | suspect`
- every envelope has `data_status: "real"` and a non-mock `data_version`; no `MOCK` text in any result
- the store attests only real assets in prod
- live endpoint results equal the reference files within 1e-6
