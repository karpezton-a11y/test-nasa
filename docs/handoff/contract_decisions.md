# Contract G–J: open decisions (none approved)

Every row is **OPEN** until the named sign-off person agrees in writing (chat or meeting notes).
The code implements the recommendation provisionally so the endpoints work; changing a decision means
changing the model, the examples, `docs/contract.md` and the tests together (and a `contract_version` bump
after the freeze).

Sign-off owners (roster of 14 Nov): **Adrian** = shared schemas, errors, A–F compatibility ·
**Sritharan** = anomaly/indicator definitions, units, thresholds · **Aadarsh** = interaction and statistics ·
**Kavin** = Anomaly Radar and report fields · **Sri Prasath** = Interaction screen and download fields.
Deadlines: interface items at IM4 (Sat 09:00) if IM3 did not settle them; science items at H7 (Sat 19:30)
or H9 (Sun 11:00).

| ID | Question | Options | Recommendation (implemented provisionally) | Sign-off | Deadline | Status |
|---|---|---|---|---|---|---|
| D-01 | Do errors carry `data_status`/`data_version`? | bare `{"error":{…}}` · envelope | bare shape everywhere | Adrian | IM4 Sat 09:00 | OPEN |
| D-02 | Extra codes `VALIDATION_ERROR` 422, `NOT_FOUND` 404, `METHOD_NOT_ALLOWED` 405, `PAYLOAD_TOO_LARGE` 413, `INVALID_EXPORT_TYPE` 400, `INVALID_INDICATOR` 400, `INVALID_REPORT_ID` 400, `REPORT_NOT_FOUND` 404, `HTTP_ERROR`, `RATE_LIMITED` 429 | adopt all · subset | adopt all | Adrian | IM4 Sat 09:00 | OPEN |
| D-03 | When does `/explain` return `AI_UNAVAILABLE`? | any LLM failure · only if the template fails too | only if the template fails | Adrian | IM4 Sat 09:00 | OPEN |
| D-04 | Which trendlib exceptions map to `INSUFFICIENT_DATA`? | all · named data exceptions only | named ones only; others `INTERNAL_ERROR` | Adrian + Aadarsh | H7 Sat 19:30 | OPEN |
| G-1 | Shape of `variable=both` | wrapper `{results:[rain, aod], combined_flags}` · flat list | wrapper | Adrian + Kavin | IM4 Sat 09:00 | OPEN |
| G-2 | Meaning of "minimum 10 years" for anomalies | ≥10 valid baseline values per calendar month · window ≥10 years | baseline rule; the window may be shorter | Sritharan | H7 Sat 19:30 | OPEN |
| G-3 | All months or flagged months in `anomalies[]` | all · flagged only | all months (Radar heatmap) | Kavin | IM4 Sat 09:00 | OPEN |
| G-4 | Statistic per variable | rainfall percentile 0.90/0.10 + min valid 0.9; AOD z-log ±2 · one statistic | per G3 §9 as listed | Sritharan | H7 Sat 19:30 | OPEN |
| G-5 | Dry-flag suppression threshold | 10 mm/month · other | 10 mm/month | Sritharan | H7 Sat 19:30 | OPEN |
| G-6 | Threshold edges and percentile formula | inclusive · strict; formula named by G3 | inclusive; G3 names the formula | Sritharan | H7 Sat 19:30 | OPEN |
| G-7 | Meaning of `unusual_combination` | any other both-flagged pair · drop it | any other both-flagged pair | Sritharan | H7 Sat 19:30 | OPEN |
| G-8 | Added G fields (`result_id`, `unit`, `period`, `qc_flag`, threshold extras, combined categories) | accept · trim | accept | Adrian + Kavin | IM4 Sat 09:00 | OPEN |
| G-9 | `start`/`end` optional on `/anomalies`? | optional, default `period_available` · required | optional (same rule as `/export/csv`) | Kavin | IM4 Sat 09:00 | OPEN (new) |
| H-1 | Fewer than 10 used events | 200 + `status: too_few_events` + note · error | 200 + status + note | Aadarsh + Sri Prasath | IM4 Sat 09:00 | OPEN |
| H-2 | Fields kept when there are too few events | keep descriptive + monthly association, null CI/p · null all | keep descriptive | Aadarsh | H9 Sun 11:00 | OPEN |
| H-3 | Control size and % denominator | `n_events_used × 5`, `n_events × window_days` · G3 alternative | as listed | Aadarsh | H9 Sun 11:00 | OPEN |
| H-4 | Added H fields (`result_id`, `period`, `source_ids`, `status`, `note`, `ci_level`, `ci_method`, event-definition extras) | accept · trim | accept | Adrian + Sri Prasath | IM4 Sat 09:00 | OPEN |
| H-5 | Event-composite curve for the Interaction screen | G3 adds `composite[]` · before/after summary only | summary only for MVP | Sri Prasath + Aadarsh | IM4 Sat 09:00 | OPEN |
| H-6 | `/interaction` before H9 in real mode | `DATA_NOT_AVAILABLE` + "being validated" UI · hide the screen | 404 + UI text | Sri Prasath | IM4 Sat 09:00 | OPEN |
| H-7 | Season parameter on `/interaction`; seasons without results | required, MAM/JF → `DATA_NOT_AVAILABLE` · default `all` · drop MAM/JF from the enum | required; unavailable seasons return 404 | Aadarsh + Sri Prasath | IM4 Sat 09:00 | OPEN (new) |
| J-1 | Indicator section placement, units, seasonal denominator | section J, `%`, days in that season · fraction | as listed | Sritharan | H7 Sat 19:30 | OPEN |
| J-2 | TrendResult extension for annual indicators (`season: "annual"`, `series_type`, slope units, year counts) | extend E/F · separate object | extend E/F | Adrian + Aadarsh | IM4 Sat 09:00 | OPEN |
| J-3 | No indicator trend below 10 valid years | `trend: null` + `trend_note` · error | null + note | Aadarsh | H7 Sat 19:30 | OPEN |
| J-4 | Indicator parameters all required (no default season)? | all required · default `annual` | all required | Kavin | IM4 Sat 09:00 | OPEN (new) |
| C-1 | CSV layout (nested trend fields as JSON cells, `#` escaping, decoder) | accept · flatten | accept | Adrian | IM4 Sat 09:00 | OPEN |
| C-2 | 70% coverage gate on the CSV series export | gate · no gate | gate on CSV only | Adrian | IM4 Sat 09:00 | OPEN |
| C-3 | `what=anomalies&variable=both` in CSV | add · single variable only | single only (MVP) | Kavin | IM4 Sat 09:00 | OPEN (new) |
| R-1 | Mock PDF footer wording | mock footer · DOCX footer | mock footer while data is mock | Aadarsh | IM4 Sat 09:00 | OPEN |
| R-2 | Regions per report | one `region_id` · `region_ids[]` | one (MVP) | Kavin | IM4 Sat 09:00 | OPEN |
| R-3 | Requested section without data, or computed for other dates | "Not available" box · fail the report | box with reason | Kavin | IM4 Sat 09:00 | OPEN |
| R-4 | Trend line/band in charts | G3 supplies fitted values · slope as text | text now | Aadarsh + Kavin | H9 Sun 11:00 | OPEN |
| R-5 | Reports lost on host restart (ephemeral disk) | accept, UI re-creates · persistent store | accept | Sri Prasath | IM4 Sat 09:00 | OPEN |
| R-6 | Real-mode PDF before the H9 text arrives | build with honest "not available yet" boxes and refuse any mock/placeholder text · refuse the whole PDF until H9 | boxes + refuse placeholders | Aadarsh + Kavin | IM4 Sat 09:00 | OPEN (new) |
| R-7 | AI summary hook for the PDF | in-process `app.ai.report_summary.summarize(results) -> (text, source)` · call `/explain` over HTTP | in-process hook | Adrian | IM4 Sat 09:00 | OPEN (new) |
| DS-1 | `DATA_MODE=real` without Adrian's loader | dev: stub that answers `DATA_NOT_AVAILABLE`, prod: refuse · refuse in both | as listed | Adrian | IM4 Sat 09:00 | OPEN (new) |
| DS-2 | Real file layout and reference-result files for the acceptance tests | per [real_data_dropin.md](real_data_dropin.md) · Adrian's own layout | Adrian decides the loader; G3 supplies `reference/*.json` | Adrian + Sritharan + Aadarsh | H5 Sat 14:30 | OPEN (new) |
| M-1 | Rainfall units per frequency in `/variables` | monthly in `unit`, daily in `caveat` · `units_by_frequency` | as implemented | Adrian + Sritharan | IM4 Sat 09:00 | OPEN |
| M-2 | Nullable `doi`, `access_date`, `citation` | nullable · required | nullable | Sritharan | IM4 Sat 09:00 | OPEN |
| M-3 | GeoJSON feature shape | `id = region_id`, always `{regions, geojson}` | as stated | Kavin + Sri Prasath | IM4 Sat 09:00 | OPEN |
