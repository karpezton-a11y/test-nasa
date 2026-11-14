# Changed files relative to main db1ede0

- `.env.example` — Clarify provider configuration; keep key values empty.
- `README.md` — Complete current setup, locked installs, research methods, AI disclosure and limitations.
- `backend/app/ai/client.py` — Integrate guarded explanations, ID resolution, shared quota handling and bounded PDF summary reuse.
- `backend/app/ai/context.py` — Integrate guarded explanations, ID resolution, shared quota handling and bounded PDF summary reuse.
- `backend/app/ai/facts.py` — Integrate guarded explanations, ID resolution, shared quota handling and bounded PDF summary reuse.
- `backend/app/ai/guardrails.py` — Integrate guarded explanations, ID resolution, shared quota handling and bounded PDF summary reuse.
- `backend/app/ai/report_summary.py` — Integrate guarded explanations, ID resolution, shared quota handling and bounded PDF summary reuse.
- `backend/app/ai/resolve.py` — Integrate guarded explanations, ID resolution, shared quota handling and bounded PDF summary reuse.
- `backend/app/ai/service.py` — Integrate guarded explanations, ID resolution, shared quota handling and bounded PDF summary reuse.
- `backend/app/ai/templates.py` — Integrate guarded explanations, ID resolution, shared quota handling and bounded PDF summary reuse.
- `backend/app/config.py` — Merge shared foundation additions while preserving current-main hardening.
- `backend/app/core_schemas.py` — Add request/composition models reusing the frozen scientific output models.
- `backend/app/errors.py` — Merge shared foundation additions while preserving current-main hardening.
- `backend/app/main.py` — Merge shared foundation additions while preserving current-main hardening.
- `backend/app/routers/core.py` — Register core endpoints and accurate contract error responses.
- `backend/app/schemas.py` — Merge shared foundation additions while preserving current-main hardening.
- `backend/app/services/core.py` — Add common validation/selection/comparison over the existing store.
- `backend/app/services/real_store.py` — Integrate cached validated real imports, version/method metadata and coverage rules.
- `backend/app/services/science.py` — Integrate thin Group3 adapter; no statistics or fabricated fallback outputs.
- `backend/app/services/validation.py` — Merge shared foundation additions while preserving current-main hardening.
- `backend/tests/test_adrian_ai.py` — Add core/real-loader/AI/reference/release regression coverage from Adrian’s implementation.
- `backend/tests/test_adrian_core.py` — Add core/real-loader/AI/reference/release regression coverage from Adrian’s implementation.
- `backend/tests/test_adrian_core_real.py` — Add core/real-loader/AI/reference/release regression coverage from Adrian’s implementation.
- `backend/tests/test_adrian_foundation.py` — Add core/real-loader/AI/reference/release regression coverage from Adrian’s implementation.
- `backend/tests/test_adrian_reference.py` — Add core/real-loader/AI/reference/release regression coverage from Adrian’s implementation.
- `backend/tests/test_adrian_release.py` — Add core/real-loader/AI/reference/release regression coverage from Adrian’s implementation.
- `backend/tests/test_report.py` — Update a previously absent-feature expectation while retaining fallback/error coverage.
- `backend/tests/test_report_hooks.py` — Update a previously absent-feature expectation while retaining fallback/error coverage.
- `backend/tests/test_research_integration.py` — Verify source-qualified methods and nonblocking/cached report summaries.
- `backend/tests/test_smoke_script.py` — Update a previously absent-feature expectation while retaining fallback/error coverage.
- `backend/tests/test_snapshot.py` — Update a previously absent-feature expectation while retaining fallback/error coverage.
- `docs/api-change-log.md` — Document contract, current integration, provisional decisions and team handoffs.
- `docs/contract.md` — Document contract, current integration, provisional decisions and team handoffs.
- `docs/decisions.md` — Document contract, current integration, provisional decisions and team handoffs.
- `docs/implementation/github-release.md` — Document contract, current integration, provisional decisions and team handoffs.
- `docs/implementation/integration-update.md` — Document contract, current integration, provisional decisions and team handoffs.
- `docs/implementation/phase-cd-integration.md` — Document contract, current integration, provisional decisions and team handoffs.
- `docs/implementation/pr-description.md` — Document contract, current integration, provisional decisions and team handoffs.
- `docs/implementation/real-data-layout.md` — Document contract, current integration, provisional decisions and team handoffs.
- `docs/implementation/reference-results.md` — Document contract, current integration, provisional decisions and team handoffs.
- `docs/implementation/release-verification.md` — Document contract, current integration, provisional decisions and team handoffs.
- `docs/methods.md` — Integrate documented processing protocols and caveats without claiming statistical validation.
- `docs/research/group3-handoff-review.md` — Record inspected source evidence, reported results and exact missing science-package inputs.
- `scripts/security_audit.py` — Provide reproducible redacted source/history credential checks.
- `scripts/smoke_test.py` — Add core checks and timing while preserving current strict download/guardrail/skip checks.

- `docs/implementation/changed-files.md` — List this delivery’s complete changed-file scope.

- `docs/research/source-manifest.json` — Record provided-source hashes and their non-dataset/non-code status.

No source files removed. Original scientific examples/mock data, CSV and advanced routes were preserved. Targeted report service/store fixes are listed below.
Runtime/application dependencies and requirements.lock were preserved. No empty commits, filler files or generated line padding added.

- `backend/app/reports/service.py` — Apply the same selected-season coverage gate as core analysis (Karnish module; targeted fix).
- `backend/app/reports/store.py` — Log cleanup scan failure without failing the saved report (Karnish module; targeted fix).
- `backend/tests/test_release_regressions.py` — Reproduce date, guardrail, concurrency, PDF coverage and cleanup failures.

## QA follow-up

- `scripts/generate_load_fixture.py` — Deterministically generate or verify full-period labelled MOCK daily input from the existing registry.
- `data/mock/qa_large/daily.csv` — 48,216 generated daily acceptance-test records; not application code or NASA observations.
- `data/mock/qa_large/manifest.json` — MOCK provenance, generator-registry checksum, series inventory and CSV checksum.
- `backend/tests/test_large_daily_csv.py` — Exercise existing API/export routes with large inputs, alternate sources, leap days and exact null/zero/float fidelity.
- `backend/tests/test_mock_generator.py` — Keep original generator comparison scoped to its scenarios; the QA fixture has independent deterministic checks.
- `README.md`, `docs/api-change-log.md`, `docs/decisions.md`, release verification and PR description — Disclose generated data and reproducible QA commands.

## Direct-main sparse QA and AI hardening follow-up

- `backend/app/ai/guardrails.py` — Check exact p-value relations and reject link/active-URI text, including normalized obfuscation.
- `backend/tests/test_adrian_text_guards.py` — Reproduce unsafe p-value/link claims and verify deterministic template fallback.
- `scripts/generate_load_fixture.py` — Share deterministic CSV generation across normal and sparse QA inputs.
- `data/mock/qa_large/sparse_daily.csv` — 32,144 generated MOCK missing-data/outage records; no scientific findings.
- `data/mock/qa_large/manifest.json` — Record sparse inventory/policy/checksum while retaining the previous normal checksum.
- `backend/tests/test_large_daily_csv.py` — Allow the test-only store to read either verified QA fixture.
- `backend/tests/test_sparse_daily_qa.py` — Verify nulls/zeros, CSV quality errors, outage chart gaps, missing-source behaviour, regeneration and production refusal.
- README, API log, decisions, current integration/release verification — Explain test commands, provenance and authorized publication scope.
