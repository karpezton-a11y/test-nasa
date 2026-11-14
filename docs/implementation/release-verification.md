# Current integration verification — 14 November 2026

## Actual verification

- CPython **3.11.18**, installed in a temporary environment, with `pip install -r requirements-dev.txt -c requirements.lock`.
- Full integrated suite: **588 passed, 5 skipped (593 collected), in 19.72 s**. Includes current main's audits/conformance/security/report/smoke checks and Adrian's core, real-store, guarded AI, reference and research-integration checks.
- Local real Uvicorn process in dev/mock/no-key mode: **21/21 smoke checks passed**, 0 skipped, 0 failed. /analyze below2s locally; one-region PDF built in0.21s. Server terminated after the run. This is not an external host/real-science benchmark.
- Python compilation, `git diff --check` and `pip check` pass. Existing dependency lock/CI retained; no application dependency added.
- Credential scan covers current source and reachable Git history, redacts matched values, and reports no high-confidence credential patterns. The final source/file counts are included in the delivery's audit JSON. The scan is heuristic, not a declaration of vulnerability-free software.

## Five skipped tests

One core reference test: Group3 trend_results_reference.json has not been delivered. Four current-main real-data acceptance checks: actual processed files and their reference outputs have not been supplied. These skips are input gaps, not successful scientific validation.

The real loader and adapter were tested with isolated fixtures and fake Group3 functions. The complete reference/real-data acceptance tests will run when genuine inputs exist. They must fail on invalid data rather than fall back to mocks.

## Scientific documentation integrated

Source-qualified methods, exact stated product/SDS names, definitions and limitations are in docs/methods.md. docs/research/group3-handoff-review.md lists source hashes, page/slide evidence, reported versus verified observations, and remaining contract questions. The code's scientific outputs and examples were not rewritten using handbook illustration numbers or rounded slide aggregates.

## What remains external

Actual Group3 package/files/reference results and scientific sign-off; the frontend build and deployed integrated journey; deployment-host performance; a live optional provider/model call if enabled. Team meeting chairs and scientific approvals cannot be inferred from documents. Adrian authorized PR #3 publication and subsequently its merge to main, preserving both authored commits. This follow-up is explicitly authorized for a direct, normal push to main after tests. GitHub Actions provides remote CI status. Collaborator/protection settings, deployment and scientific approval remain separate; this update does not claim those were performed.

## Compatibility

Current main's CSV/advanced/mock/snapshot implementations are preserved. Two targeted report fixes align seasonal coverage and make cleanup scans best-effort; public report shapes are unchanged. Shared foundation integration and additive smoke checks are recorded in the API log. Four existing test expectations changed where planned feature absence or missing methods had become obsolete; missing-hook fallback is still explicitly tested. Existing main's P-1 approval and other decisions remain in the log.

The complete source zip omits .git, environments, secrets, raw downloads, caches and generated outputs. Historical verification reports from the previous zip are superseded by this current integration record; no previous Python3.14-only limitation is claimed for this build.

## Combined release regression checks

Thirteen focused regression cases pass: blank start/end across series/anomalies/CSV; trailing date newline; signed leading-decimal numeric claims; whole-generation explanation concurrency and release; season-specific report coverage; cleanup scan isolation. Before fixing, twelve cases failed and the trailing-newline case already passed through availability validation. The full suite passes after the fixes. Source compilation, dependency consistency and diff whitespace checks pass. No application dependency was added.

## Large-file QA follow-up

Added 48,216 deterministic generated MOCK rows (six daily series, 2003–2024) and 31 acceptance checks. The complete suite reports 526 passed and five genuine-input skips. Focused QA plus original-generator tests report 61 passed. The QA CSV/manifest are checked byte-for-byte against the separate generator; all parsed series validate, API windows and CSV preserve exact values/nulls/zeros, alternate-source selection is exercised, and production rejects the injected MOCK store. Existing application code and ordinary mock scenario files are unchanged in this follow-up. Generated records are test data, not manually authored code or scientific findings. GitHub may exclude them from contributor analytics.

## Direct-main sparse QA and AI guardrails follow-up

The sparse fixture adds 32,144 generated MOCK records alongside the unchanged 48,216-row normal CSV. Sixty-two new checks exercise daily quality errors/outages, source unavailability, generator tampering, production refusal, altered p-value operators/prose and links/active URI text. The 16 initial symbolic/link reproductions failed before the guardrail fix; the canonical template already passed. Unsafe provider output now falls back to the guarded template. Final local suite: 588 passed, 5 real-input skips in 19.72 s. Local Uvicorn smoke: 21/21 passed, no skips, PDF0.21 s. Compilation, diff checks and heuristic source/reachable-history credential scan pass (221 source files,342 historical blobs at scan time, no findings). No paid provider call or real-science certification was performed.

Generated data rows must be reported separately from application code. Passing tests does not establish that every possible bug is absent; real-data/reference sign-off and deployed frontend/host testing remain outstanding.
