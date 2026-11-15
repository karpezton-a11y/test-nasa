# TrendTrace – repository structure

```
TrendTrace/
├── README.md                 Animated showcase + challenge mapping + technical docs
├── LICENSE                   Apache-2.0
├── STRUCTURE.md              This file
├── Procfile / render.yaml    Render deployment (FastAPI)
├── requirements*.txt/.lock   Python dependencies
├── pytest.ini                Test config (665 tests)
├── .env.example              Env var names only – real keys go in Render, never in git
├── .github/workflows/        tests.yml (CI), fetch-nasa-data.yml
│
├── backend/
│   ├── app/
│   │   ├── main.py           FastAPI app, GZip, routers
│   │   ├── routers/          HTTP endpoints
│   │   ├── services/         Stats engine glue, real data store, demos, CSV, validation
│   │   ├── ai/               Groq client, guardrails, repair, templates, report summary
│   │   └── *_schemas.py      Pydantic request/response contracts
│   └── tests/                API, guardrail, landing-page, regression tests
│
├── analysis/                 Trend statistics library (Mann-Kendall, Theil-Sen, OLS, FDR…)
├── frontend/                 No-build site: index.html, app.js, style.css
│   ├── globe.js, rocket.js, mascot.js, fx.js, guide.js   3D globe, rocket, Trace, effects
│   ├── vendor/               Vendored three.js
│   └── data/                 Country shapes + globe snapshot
│
├── data/
│   ├── processed/            Real NASA-derived series used by the app
│   ├── raw/ catalog/ research/ mock/
├── scripts/                  Data builders (build_real_data.py, NASA POWER fetch…), smoke tests
├── group3_pipeline/          Earlier pipeline work (Group 3)
├── reports/  research data/  Sample reports and research inputs
└── docs/
    ├── readme/               Animated README assets (SVGs + tour.gif)
    ├── methods.md, contract.md, decisions.md, api-change-log.md, deploy.md
    └── research/ implementation/ handoff/ examples/
```
