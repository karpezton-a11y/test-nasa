"""One explanation pipeline for HTTP and PDF, with bounded in-memory caches."""
from collections import OrderedDict
from contextlib import contextmanager
import hashlib
from copy import deepcopy
import json
import logging
from threading import Lock
from time import monotonic

from ..core_schemas import Explanation, GuardrailResult, LlmOutput
from ..errors import ApiError, api_error
from ..services.rate_limit import RequestLimiter
from .client import ProviderClient
from .facts import build_facts
from .guardrails import NUMBER, check
from .templates import render

logger = logging.getLogger("trendtrace.ai")


class RateLimiter(RequestLimiter):
    """Use the existing limiter's admission/quota/Retry-After semantics."""
    def __init__(self, clock=monotonic):
        super().__init__(max_concurrent=4, max_per_window=10, window_s=60,
                         clock=clock, busy_code="AI_UNAVAILABLE")
        self._admission_lock = Lock()

    @property
    def clients(self):
        return self._recent  # introspection for deterministic expiry tests

    def _admit(self, client_key):
        with self._admission_lock:
            with self._lock:
                self._forget_old(self._clock())
                if client_key not in self._recent and len(self._recent) >= 10000:
                    raise api_error("RATE_LIMITED", "Please try again shortly.", {"retry_after_s": 60})
            super()._admit(client_key)

    @contextmanager
    def slot(self, ip):
        try:
            with super().slot(ip):
                yield
        except ApiError as exc:
            if exc.code == "AI_UNAVAILABLE":
                raise api_error("AI_UNAVAILABLE", "The explanation service is busy. Please try again shortly.",
                                exc.details) from None
            raise

    def consume(self, ip):
        """Quota-only compatibility helper; HTTP handlers hold slot() instead."""
        with self.slot(ip):
            pass


class ExplanationService:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client or ProviderClient(settings)
        self.cache = OrderedDict()
        self.lock = Lock()
        self.limiter = RateLimiter()

    def explain(self, results, *, data_status, data_version, use_llm=True):
        facts = build_facts(results, data_status=data_status, data_version=data_version)
        canonical = json.dumps(facts, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        key = hashlib.sha256(canonical.encode()).hexdigest()
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key].model_copy(deep=True)
        issues = []
        candidate = None
        llm_failed = False
        if use_llm and self.settings.llm_api_key_set:
            try:
                raw = self.client.generate(facts)
                candidate = LlmOutput.model_validate_json(raw) if isinstance(raw, (str, bytes)) else LlmOutput.model_validate(raw)
                candidate = repair(candidate, facts)
                issues = check(candidate, facts)
                if issues:
                    logger.warning("Explanation provider text rejected by guardrails %s; using automatic summary", issues)
            except Exception as exc:
                # Do not log provider bodies/keys or copy exception messages to users.
                status = getattr(exc, "status", None)
                logger.warning("Explanation provider failed (%s%s); using automatic summary", type(exc).__name__,
                               f", HTTP {status}" if status else "")
                issues = ["provider_unavailable" if status is None else f"provider_http_{status}"]
            llm_failed = candidate is None or bool(issues)
            if candidate is not None and not issues:
                result = Explanation(text=candidate.text, key_points=candidate.key_points, caveats=candidate.caveats,
                                     source="llm", guardrail=GuardrailResult(passed=True, issues=[]))
            else:
                result = self._template(facts, issues)
        else:
            result = self._template(facts, ["llm_unconfigured"] if not self.settings.llm_api_key_set else [])
        # A report's immediate template must not prevent a later explicit
        # /explain request from generating an optional LLM explanation.
        # A provider failure is not cached, so the next click can try the provider again (the per-client
        # rate limit still bounds cost); successes and unconfigured templates are cached.
        if (use_llm or result.source == "llm") and not llm_failed:
            with self.lock:
                self.cache[key] = result.model_copy(deep=True)
                self.cache.move_to_end(key)
                while len(self.cache) > 256: self.cache.popitem(last=False)
        return result

    @staticmethod
    def _template(facts, issues):
        try:
            output = render(facts)
            problems = check(output, facts)
            if problems:
                # Preserve all result facts, using a fixed relevant caveat if the
                # original free-text limitation cannot safely fit the summary.
                compact = deepcopy(facts)
                for item in compact["items"]:
                    if item["kind"] != "interaction":
                        item["limitations"] = ["Scientific interpretation depends on data coverage."]
                output = render(compact)
                if check(output, facts):
                    raise ValueError("Automatic summary did not pass guardrails")
            return Explanation(text=output.text, key_points=output.key_points, caveats=output.caveats,
                               source="template", guardrail=GuardrailResult(passed=True, issues=issues))
        except Exception as exc:
            logger.error("Automatic summary failed (%s)", type(exc).__name__)
            raise api_error("AI_UNAVAILABLE", "The explanation is temporarily unavailable.") from exc


def repair(candidate: LlmOutput, facts: dict) -> LlmOutput:
    """Fix formatting only, never content: add a missing exact significance statement or verbatim limitation,
    and list the numbers actually used. Every number, word and claim is still checked by guardrails.check."""
    text = candidate.text.strip()
    for item in facts["items"]:
        statement = item.get("significance_statement")
        if statement and statement not in text:
            text = f"{statement} {text}"
    limits = [lim for item in facts["items"] for lim in item["limitations"]]
    visible = " ".join([text, *candidate.key_points, *candidate.caveats])
    if limits and not any(lim in visible for lim in limits):
        text = f"{text} Limitation: {limits[0]}"
    numbers = NUMBER.findall(" ".join([text, *candidate.key_points, *candidate.caveats]))
    return candidate.model_copy(update={"text": text, "numbers_used": numbers})
