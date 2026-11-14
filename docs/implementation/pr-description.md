## Core science API, guarded explanations and backend integration

Adds Adrian's `/timeseries`, `/analyze`, `/compare` and `/explain` to Karnish's existing FastAPI app, so selected API, CSV and PDF results share the same store. Includes the real-data loader, thin Group 3 adapter, guarded optional AI with automatic summaries, contract A–F and the revised README. No statistics, unit conversion or gap filling are implemented by the backend.

The combined release review also fixes blank date handling across shared routes, leading-decimal numeric guardrail bypasses, explanation concurrency admission, season-specific PDF coverage and report-cleanup error isolation. New regression tests reproduce those failures before their fixes.

Preserves Karnish's authorship, advanced response shapes, dependency lock, CI, existing mock fixtures, CSV encoding, report modules and deployment/fallback setup. Changes to report service/store are small targeted fixes, recorded in the change log. Latest teammate research uploads are included from main without modification.

Validation: Python 3.11.18 full suite and local HTTP smoke results are recorded in docs/implementation/release-verification.md. Tests use fake science/provider implementations; no paid LLM or NASA data requests were made. Source/reachable-history credential scan is heuristic, not a vulnerability-free guarantee.

Remaining handoffs: Group 3's genuine full-precision observations/provenance, importable trendlib and reference outputs; scientific sign-off; Group 2's integrated build; deployment-host timing. Research PDF/PPTX content is documented with source qualifications, not substituted for real inputs. No filler files, empty commits or attribution rewriting were used to inflate contribution totals.

## Generated large-file QA coverage

Adds a reproducible CSV fixture with 48,216 explicitly labelled MOCK daily records plus a checksum manifest and generator. Six full-period series exercise daily slicing across leap days, alternate sources, exact CSV/API float fidelity, nulls, zeros, QC states and production refusal through a test-only adapter. Existing runtime mock fixtures and application code are unchanged by this follow-up. These records are generated test data, not handwritten application code; GitHub may exclude them from contributor statistics.

Latest full validation: Python 3.11.18 — 526 passed, 5 skipped in 16.71 s. The skipped checks require genuine Group 3 inputs.
