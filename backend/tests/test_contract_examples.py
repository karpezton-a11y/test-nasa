"""Step 2: every docs/examples file is valid JSON in the exact wire format.

Success examples = envelope + typed result. Error examples = bare section 6-I shape.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from app.advanced_schemas import (
    AnomalyBothResult, AnomalyResult, ErrorResponse, IndicatorResult, InteractionResult,
)
from app.config import REPO_ROOT
from app.errors import CONTRACT_ERROR_STATUS, ERROR_STATUS
from app.schemas import Envelope

EXAMPLES = REPO_ROOT / "docs" / "examples"
SUCCESS_MODELS = {
    "anomaly_rainfall.json": AnomalyResult,
    "anomaly_aod.json": AnomalyResult,
    "anomaly_low_coverage.json": AnomalyResult,
    "anomaly_both.json": AnomalyBothResult,
    "interaction_ok.json": InteractionResult,
    "interaction_too_few_events.json": InteractionResult,
    "rainfall_indicator_heavy_rain_share.json": IndicatorResult,
}


def _load(path: Path):
    def reject_constant(name: str):
        raise ValueError(f"non-JSON constant {name}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)


def test_every_example_file_is_covered():
    names = {p.name for p in EXAMPLES.glob("*.json")}
    error_names = {n for n in names if n.startswith("error_")}
    assert names - error_names == set(SUCCESS_MODELS)


@pytest.mark.parametrize("name,model", sorted(SUCCESS_MODELS.items()))
def test_success_example_matches_envelope_and_model(name, model):
    data = _load(EXAMPLES / name)
    envelope = Envelope[model].model_validate(data)
    assert envelope.data_status == "mock"
    assert envelope.data_version.startswith("MOCK-")
    assert "YYYY" not in json.dumps(data)


@pytest.mark.parametrize("code", sorted(CONTRACT_ERROR_STATUS))
def test_one_error_example_per_contract_code(code):
    data = _load(EXAMPLES / f"error_{code}.json")
    parsed = ErrorResponse.model_validate(data)
    assert parsed.error.code == code
    assert set(data) == {"error"}  # bare shape: no envelope fields on errors (decision D-01)


def test_error_examples_use_registered_codes():
    for path in EXAMPLES.glob("error_*.json"):
        code = ErrorResponse.model_validate(_load(path)).error.code
        assert path.name == f"error_{code}.json"
        assert code in ERROR_STATUS


def test_interaction_examples_keep_guardrail_and_low_count_rule():
    ok = _load(EXAMPLES / "interaction_ok.json")["result"]
    few = _load(EXAMPLES / "interaction_too_few_events.json")["result"]
    assert ok["guardrail"] == few["guardrail"]
    assert few["n_events_used"] < 10 and few["p_value"] is None and few["median_change_ci"] is None
    assert ok["n_events_used"] >= 10 and ok["p_value"] is not None


def test_json_blocks_in_contract_md_equal_example_files():
    import re
    text = (REPO_ROOT / "docs" / "contract.md").read_text(encoding="utf-8")
    blocks = [json.loads(b) for b in re.findall(r"```json\n(.*?)```", text, flags=re.S)]
    examples = [_load(p) for p in EXAMPLES.glob("*.json")]
    assert len(blocks) >= 3
    for block in blocks:
        assert block in examples, f"contract.md block not identical to any example file: {str(block)[:80]}"


def test_examples_keep_real_zero_and_null_missing():
    rows = _load(EXAMPLES / "anomaly_rainfall.json")["result"]["anomalies"]
    assert any(r["value"] == 0.0 and r["qc_flag"] == "ok" for r in rows)
    for r in rows:
        if r["value"] is None:
            assert r["qc_flag"] == "missing" and r["score"] is None
        else:
            assert math.isfinite(r["value"])
