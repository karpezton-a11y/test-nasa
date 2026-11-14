"""Exercise core HTTP routes through the real loader and a fake G3 package."""
import json
import sys
from types import SimpleNamespace

from fastapi.testclient import TestClient

from test_adrian_foundation import inputs, real_store  # shared isolated test fixtures
from app.config import REPO_ROOT
from app.main import create_app
from app.schemas import Period
from app.services.store import MockStore


def test_real_analysis_cache_and_option_forwarding(real_store, make_settings, monkeypatch):
    fixture = MockStore(REPO_ROOT / "data/mock/normal").trend("IGP", "aod", Period(start="2003-01", end="2024-12"), "all")
    raw = json.loads(fixture.model_dump_json().replace("MOCK", "TEST").replace("mock", "test"))
    calls = []
    def compute(frame, *, season, alpha, exclude_low_coverage=False):
        calls.append((frame, alpha, exclude_low_coverage))
        result = json.loads(json.dumps(raw))
        result["method"]["alpha"] = alpha
        return result
    monkeypatch.setitem(sys.modules, "trendlib", SimpleNamespace(compute_trend=compute,
        compute_evidence=lambda frame, result, sensitivity: result["evidence"]))
    with TestClient(create_app(make_settings(DATA_MODE="real"), store=real_store)) as client:
        body = {"region_id": "IGP", "variable": "aod", "options": {"alpha": 0.10, "exclude_low_coverage": True}}
        for _ in range(2):
            response = client.post("/api/v1/analyze", json=body)
            assert response.status_code == 200, response.text
            assert response.json()["data_status"] == "real"
        assert len(calls) == 1 and calls[0][1:] == (0.10, True)
        assert calls[0][0].attrs["source_id"] == raw["source_id"]


def test_real_no_package_and_programming_fault_have_distinct_errors(real_store, make_settings, monkeypatch):
    monkeypatch.setitem(sys.modules, "trendlib", None)
    with TestClient(create_app(make_settings(DATA_MODE="real"), store=real_store), raise_server_exceptions=False) as client:
        response = client.post("/api/v1/analyze", json={"region_id": "IGP", "variable": "aod"})
        assert response.status_code == 404 and response.json()["error"]["code"] == "DATA_NOT_AVAILABLE"
        def bug(*args, **kwargs): raise ValueError("do not disclose this path")
        monkeypatch.setitem(sys.modules, "trendlib", SimpleNamespace(compute_trend=bug))
        response = client.post("/api/v1/analyze", json={"region_id": "IGP", "variable": "aod"})
        assert response.status_code == 500 and response.json()["error"]["code"] == "INTERNAL_ERROR"
        assert "disclose" not in response.text
