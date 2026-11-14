# Core API and AI integration — Phases C–D

## Core routes

The existing app factory registers routers/core.py alongside Karnish's routers. core_schemas.py adds request/composition types while reusing the existing contract result models. core.py delegates selection to services/core.py and scientific calculations to the Phase B adapter.

Period and ID validation reuse existing helpers and services.advanced.find_region. Seasonal coverage counts only expected selected-season slots, never fills a gap. Under ten requested years => PERIOD_TOO_SHORT; below 70% selected-season coverage => INSUFFICIENT_DATA. Timeseries keeps nulls and genuine zeros. Optional source selection uses RealStore.series_for_source where available and never silently substitutes a different source.

Comparison uses a common period and calls the same analyze service. If any result is not significant, same_direction is null. Variables mode obtains monthly_association through Karnish's interaction_for, requiring matching periods. No correlation or trend is recalculated by the API.

RealStore analysis is cached by region, variable, period, season, alpha and exclude_low_coverage. The latter is passed only to G3's explicitly declared keyword; otherwise DATA_NOT_AVAILABLE. Non-default alpha is forwarded. Mock mode never alters fixture statistics: unavailable option/window combinations return DATA_NOT_AVAILABLE.

The SCI-03 conflict remains: no not_assessed label is added to the frozen enum. Missing evidence returns DATA_NOT_AVAILABLE unless compute_trend already supplies a valid evidence block. Aadarsh/Adrian/G2 must settle the pre-H7 H6 fallback before real deployment.

## Explanation pipeline

1. Resolve a server-known ID from an in-memory verified-result registry or canonical validated store selection. Never form a filename from user input. Arbitrary/custom IDs not in the registry require a fresh result request or inline input. Client inline objects are schema-validated and never enter the verified-ID registry.
2. Prepare a small facts object with preformatted slope, CI, p-value and coverage strings. Numbers are not recomputed by an LLM. Display rounding only: rainfall one decimal, AOD three, p-value three or p < 0.001. Scientific source objects remain untouched.
3. Optional fixed-origin httpx call with system prompt, temperature 0.1, completion-token bound, JSON mode and 15-second httpx timeout. No retries, redirects or env-proxy use. Keys are omitted from repr/logs/prompts. A compatible model is explicitly chosen through the environment.
4. Validate structured output, exact numeric strings (including punctuation and Unicode hiding/sign cases), causal language, significance, limitations, total word count, PM2.5 equivalence and active markup. All visible fields are checked. Conservative rejections use a safe fallback rather than accepting ambiguous prose.
5. Missing key/provider failure/malformed JSON/check failure => deterministic template. Templates pass the same checks; unsafe/overlong free-text limitations can use a fixed coverage caveat present in facts. Only inability to produce even a safe template returns AI_UNAVAILABLE.
6. Cache the served explanation by SHA-256 of canonical facts JSON, bounded at 256 entries per app. Results are deep-copied; no facts preparation mutates science objects.
7. Ten explanation requests per minute per direct peer IP, cache hits included; client X-Forwarded-For is not read. Limiter expires entries and caps tracked peers. Multi-worker limits/caches are per process; use a single worker for this MVP.

Anomaly and interaction templates preserve baseline/association warnings without inventing findings. Summary input is provisional `{results:[existing objects]}` (up to eight), or CompareResult (its trend results are summarised). No undocumented public summary ID is created.

## PDF hook and frontend

Karnish's unchanged reports/hooks.py imports app.ai.report_summary.summarize(results). Request context supplies the per-app service and data provenance, including mock labelling. Direct script invocation without app context is template-only and performs no paid request.

- source=llm: **AI-generated explanation of computed results**
- source=template: **Automatic summary**

The returned Explanation object is `{text,key_points,caveats,source,guardrail:{passed,issues}}` in the standard envelope. The in-process PDF hook returns its exact existing `(text, source)` tuple. passed=true refers to the served safe text; issues lists why LLM output was bypassed/rejected. UI must render text as text rather than HTML.

## Provider documentation

Provider: OpenAI Chat Completions via raw httpx, no added SDK. Request format checked against [official Create chat completion reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create); max_completion_tokens is used instead of deprecated max_tokens. The model is intentionally unset: the team must choose one supporting JSON mode and the specified temperature. No live account, model availability, billing or generated response has been verified. Default empty-key automatic summaries are fully functional.

## Karnish impact

No advanced route/service, report builder, CSV module, snapshot exporter, mock generator, G–J model or example JSON was edited. Shared changes are main.py registration/context, config, the proposed rate-limit error, and optional seasonal coverage arguments. .env.example comments were updated without keys. scripts/smoke_test.py gained additive core/timing checks. Three old test expectations needed updates because planned core/summary features now exist; missing-hook behaviour remains explicitly tested. These changes are listed in decisions QA-02 and the API log.


## Integration with current main (14 November)

Shared RequestLimiter now handles /explain quota admission and Retry-After semantics. The app retains lazy creation, outer security/CORS/error middleware, report limits and contract OpenAPI documentation. Dependencies install under requirements.lock. Source-qualified methods and limitations are in docs/methods.md; their presence does not prove statistical execution or package delivery.
