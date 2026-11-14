"""Prepare display strings from validated results; never compute science."""
from __future__ import annotations

from ..advanced_schemas import AnomalyBothResult, AnomalyResult, IndicatorResult, InteractionResult, INTERACTION_GUARDRAIL
from ..schemas import TrendResult


import re

# Limitations an explanation may quote verbatim. A sentence that itself mentions significance, PM2.5,
# a direction word, a number or a cause would make the guardrails reject any text quoting it, so such
# sentences stay in the result (and the UI) but are not offered to the explanation.
_UNSAFE_LIMITATION = re.compile(r"significan|pm2\.5|increas|decreas|\brose\b|\bfell\b|\d|"
                                r"\bcaus|due to|because|leads? to|driven by|result(?:s|ed)? in", re.IGNORECASE)


def safe_limitations(limitations) -> list[str]:
    return [lim for lim in limitations if not _UNSAFE_LIMITATION.search(lim) and len(lim.split()) <= 35]


def p_text(p: float) -> str:
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


def num(value: float, variable: str) -> str:
    """DOCX 6-A: rainfall 1 d.p., AOD 3 d.p.; catalogue variables (K, DU, molecules/cm2...) 3 significant figures."""
    if variable == "rainfall":
        return f"{value:.1f}"
    if variable.startswith("aod"):
        return f"{value:.3f}"
    return f"{value:.3g}"


def item_facts(result) -> dict:
    if isinstance(result, TrendResult):
        label = f"{result.region_id} {result.variable}"
        significance = f"{label}: the trend is {'statistically significant' if result.significant else 'not statistically significant'}."
        direction = {"increasing": "increased", "decreasing": "decreased", "no_significant_trend": "had no statistically significant trend"}[result.direction]
        unit = "per decade" if result.slope_unit.startswith("1 ") else result.slope_unit  # dimensionless AOD
        slope = f"{num(result.sen_slope, result.variable)} {unit}"
        ci = f"{num(result.slope_ci[0], result.variable)} to {num(result.slope_ci[1], result.variable)} {unit}"
        return {"kind": "trend", "label": label, "period": f"{result.period.start} to {result.period.end}",
                "season": result.season, "direction": direction, "significant": result.significant,
                "significance_statement": significance, "slope": slope, "range": ci,
                "p_value": p_text(result.p_value), "coverage": f"{result.evidence.valid_obs_pct:.1f}%",
                "evidence_label": result.evidence.evidence_label,
                "limitations": safe_limitations(result.limitations) or ["Record length limits the interpretation of this trend."]}
    if isinstance(result, AnomalyBothResult):
        return {"kind": "anomaly", "label": result.region_id + " rainfall and AOD",
                "period": f"{result.period.start} to {result.period.end}",
                "children": [item_facts(r) for r in result.results],
                "limitations": ["Anomaly flags depend on the stated baseline and data coverage."]}
    if isinstance(result, AnomalyResult):
        return {"kind": "anomaly", "label": f"{result.region_id} {result.variable}",
                "period": f"{result.period.start} to {result.period.end}",
                "baseline": f"{result.baseline.start} to {result.baseline.end}",
                "method": result.baseline.statistic,
                "limitations": ["Anomaly flags depend on the stated baseline and data coverage."]}
    if isinstance(result, InteractionResult):
        return {"kind": "interaction", "label": f"{result.region_id} rainfall and AOD", "season": result.season,
                "period": f"{result.period.start} to {result.period.end}", "n_events_used": str(result.n_events_used),
                "change": "not available" if result.median_change is None else f"{result.median_change:.3f}",
                "p_value": "not assessed" if result.p_value is None else p_text(result.p_value),
                "note": result.note, "guardrail": INTERACTION_GUARDRAIL,
                "limitations": [INTERACTION_GUARDRAIL]}
    if isinstance(result, IndicatorResult):
        return {"kind": "indicator", "label": f"{result.region_id} {result.indicator}",
                "unit": result.unit, "definition": result.definition,
                "period": f"{result.period.start} to {result.period.end}",
                "limitations": ["Indicator values depend on daily data coverage."]}
    raise TypeError("Unsupported scientific result")


def build_facts(results, *, data_status: str, data_version: str) -> dict:
    items = [item_facts(r) for r in results]
    for item in items:
        item["limitations"].append("Scientific interpretation depends on data coverage.")
    return {"data_status": data_status, "data_version": data_version,
            "items": items,
            "aod_caveat": "AOD is a column optical measurement, not ground-level PM2.5."}
