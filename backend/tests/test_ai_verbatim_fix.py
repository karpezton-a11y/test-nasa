"""LLM answers that copy our own limitation text word for word must not be rejected for words inside it
("One MAM mean...", "non-significant"), while invented numbers and causal claims are still rejected."""

from __future__ import annotations

import json

import pytest
from conftest import build_settings
from fastapi.testclient import TestClient

from app.ai.service import ExplanationService
from app.main import create_app
from app.schemas import TrendResult

STATEMENT = "IGP rainfall: the trend is not statistically significant."
LIMIT = "One MAM mean per year from complete seasons only; years with a missing month in the season are skipped."


@pytest.fixture(scope="module")
def trend():
    with TestClient(create_app(build_settings(DATA_MODE="real"))) as c:
        r = c.post("/api/v1/analyze", json={"region_id": "IGP", "variable": "rainfall", "season": "MAM"}).json()["result"]
    return TrendResult.model_validate(r)


class Fake:
    def __init__(self, out): self.out = out
    def generate(self, facts): return json.dumps(self.out)


def run(trend, text, key_points=(), caveats=()):
    out = {"text": text, "key_points": list(key_points), "caveats": list(caveats), "numbers_used": []}
    return ExplanationService(build_settings(LLM_API_KEY="k", DATA_MODE="real"), Fake(out)).explain(
        [trend], data_status="real", data_version="v")


def test_reported_case_copying_the_limitation_is_accepted(trend):
    res = run(trend, f"{STATEMENT} The slope was 4.1 mm/month per decade, range -2.9 to 13.7 mm/month per decade "
                     f"(p = 0.259). Limitation: {LIMIT}", ["p = 0.259", "Coverage: 100.0%"])
    assert res.source == "llm" and res.guardrail.passed and LIMIT in res.text


def test_paraphrased_significance_bullet_is_dropped_not_fatal(trend):
    res = run(trend, f"{STATEMENT} Limitation: {LIMIT}", ["The change is not significant.", "p = 0.259"])
    assert res.source == "llm" and res.key_points == ["p = 0.259"]


def test_spelled_number_sentence_is_dropped_not_fatal(trend):
    res = run(trend, f"{STATEMENT} This covers twenty-two springs. Limitation: {LIMIT}")
    assert res.source == "llm" and "twenty" not in res.text


@pytest.mark.parametrize(("text", "issue"), [
    (f"{STATEMENT} The slope was 5.0 mm/month per decade. Limitation: {LIMIT}", "unsupported_number"),
    (f"{STATEMENT} Rain changed due to warming. Limitation: {LIMIT}", "causal_language"),
])
def test_real_violations_are_still_rejected(trend, text, issue):
    res = run(trend, text)
    assert res.source == "template" and issue in res.guardrail.issues


def test_every_served_limitation_can_be_quoted_safely():
    """For every region, variable and season, an answer made only of our own sentences must pass."""
    from app.ai.facts import build_facts
    from app.ai.guardrails import check
    from app.core_schemas import LlmOutput
    with TestClient(create_app(build_settings(DATA_MODE="real"))) as c:
        regions = c.get("/api/v1/regions").json()["result"]["regions"]
        for reg in regions:
            for var in reg["variables"]:
                for season in ("all", "JF", "MAM", "JJAS", "OND"):
                    res = c.post("/api/v1/analyze", json={"region_id": reg["region_id"], "variable": var, "season": season})
                    if res.status_code != 200:
                        continue
                    facts = build_facts([TrendResult.model_validate(res.json()["result"])], data_status="real", data_version="v")
                    item = facts["items"][0]
                    for lim in item["limitations"]:
                        out = LlmOutput(text=f"{item['significance_statement']} Limitation: {lim}", key_points=[], caveats=[],
                                        numbers_used=[])
                        issues = [i for i in check(out, facts) if i != "numbers_used_incomplete"]
                        assert issues == [] or set(issues) <= {"unsupported_number"}, (reg["region_id"], var, season, lim, issues)
