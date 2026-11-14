# Deploy guide (Render free tier) — about 15 minutes

## What was checked (Fri 13 Nov 2026, official Render docs)

- render.com/docs/free: free web services **spin down after 15 minutes without traffic**; the next request takes **about one minute** to spin up; **750 free instance hours per workspace per month**; the **filesystem is ephemeral** (lost on redeploy, restart or spin-down; no persistent disk). RAM/CPU for free instances are not stated on that page.
- render.com/docs/python-version: the default Python for new services is 3.14, so this repo pins it with `.python-version` (`3.11`). The `PYTHON_VERSION` env var (fully qualified, e.g. `3.11.16`) would take precedence if set.
- render.com/docs/blueprint-spec: field names used in `render.yaml` (`runtime: python`, `plan: free`, `region: singapore`, `healthCheckPath`, `autoDeployTrigger`, `envVars` with `sync: false`).

Consequences for us:

- Saved PDF reports disappear on restart or spin-down. The UI should simply create the report again (`REPORT_NOT_FOUND`, decision R-5).
- PDF limits (audit M1): at most 2 PDFs at once (`REPORT_BUSY` 503), 10 per client per minute (`RATE_LIMITED` 429),
  and every save deletes reports older than 1 hour or beyond the newest 200. The rate limit keys on the connecting
  address; behind Render's proxy that may be the proxy itself, so it can act as one shared limit. That is safe (the
  2-at-once cap protects memory), and the start command is deliberately unchanged: trusting `X-Forwarded-For`
  would let anyone fake their address.
- Before a demo, open `/api/v1/health` about a minute early to wake the service.

## Plan: staging today, production after real data (decision DEP-1)

| When | APP_ENV | DATA_MODE | Data | Purpose |
|---|---|---|---|---|
| Fri/Sat rehearsal (now) | `dev` | `mock` | `data/mock/` (MOCK-labelled) | Staging rehearsal; Group 2 integration |
| After H5 (Sat 14:30) + Member 1's loader | `prod` | `real` | Group 3's `data/processed/` | Public URL for judges |

The startup guard **refuses** `APP_ENV=prod` with `DATA_MODE=mock`, and in `prod` it also refuses any loaded asset that is not labelled real. Never weaken it to make a deploy pass; staging uses `dev`. Debug is always off (`debug=False`), and CORS allows only `ALLOWED_ORIGIN`.

## Staging status

| Field | Value |
|---|---|
| URL | https://trendtrace-api-staging.onrender.com (API docs at `/docs`) |
| Deployed | Fri 13 Nov 2026, 19:33 IST, Blueprint `trendtrace-staging`, service `trendtrace-api-staging` (free, Singapore) |
| Branch / commit | `g1m2/backend-foundations` @ `47dde8d`; auto-deploys on every push to this branch |
| Mode | `APP_ENV=dev`, `DATA_MODE=mock`, `data_version` `MOCK-2026-11-13-normal` |
| `ALLOWED_ORIGIN` | `http://localhost:5173` (placeholder until Group 2 sends the frontend origin; change in Render → Settings → Environment) |
| `LLM_API_KEY` | empty (`ai_available: false`) |
| Smoke test | 12/12 passed at 19:34 IST; `POST /report` 4.3 s, every other check under 0.3 s |

## Steps

1. Decision P-1 is settled: the Local Lead approved using the Friday code (reported by Karnish, Sat 14 Nov 2026),
   so the backend is merged into `main`. Staging still deploys from `g1m2/backend-foundations`; for production,
   point the Render service at `main`.
2. Sign in at dashboard.render.com (owner: whoever holds the team account; an adult may need to own it).
3. **New → Blueprint**, connect GitHub repo `adrian-hue-pixel/TrendTrace`, pick the branch, and Render reads `render.yaml`.
4. When prompted for `sync: false` variables:
   - `ALLOWED_ORIGIN`: the frontend's origin (e.g. `https://<frontend>.netlify.app`). Use one origin and no `*`,
     exactly as the browser sends it: no trailing `/`, no path, no list (the app refuses to start otherwise). If the frontend is later served by the same FastAPI app, set it to the service's own URL.
   - `LLM_API_KEY`: leave empty today (template explanations; `ai_available: false`).
5. Click **Deploy Blueprint**. Build = `pip install -r requirements.txt -c requirements.lock` (every sub-dependency
   pinned to the tested version; `pip-audit -r requirements.lock --no-deps --disable-pip` found no known
   vulnerabilities on 2026-11-14); start = `uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT`.
