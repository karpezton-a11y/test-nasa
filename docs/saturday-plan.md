# Saturday 14 Nov 2026: G1 Member 2 tickets (draft for the 19:15 planning block)

Built from the Group 1 DOCX schedule and Appendix A, adjusted to the current split (Karnish = G1 M2: advanced endpoints, reports, exports, delivery). Roster of 14 Nov: Adrian = G1 M1; Sritharan and Aadarsh = G3; Kavin and Sri Prasath = G2.

**Status after the Friday-evening session (branch `karnish/phase2-advanced-endpoints`):** S-03, S-04, S-05 and S-07 are built and tested on mock; S-10/S-11 hooks exist (they wait for Adrian's summary module and G3's `docs/methods.md`). Handoffs: `docs/handoff/`.
Times are IST. Re-check this list after the IM3 freeze (20:15) and adjust it to the frozen contract.

| ID | When | Ticket | Owner | Depends on | Done when |
|---|---|---|---|---|---|
| S-01 | 09:00 IM4 | Read the Local Lead's answer (P-1). Yes → merge PR #1. No → rebuild from it as a reference. **Done 14 Nov: approved (reported by Karnish); PR #2 and PR #1 merged. Adrian: please record the answer in `docs/decisions.md` row P-1.** | Karnish + Adrian | written answer | `main` has the backend |
| S-02 | 09:00–09:30 | Apply the IM3 frozen decisions (G-*, H-*, J-*, D-*) to `advanced_schemas.py`, `docs/examples/` and mock fixtures; bump `contract_version` only if a field changed | Karnish | IM3 outcome | `pytest` green; `docs/api-change-log.md` updated |
| S-03 | 09:30–11:00 | `GET /anomalies` (single + `both`, window slicing, `detrended`); errors `INVALID_*`, `INSUFFICIENT_DATA`, `DATA_NOT_AVAILABLE` | Karnish | S-02 | typed tests + examples match the wire |
| S-04 | 09:30–11:00 | `GET /interaction` (status `ok` / `too_few_events`, guardrail always present) | Karnish | S-02 | tests for 0, 9 and 10 used events |
| S-05 | 09:30–11:00 | `GET /rainfall/indicators` (`annual`/`JJAS`/`OND`, `INVALID_INDICATOR`) | Karnish | S-02 | 95%-valid null rule tested |
| S-06 | **11:00 H4** | Hand the mock API to G2: staging URL + `docs/examples/` + run instructions | Adrian (+ Karnish) | staging deploy | Kavin / Sri Prasath load `/regions` in the browser |
| S-07 | 11:00–12:30 | Add S-03…S-05 to `smoke_test.py`, `export_static_snapshot.py` and the CSV `what=anomalies` path (`variable=both` if agreed) | Karnish | S-03…S-05 | smoke test green locally |
| S-08 | 13:15–14:30 | Help Adrian wire `services/real_store.py` (`create_store`, `asset_statuses`) against G3's file format; run the format checks on G3's sample file | Adrian (+ Karnish) | G3 sample file | loader passes `verify_store` in `prod` |
| S-09 | **14:30 H5** | Real monthly series arrive → run with `DATA_MODE=real` locally; `smoke_test.py --expect-status real` | Adrian | H5 | real `/timeseries` + `/analyze` |
| S-10 | 16:00–18:30 | PDF: plug in Adrian's `/explain` output (`AiSummary` hook) and the real trend results; check the PDF numbers against `/analyze` | Karnish | `/explain` template | `test_report` + manual check |
| S-11 | **19:30 H7** | Wire G3's anomaly/evidence outputs and daily series into S-03…S-05; methods.md v1 into the PDF (`methods_text`) | Karnish | H7 | real anomalies served; methods placeholder gone |
| S-12 | 20:30–21:30 | Deploy rehearsal on real data (`APP_ENV=prod`, `DATA_MODE=real`, `DATA_VERSION` pin) → smoke test → phone check | Adrian (+ Karnish) | S-09 | public URL v0 passes the smoke test |
| S-13 | **21:30 IM6 gate** | Demo: region → real series → trend in the UI | All | S-12 | gate passed |

## Risks and fallbacks

- **H5 late:** keep staging on mock (labelled) and integrate whichever region is ready first (IGP).
- **H7 late:** ship the advanced endpoints on mock fixtures in staging only. In real mode they return `DATA_NOT_AVAILABLE` and the UI shows "being validated".
- **Deploy fails:** `python scripts/export_static_snapshot.py` → G2 serves `snapshot/` from GitHub Pages or Netlify.
- **Free host asleep at demo time:** open `/api/v1/health` one minute before.
