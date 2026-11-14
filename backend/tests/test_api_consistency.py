"""Audit M2, M3, M7, M8: one error code per mistake, documented error shape, CORS headers, one store."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.errors import ERROR_STATUS
from app.main import create_app
from app.services.store import DatasetInfo, MockStore, get_store

API = "/api/v1"
LONG = "X" * 40
HUGE = "Y" * 4000
REPORT_BODY = {"region_id": "IGP", "variables": ["rainfall", "aod"], "start": "2003-01", "end": "2024-12",
               "season": "all", "include": ["trend"]}


# ----------------------------------------------------------------- M2: the same mistake gets the same code

GET_CASES = [
    ("/anomalies", {"region_id": LONG, "variable": "aod"}, "INVALID_REGION"),
    ("/anomalies", {"region_id": HUGE, "variable": "aod"}, "INVALID_REGION"),
    ("/anomalies", {"region_id": "IGP", "variable": LONG}, "INVALID_VARIABLE"),
    ("/anomalies", {"region_id": "IGP", "variable": "aod", "start": "2003-01-01"}, "INVALID_PERIOD"),
    ("/anomalies", {"region_id": "IGP", "variable": "aod", "end": "2024-12-31"}, "INVALID_PERIOD"),
    ("/interaction", {"region_id": LONG, "season": "JJAS"}, "INVALID_REGION"),
    ("/interaction", {"region_id": "IGP", "season": "MONSOON-SEASON"}, "INVALID_SEASON"),
    ("/rainfall/indicators", {"region_id": "IGP", "indicator": LONG, "season": "annual"}, "INVALID_INDICATOR"),
    ("/rainfall/indicators", {"region_id": "IGP", "indicator": "rx5day", "season": "MONSOON"}, "INVALID_SEASON"),
    ("/export/csv", {"region_id": LONG, "variable": "aod"}, "INVALID_REGION"),
    ("/export/csv", {"region_id": "IGP", "variable": LONG}, "INVALID_VARIABLE"),
    ("/export/csv", {"region_id": "IGP", "variable": "aod", "start": "2003-01-01"}, "INVALID_PERIOD"),
    ("/export/csv", {"region_id": "IGP", "variable": "aod", "what": "everything-at-once"}, "INVALID_EXPORT_TYPE"),
]


@pytest.mark.parametrize("path,params,code", GET_CASES)
def test_overlong_or_full_date_values_get_the_specific_400_code(client, path, params, code):
    response = client.get(f"{API}{path}", params=params)
    assert (response.status_code, response.json()["error"]["code"]) == (400, code)
    assert LONG not in response.text and HUGE not in response.text  # never echo the input


@pytest.mark.parametrize("field,value,code", [
    ("region_id", LONG, "INVALID_REGION"),
    ("start", "2003-01-01", "INVALID_PERIOD"),
    ("end", "2024-12-31", "INVALID_PERIOD"),
    ("season", "MONSOON-SEASON", "INVALID_SEASON"),
])
def test_report_body_overlong_values_get_the_specific_400_code(client, field, value, code):
    response = client.post(f"{API}/report", json={**REPORT_BODY, field: value})
    assert (response.status_code, response.json()["error"]["code"]) == (400, code)


def test_wrong_type_is_still_a_validation_error(client):
    response = client.get(f"{API}/export/csv", params={"region_id": "IGP", "variable": "aod",
                                                       "frequency": "fortnightly"})
    assert (response.status_code, response.json()["error"]["code"]) == (422, "VALIDATION_ERROR")


# ----------------------------------------------------------------- M3: OpenAPI shows the real error shape


@pytest.fixture
def openapi(client) -> dict:
    return client.get("/openapi.json").json()


def _error_ref(response: dict) -> str:
    return response["content"]["application/json"]["schema"]["$ref"]


def test_openapi_has_no_fastapi_default_validation_shape(openapi):
    text = json.dumps(openapi)
    assert "HTTPValidationError" not in text and '"detail"' not in text


def test_every_operation_documents_contract_errors(openapi):
    for path, item in openapi["paths"].items():
        for method, operation in item.items():
            responses = operation["responses"]
            assert "500" in responses, f"{method} {path}"
            for status, response in responses.items():
                if status.startswith(("4", "5")):
                    assert _error_ref(response).endswith("/ErrorResponse"), f"{method} {path} {status}"


@pytest.mark.parametrize("path,method,status,code", [
    ("/api/v1/anomalies", "get", "400", "INVALID_REGION"),
    ("/api/v1/anomalies", "get", "404", "DATA_NOT_AVAILABLE"),
    ("/api/v1/anomalies", "get", "422", "VALIDATION_ERROR"),
    ("/api/v1/rainfall/indicators", "get", "400", "INVALID_INDICATOR"),
    ("/api/v1/export/csv", "get", "422", "PERIOD_TOO_SHORT"),
    ("/api/v1/report", "post", "429", "RATE_LIMITED"),
    ("/api/v1/report", "post", "503", "REPORT_BUSY"),
    ("/api/v1/report", "post", "500", "REPORT_FAILED"),
    ("/api/v1/report/{report_id}", "get", "404", "REPORT_NOT_FOUND"),
    ("/api/v1/health", "get", "500", "INTERNAL_ERROR"),
])
def test_documented_examples_name_the_codes_each_route_returns(openapi, path, method, status, code):
    examples = openapi["paths"][path][method]["responses"][status]["content"]["application/json"]["examples"]
    assert examples[code]["value"]["error"]["code"] == code


def test_documented_codes_are_registered_with_their_status(openapi):
    for item in openapi["paths"].values():
        for operation in item.values():
            for status, response in operation["responses"].items():
                for code in response.get("content", {}).get("application/json", {}).get("examples", {}):
                    if status.startswith(("4", "5")):
                        assert ERROR_STATUS[code] == int(status), code


# ----------------------------------------------------------------- M7: the browser can read the file name


def test_cors_exposes_content_disposition_and_retry_after(make_settings, tmp_path):
    settings = make_settings(ALLOWED_ORIGIN="https://frontend.example", REPORTS_DIR=str(tmp_path))
    with TestClient(create_app(settings)) as c:
        response = c.get(f"{API}/export/csv", params={"region_id": "IGP", "variable": "aod"},
                         headers={"Origin": "https://frontend.example"})
    exposed = {h.strip().lower() for h in response.headers["access-control-expose-headers"].split(",")}
    assert {"content-disposition", "retry-after"} <= exposed


# ----------------------------------------------------------------- M8: one store for provenance and data


class RenamedStore(MockStore):
    def __init__(self, scenario_dir) -> None:
        super().__init__(scenario_dir)
        self.info = DatasetInfo("mock", "MOCK-override-test", self.info.contract_version)

    def _envelope(self, relative: str):
        return self._load(relative).model_copy(update={"data_version": self.info.data_version})


def test_overridden_store_is_used_for_data_and_provenance(settings):
    app = create_app(settings)
    other = RenamedStore(settings.mock_dir / settings.mock_scenario)
    app.dependency_overrides[get_store] = lambda: other
    with TestClient(app) as c:
        for path in ("/health", "/variables"):
            assert c.get(f"{API}{path}").json()["data_version"] == "MOCK-override-test", path
        assert c.get(f"{API}/health").json()["result"]["data_version"] == "MOCK-override-test"
