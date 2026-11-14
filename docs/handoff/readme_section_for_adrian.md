# README-ready text for Adrian (paste where you want; edit freely)

Karnish does not edit `README.md`. Below are the parts covering Karnish's endpoints, data modes, tests,
deployment and fallback. Commands are for zsh/bash (macOS/Linux); Windows variants are in comments.

---

## Run the backend locally

```bash
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env               # Windows: copy .env.example .env
python scripts/generate_mock_data.py
uvicorn app.main:app --app-dir backend --port 8000
```

Open http://127.0.0.1:8000/docs (interactive API docs). `/` itself returns `NOT_FOUND` by design.

## Data modes

| `APP_ENV` | `DATA_MODE` | What happens |
|---|---|---|
| `dev` | `mock` | Serves `data/mock/<MOCK_SCENARIO>/` (`normal`, `sparse` ≈ 40% missing, `short` < 10 years). Every response says `data_status: "mock"`; the PDF and CSV are labelled MOCK. |
| `dev` | `real` | Uses `backend/app/services/real_store.py` (Adrian's loader) on Group 3's `data/processed/`. Without the loader, every data route returns `DATA_NOT_AVAILABLE` (never mock data). |
| `prod` | `real` | Public deployment. Refuses to start unless every loaded file is labelled `data_status: "real"`; set `DATA_VERSION` to pin the release. |
| `prod` | `mock` | **Refused at startup** by design. |

## Endpoints (Karnish)

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/health` | liveness, `data_status`, `data_version`, `trendlib_version`, `ai_available` |
| `GET /api/v1/variables`, `/regions`, `/meta/sources` | metadata, region boxes (+GeoJSON), dataset provenance |
| `GET /api/v1/anomalies?region_id&variable=rainfall\|aod\|both&start&end&detrended` | unusual months vs the same calendar month in the 2003–2024 baseline |
| `GET /api/v1/interaction?region_id&season=all\|JF\|MAM\|JJAS\|OND` | AOD before/after heavy-rain events + monthly association (association only) |
| `GET /api/v1/rainfall/indicators?region_id&indicator&season=annual\|JJAS\|OND` | heavy-rain share, longest dry spell, Rx5day per year + trend |
| `GET /api/v1/export/csv?region_id&variable&what=series\|trend\|anomalies` | the exact numbers as CSV (`#` metadata lines; `pandas.read_csv(path, comment="#")`) |
| `POST /api/v1/report`, `GET /api/v1/report/{id}` | PDF Discovery Report |

Contract: `docs/contract.md` (G–J) · examples: `docs/examples/` · open decisions:
`docs/handoff/contract_decisions.md` · frontend guide: `docs/handoff/frontend_endpoints.md`.

Decode a CSV with special characters exactly: `python scripts/decode_csv.py file.csv` (or `--json`).

## Tests

```bash
python -m pytest
```

`backend/tests/test_real_data_acceptance.py` is skipped until `services/real_store.py` and `data/processed/`
exist; then it checks dates, units, sources, provenance and Group 3's reference results.

## Deploy (Render, free tier)

See `docs/deploy.md`. Staging (mock, labelled) uses `render.yaml` as it is. After a deploy:

```bash
python scripts/smoke_test.py https://<service>.onrender.com --expect-status mock
```

For real data use `--expect-status real` (add `--allow-unavailable` until Group 3's H7/H9 results exist).

## Fallback if the live API fails

```bash
python scripts/export_static_snapshot.py --require-real
```

This writes `snapshot/` (saved API responses, CSVs, one PDF per region, `manifest.json`); host it next to the
frontend build. If PDF creation fails, the app offers the printable report page and the CSV download.

## Data and honesty rules

Missing values are `null` / empty CSV cells, never 0. The backend serves Group 3's computed results unchanged
(no unit conversion, gap filling or smoothing). The evidence label is a team rule, not an official NASA score.
Interaction results are associations only. AOD is a column optical measure, not ground-level PM2.5.
Results are computed from NASA data by the TrendTrace team; this is not an official NASA product.
