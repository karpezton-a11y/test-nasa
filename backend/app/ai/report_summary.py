"""Exact existing PDF hook: summarize(results) -> (text, llm|template)."""
from ..config import load_settings
from .context import REPORT_CONTEXT
from .service import ExplanationService


def summarize(results):
    if not results:
        return "No computed result is available for an automatic summary.", "template"
    context = REPORT_CONTEXT.get()
    if context is not None:
        service, info = context
        # Reports must not wait for a new 15-second provider call. Reuse a
        # guarded cached explanation, or render an immediate automatic summary.
        summary = service.explain(results[:8], data_status=info.data_status,
                                  data_version=info.data_version, use_llm=False)
    else:
        # Direct PDF/script usage has no app settings/verified store provenance.
        # Do not contact an LLM or assume loaded provenance outside a request.
        service = ExplanationService(load_settings(env={}, env_file=None))
        summary = service.explain(results[:8], data_status="real", data_version="unavailable", use_llm=False)
    return summary.text, summary.source