6. When the deploy is live, run from your laptop:

   ```bash
   python scripts/smoke_test.py https://<service>.onrender.com --expect-status mock
   ```

   Expect `18/18 checks passed, 0 skipped, 0 failed` (health, metadata, `/anomalies`, `/interaction` ×2 each with
   the guardrail, `/rainfall/indicators` + `INVALID_INDICATOR`, CSV ×3 + error, PDF create + download (must start
   with `%PDF-`) + error). The first line includes the cold start.
   The 12/12 result in the table above predates the three advanced endpoints.
7. Post the URL in the team chat, labelled **STAGING / MOCK DATA**.

## Environment variables

| Key | Staging value | Production value | Notes |
|---|---|---|---|
| `APP_NAME` | (unset → TrendTrace) | final name | display name, one place only |
| `APP_ENV` | `dev` | `prod` | |
| `DATA_MODE` | `mock` | `real` | |
| `MOCK_SCENARIO` | `normal` | (ignored) | `sparse` / `short` for error-state demos |
| `DATA_VERSION` | (empty) | G3's version, e.g. `2026-11-14a` | startup fails if loaded data differs |
| `CONTRACT_VERSION` | `1.0` | `1.0` | bump only after an agreed change |
| `ALLOWED_ORIGIN` | frontend origin | frontend origin | single origin |
| `LOG_LEVEL` | `INFO` | `INFO` | |
| `REPORTS_DIR` | `reports` | `reports` | ephemeral on Render |
| `MAX_BODY_BYTES` | `65536` | `65536` | |
| `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY` | empty | Adrian decides | keys only in host env vars |
| `PORT` | set by Render | set by Render | passed to `--port` |

## Switch to production (Saturday, after H5/H6)

Render builds from git, so Group 3's files must be **committed** in `data/processed/` (the folder is tracked;
only `data/raw/` is ignored). Keep them small (regional series and results, not gridded NASA files).

1. Group 3's files are in `data/processed/` (layout: [handoff/real_data_dropin.md](handoff/real_data_dropin.md)), and Adrian's `backend/app/services/real_store.py` (`create_store(settings)`) attests `data_status: "real"` for every loaded asset.
2. Locally: `APP_ENV=prod DATA_MODE=real DATA_VERSION=<v> uvicorn app.main:app --app-dir backend --port 8000`, then
   `python -m pytest backend/tests/test_real_data_acceptance.py` and
   `python scripts/smoke_test.py http://localhost:8000 --expect-status real --allow-unavailable`
   (`--allow-unavailable` marks `DATA_NOT_AVAILABLE` from the advanced endpoints as **SKIP** until H7/H9 and
   prints a warning; a missing route still fails. Drop it after H9 so they are really checked).
3. On Render: change `APP_ENV=prod`, `DATA_MODE=real`, `DATA_VERSION=<v>`; redeploy; run the same smoke test against the URL.

What happens on misconfiguration (checked by tests):

| Setting | Result |
|---|---|
| `APP_ENV=prod` + `DATA_MODE=mock` | refuses to start |
| `APP_ENV=prod` + `DATA_MODE=real`, loader missing | refuses to start |
| `APP_ENV=prod` + any loaded asset not labelled real | refuses to start |
| `APP_ENV=dev` + `DATA_MODE=real`, loader missing | starts; every data route returns `DATA_NOT_AVAILABLE` (stub, never mock); `/health` shows `data_version: REAL-DATA-NOT-LOADED` |
| `DATA_VERSION` pin differs from the loaded data | refuses to start |

## Fallback: static snapshot (if hosting fails)

```bash
python scripts/export_static_snapshot.py                 # staging / rehearsal (mock allowed, labelled)
python scripts/export_static_snapshot.py --require-real  # the judged fallback: refuses mock data, writes nothing
```

Exit codes: `0` written; `1` some request failed with an error other than "not available" (a 500, a failed
PDF): every failure is printed and the previous `snapshot/` is kept unchanged; `2` refused (`--require-real`
on non-real data). The new snapshot is built in a staging folder and replaces the old one only when complete.

This writes `snapshot/` (git-ignored): every supported selection of `/variables`, `/regions`, `/meta/sources`,
`/anomalies` (rainfall, aod, both), `/interaction` (5 seasons), `/rainfall/indicators` (3 × 3), CSV exports,
Adrian's `/timeseries` once it exists, and one sample PDF per region. `manifest.json` has `files` (URL → file),
`unavailable` (URL → error code) and `selections` (what the UI may offer). It works from any static host with
no backend (tested). Group 2 serves it next to the built frontend (GitHub Pages or Netlify); reading rules:
[handoff/frontend_endpoints.md](handoff/frontend_endpoints.md#static-fallback-if-the-backend-is-down).

If only the PDF fails (`REPORT_FAILED`), the UI offers the printable report page and the CSV download; CSV
export does not import the PDF stack (tested).

## Railway alternative

`Procfile` has the same start command. Railway was not checked today; verify its current free-tier terms before using it.
