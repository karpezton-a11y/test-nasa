"""Deterministic summaries. Scientific numbers come only from prepared facts."""
from ..advanced_schemas import INTERACTION_GUARDRAIL
from ..core_schemas import LlmOutput
from .guardrails import NUMBER


def render(facts: dict) -> LlmOutput:
    items = facts["items"]
    parts = []
    # Compact multi-result summaries retain all significance statements. Limit
    # the standalone summary request to eight objects; PDF has its own compact fallback.
    for item in items:
        if item["kind"] == "trend":
            parts.append(item["significance_statement"])
            if len(items) == 1:
                parts.append(f"Period: {item['period']}; season: {item['season']}. Slope: {item['slope']} "
                             f"(range {item['range']}; {item['p_value']}). Coverage: {item['coverage']}. "
                             f"Evidence: {item['evidence_label']} under the team's rule.")
        elif item["kind"] == "interaction":
            parts.append(f"{item['label']}, {item['season']}: {item['n_events_used']} usable events. "
                         + (item["note"] + "." if item["note"] else "The comparison describes an association."))
        elif item["kind"] == "anomaly":
            parts.append(f"{item['label']}: unusual-month flags use the stated baseline.")
        else:
            parts.append(f"{item['label']}: indicators are reported in {item['unit']}.")
    if any(i["kind"] == "interaction" for i in items):
        limitation = INTERACTION_GUARDRAIL
    else:
        limitation = items[0]["limitations"][0]
    # G3 descriptions can be long; include a short fixed caveat already present
    # in facts, rather than cutting a scientific statement halfway through.
    if len(limitation.split()) > 35:
        limitation = "Scientific interpretation depends on data coverage."
    prefix = "MOCK development results. " if facts["data_status"] == "mock" else ""
    text = prefix + " ".join(parts) + " Limitation: " + limitation
    if len(text.split()) > 120:
        statements = [i["significance_statement"] for i in items if i["kind"] == "trend"]
        text = prefix + " ".join(statements) + " Results are described without causal interpretation. Limitation: " + limitation
    if len(text.split()) > 120:
        text = prefix + "Selected results have mixed availability; inspect the result tables for each finding. Limitation: " + limitation
    return LlmOutput(text=text, key_points=[], caveats=[], numbers_used=NUMBER.findall(text))
