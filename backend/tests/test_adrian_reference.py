"""G3 reference gate: skipped only while its named file is absent."""
import json
import math
from typing import Literal

from fastapi.testclient import TestClient
from pydantic import Field, model_validator
import pytest

from app.config import REPO_ROOT, load_settings
from app.core_schemas import AnalyzeRequest
from app.main import create_app
from app.schemas import ContractModel, Envelope, TrendResult

REFERENCE = REPO_ROOT / "data/processed/trend_results_reference.json"


class ReferenceCase(ContractModel):
    request: AnalyzeRequest
    result: TrendResult


class TrendReference(ContractModel):
    # [PROVISIONAL] REF-01, Aadarsh confirms this internal test-file layout.
    data_status: Literal["real"]
    data_version: str
    contract_version: str
    cases: list[ReferenceCase] = Field(min_length=1)

    @model_validator(mode="after")
    def _real_only(self):
        if "mock" in self.model_dump_json().lower():
            raise ValueError("Reference file must contain real results, never relabelled mock data")
        return self


def numeric_differences(expected, actual, path="result"):
    if expected is None or actual is None or isinstance(expected, bool) or isinstance(actual, bool):
        return [] if type(expected) is type(actual) and expected == actual else [path]
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return [] if math.isclose(expected, actual, rel_tol=0, abs_tol=1e-6) else [path]
    if isinstance(expected, dict) and isinstance(actual, dict):
        if expected.keys() != actual.keys(): return [path + ".keys"]
        return [item for k in expected if k != "computed_at"
                for item in numeric_differences(expected[k], actual[k], path + "." + k)]
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual): return [path + ".length"]
        return [item for i, (e, a) in enumerate(zip(expected, actual))
                for item in numeric_differences(e, a, f"{path}[{i}]")]
    return [] if type(expected) is type(actual) and expected == actual else [path]


@pytest.mark.skipif(not REFERENCE.is_file(), reason="Group 3 trend_results_reference.json not delivered")
def test_analyze_matches_group3_reference(tmp_path):
    reference = TrendReference.model_validate_json(REFERENCE.read_text(encoding="utf-8"))
    settings = load_settings(env={"APP_ENV": "prod", "DATA_MODE": "real",
        "DATA_VERSION": reference.data_version, "CONTRACT_VERSION": reference.contract_version,
        "REPORTS_DIR": str(tmp_path / "reports")}, env_file=None)
    with TestClient(create_app(settings)) as client:
        for case in reference.cases:
            response = client.post("/api/v1/analyze", json=case.request.model_dump(mode="json"))
            assert response.status_code == 200, response.text
            actual = Envelope[TrendResult].model_validate(response.json())
            assert actual.data_status == "real"
            assert actual.data_version == reference.data_version
            assert actual.contract_version == reference.contract_version
            assert numeric_differences(case.result.model_dump(mode="json"), actual.result.model_dump(mode="json")) == []


def test_reference_comparator_handles_precision_null_bool_and_timestamps():
    assert numeric_differences({"slope": 0.021}, {"slope": 0.0210005}) == []
    assert numeric_differences({"slope": 0.021}, {"slope": 0.0211}) == ["result.slope"]
    assert numeric_differences(None, 0) == ["result"]
    assert numeric_differences(True, 1) == ["result"]
    assert numeric_differences({"computed_at": "earlier"}, {"computed_at": "later"}) == []


def test_reference_format_validates_existing_scientific_shape():
    raw = json.loads((REPO_ROOT / "data/mock/normal/trend/IGP_aod_all_2003-01_2024-12.json").read_text().replace("MOCK", "TEST").replace("mock", "test"))
    ref = TrendReference.model_validate({"data_status": "real", "data_version": "TEST-only",
        "contract_version": "1.0", "cases": [{"request": {"region_id": "IGP", "variable": "aod"}, "result": raw["result"]}]})
    assert len(ref.cases) == 1
