"""Step 4: /health, /variables, /regions, /meta/sources through the store seam."""

from __future__ import annotations

import shutil
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.config import REPO_ROOT
from app.main import create_app
from app.schemas import Envelope, HealthResult, RegionsResult, SourceInfo, VariableInfo
from app.services.store import MockStore

ROUTES = {
    "/api/v1/health": HealthResult,
    "/api/v1/variables": list[VariableInfo],
    "/api/v1/regions": RegionsResult,
    "/api/v1/meta/sources": list[SourceInfo],
}
METADATA_FILES = {"/api/v1/variables": "variables.json", "/api/v1/regions": "regions.json",
                  "/api/v1/meta/sources": "sources.json"}


@pytest.mark.parametrize("path,model", ROUTES.items())
def test_route_returns_typed_mock_envelope(client, path, model):
    response = client.get(path)
    assert response.status_code == 200
    envelope = Envelope[model].model_validate(response.json())
    assert envelope.data_status == "mock"
    assert envelope.data_version == "MOCK-2026-11-13-normal"
    assert envelope.contract_version == "1.0"
    assert datetime.fromisoformat(response.json()["generated_at"]).utcoffset() is not None


def test_health_matches_envelope_and_reports_ai_from_config_only(client):
    body = client.get("/api/v1/health").json()
    result = body["result"]
    assert result["status"] == "ok"
    assert (result["data_status"], result["data_version"]) == (body["data_status"], body["data_version"])
    assert result["ai_available"] is False and result["trendlib_version"] == "1.0.0"  # bundled analysis/trendlib


@pytest.mark.parametrize("key,expected", [("", False), ("   ", False), ("not-a-real-key", True)])
def test_health_ai_available_reads_key_presence(make_settings, tmp_path, key, expected):
    with TestClient(create_app(make_settings(LLM_API_KEY=key, REPORTS_DIR=str(tmp_path)))) as c:
        body = c.get("/api/v1/health")
    assert body.json()["result"]["ai_available"] is expected
    assert "not-a-real-key" not in body.text


def test_variables_units_and_source_references(client):
    variables = {v["variable"]: v for v in client.get("/api/v1/variables").json()["result"]}
    assert set(variables) == {"rainfall", "aod"}
    assert variables["aod"]["unit"] == "1" and variables["aod"]["unit_label"] == "unitless"
    assert variables["rainfall"]["unit"] == "mm/month" and "mm/day" in variables["rainfall"]["caveat"]
    source_ids = {s["source_id"] for s in client.get("/api/v1/meta/sources").json()["result"]}
    assert all(set(v["sources"]) <= source_ids for v in variables.values())


def test_regions_and_geojson_describe_the_same_boxes(client):
    result = client.get("/api/v1/regions").json()["result"]
    features = {f["id"]: f for f in result["geojson"]["features"]}
    assert {r["region_id"] for r in result["regions"]} == set(features) == {"IGP", "TN"}
    for region in result["regions"]:
        w, s, e, n = region["bbox"]
        assert w < e and s < n and region["status"] == "provisional"
        assert region["period_available"] == {"start": "2003-01", "end": "2024-12"}
        ring = features[region["region_id"]]["geometry"]["coordinates"][0]
        assert ring[0] == ring[-1] and len(ring) == 5
        assert {tuple(p) for p in ring} == {(w, s), (e, s), (e, n), (w, n)}
        assert features[region["region_id"]]["properties"]["region_id"] == region["region_id"]


def test_sources_have_nine_fields_and_mock_provenance(client):
    sources = client.get("/api/v1/meta/sources").json()["result"]
    assert len(sources) == 6
    for source in sources:
        assert len(source) == 9 and source["doi"] is None and "MOCK" in source["product"]


@pytest.fixture
def copy_mock(tmp_path):
    target = tmp_path / "mock"
    shutil.copytree(REPO_ROOT / "data" / "mock" / "normal", target / "normal")
    return target


@pytest.mark.parametrize("path", ["/api/v1/regions", "/api/v1/meta/sources"])
def test_missing_metadata_file_returns_data_not_available(make_settings, copy_mock, tmp_path, path):
    (copy_mock / "normal" / METADATA_FILES[path]).unlink()
    with TestClient(create_app(make_settings(MOCK_DIR=str(copy_mock), REPORTS_DIR=str(tmp_path)))) as c:
        response = c.get(path)
        assert c.get("/api/v1/health").status_code == 200  # liveness unaffected
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DATA_NOT_AVAILABLE"
    assert str(tmp_path) not in response.text


def test_missing_variables_file_after_startup_returns_data_not_available(make_settings, copy_mock, tmp_path):
    with TestClient(create_app(make_settings(MOCK_DIR=str(copy_mock), REPORTS_DIR=str(tmp_path)))) as c:
        (copy_mock / "normal" / "variables.json").unlink()
        c.app.state.store._load.cache_clear()
        response = c.get("/api/v1/variables")
    assert response.status_code == 404 and response.json()["error"]["code"] == "DATA_NOT_AVAILABLE"


@pytest.mark.parametrize("content", ["{not json", '{"data_status": "mock", "result": {}}'])
def test_malformed_metadata_returns_sanitized_internal_error(make_settings, copy_mock, tmp_path, content):
    (copy_mock / "normal" / "regions.json").write_text(content)
    app = create_app(make_settings(MOCK_DIR=str(copy_mock), REPORTS_DIR=str(tmp_path)))
    with TestClient(app, raise_server_exceptions=False) as c:
        response = c.get("/api/v1/regions")
    assert response.status_code == 500
    assert response.json() == {"error": {"code": "INTERNAL_ERROR",
                                         "message": "Something went wrong on the server. Please try again.",
                                         "details": {}}}


class OtherStore(MockStore):
    """Any object implementing the DataStore protocol is served by the same routers."""

    def variables(self):
        return [v.model_copy(update={"label": v.label + " (seam test)"}) for v in super().variables()]


def test_same_routers_consume_an_injected_store(settings):
    store = OtherStore(REPO_ROOT / "data" / "mock" / "normal")
    with TestClient(create_app(settings, store=store)) as c:
        labels = [v["label"] for v in c.get("/api/v1/variables").json()["result"]]
    assert all(label.endswith("(seam test)") for label in labels)
