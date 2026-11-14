# Adrian integration update — 14 November 2026

Base: `adrian-hue-pixel/TrendTrace` main at db1ede0a9440a0a693acc01c49d4110faddcd206, combined with Adrian's final source zip. This includes the latest teammate research uploads. Publication targets the authorized review branch adrian/core-api-ai; main merging, deployment and scientific approval remain separate.

## Completed here

- Integrated Adrian's core API, real loader, science adapter, AI checks/templates and report hook into current main.
- Preserved current lazy app creation, middleware/security headers, report admission, OpenAPI errors, fixed dependency lock and CI workflow.
- Reused the shared limiter for /explain and exposed its Retry-After semantics.
- Added research-qualified methods and report limitations from the two supplied documents; documented the scientific disagreements without changing frozen fields/enums.
- Validated optional CSV version/method metadata; preserved per-frequency coverage semantics and zero/null distinctions.
- Kept PDFs fast: reuse a guarded cached explanation or use a template immediately; do not start a paid provider call during PDF construction.
- Ran the entire integrated suite on actual CPython 3.11.18 with the existing pinned dependency constraints. Source/compile/dependency checks and local HTTP smoke checks pass.

## Input gaps that this update cannot replace

Aadarsh's PDF supplies a handbook, not executable functions or actual reference statistical results. Sritharan's deck reports observation processing and names a separate package; its embedded spreadsheets contain rounded aggregates, not the full source observations. We did not turn those into fabricated real API inputs.

To complete genuine integration, supply Sritharan's separately referenced full-precision results/code/provenance package and Aadarsh's importable trendlib functions plus genuine trend_results_reference.json/interaction/evidence outputs. Source IDs, season aliases, baseline eligibility, raw-p/q and seasonal aggregation questions remain owner decisions listed in docs/decisions.md. The existing code returns explicit unavailable responses where scientific outputs are absent.

The frontend build and deployed journey/host timing still require Group2/Karnish's running artifacts. The optional paid LLM provider has not been live-tested; automatic summaries work without a key. The existing GitHub workflow is preserved; the publication PR provides its remote check status.

## Applying the result

Use the full-repository zip, or apply the accompanying patch on a clean branch based on the stated main commit. Review changes before committing/pushing. Preserve your clone's .git and any later teammate changes; do not copy a virtual environment or private .env. The change manifest lists all source paths. No padding lines or empty commits were added to inflate GitHub statistics.

## Combined release review

Added focused regressions and targeted fixes for blank periods, leading-decimal AI numeric claims, in-flight explanation admission, selected-season PDF coverage and saved-report cleanup isolation. Karnish's report service/store are touched only by the last two fixes. Existing contracts and dependencies remain unchanged.

## Direct-main follow-up

PR #3 was merged to main at d4b2f636f9245bdbc6b20caf471daab957b71ba2 with its original authored commits intact. Adrian then explicitly authorized a direct-main follow-up: strengthen p-value/link guardrails and add missing-data/outage QA coverage. The normal daily CSV is unchanged. The additional 32,144 rows are generated MOCK test input; no science calculations or public schemas change. Current validation is recorded in release-verification.md.
