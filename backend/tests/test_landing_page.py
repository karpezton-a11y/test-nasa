"""The 3D landing page: its files are served, its baked globe snapshot matches the live API,
the case-file numbers match the engine, and it carries no NASA insignia."""

from __future__ import annotations

import json
import re

import pytest
from conftest import build_settings
from fastapi.testclient import TestClient

from app.config import REPO_ROOT
from app.main import create_app

FRONTEND = REPO_ROOT / "frontend"
SNAPSHOT = json.loads((FRONTEND / "data" / "globe_snapshot.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def real_client():
    with TestClient(create_app(build_settings(DATA_MODE="real"))) as client:
        yield client


def test_landing_assets_are_served_and_compressed(client):
    page = client.get("/")
    for src in ("/static/fx.js", "/static/globe.js", "/static/vendor/three.module.min.js",
                "/static/vendor/OrbitControls.js", "/static/data/countries.json", "/static/data/globe_snapshot.json",
                "/static/logo.svg", "/static/rocket.js", "/static/mascot.js"):
        res = client.get(src, headers={"Accept-Encoding": "gzip"})
        assert res.status_code == 200, src
    big = client.get("/static/vendor/three.module.min.js", headers={"Accept-Encoding": "gzip"})
    assert big.headers.get("content-encoding") == "gzip"
    assert '"three": "/static/vendor/three.module.min.js"' in page.text  # import map
    assert '/static/fx.js' in page.text and '/static/logo.svg' in page.text


def test_lab_keeps_every_control_the_app_script_needs(client):
    html = client.get("/").text
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")
    for element_id in set(re.findall(r'\$\("#([\w-]+)"\)', script)):
        assert f'id="{element_id}"' in html, element_id
    for tab in re.findall(r'data-tab="(\w+)"', html):
        assert f'id="tab-{tab}"' in html


def test_globe_snapshot_matches_the_live_scan(real_client):
    assert SNAPSHOT["data_status"] == "real"
    live_regions = {r["region_id"]: r["variables"] for r in real_client.get("/api/v1/regions").json()["result"]["regions"]}
    assert {r["region_id"]: r["variables"] for r in SNAPSHOT["regions"]} == live_regions
    for variable, layer in SNAPSHOT["layers"].items():
        live = real_client.get(f"/api/v1/scan?season=all&variable={variable}").json()["result"]["rows"]
        assert {(r["region_id"], r["status"]) for r in layer["rows"]} == {(r["region_id"], r["status"]) for r in live}, variable


def test_globe_layer_buttons_exist_in_the_snapshot():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    for layer in re.findall(r'data-layer="(\w+)"', html):
        assert layer in SNAPSHOT["layers"], layer


CASE_FILES = [  # (region, variable, number on the card, how to read it from a scan row)
    ("LA_BASIN", "no2", -51.5, "percent"), ("DELHI", "no2", -4.2, "percent"),
    ("IGP", "aod", 15.7, "percent"), ("AMAZON_ARC", "air_temperature", 0.64, "slope"),
    ("SAHEL", "rainfall", 1.0, "slope"),
]


@pytest.mark.parametrize(("region", "variable", "shown", "kind"), CASE_FILES)
def test_case_file_numbers_match_the_engine(real_client, region, variable, shown, kind):
    rows = real_client.get(f"/api/v1/scan?season=all&variable={variable}").json()["result"]["rows"]
    row = next(r for r in rows if r["region_id"] == region)
    value = row["percent_change_per_decade"] if kind == "percent" else row["sen_slope"]
    assert round(value, 1 if kind == "percent" or shown == 1.0 else 2) == shown
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert f'data-region="{region}" data-variable="{variable}"' in html


def test_case_file_verdicts_match_the_engine(real_client):
    rows = {(r["region_id"], v): r["status"] for v in ("no2", "aod", "air_temperature", "rainfall")
            for r in real_client.get(f"/api/v1/scan?season=all&variable={v}").json()["result"]["rows"]}
    assert rows[("LA_BASIN", "no2")] == "significant"
    assert rows[("DELHI", "no2")] == "not_significant"
    assert rows[("IGP", "aod")] == "significant"
    assert rows[("IGP", "rainfall")] == "not_significant"
    assert rows[("AMAZON_ARC", "air_temperature")] == "significant"
    assert rows[("SAHEL", "rainfall")] == "significant"


def test_no_nasa_insignia_and_a_clear_disclaimer():
    # Space Apps rules: no NASA insignia, logotype or other NASA identifiers without written permission.
    names = [p.name.lower() for p in FRONTEND.rglob("*")]
    assert not any(k in n for n in names for k in ("meatball", "insignia", "nasa-logo", "nasa_logo", "worm"))
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert "not endorsed by NASA" in html


def test_mission_sections_and_their_data_routes(real_client):
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    for section in ("missions", "climate", "vitals", "finale"):
        assert f'id="{section}"' in html, section
    # Warming stripes ask /analyze/detail for air temperature in each listed place: every one must be served.
    for region in re.findall(r'class="chip(?: active)?" data-region="(\w+)"', html):
        res = real_client.post("/api/v1/analyze/detail", json={"region_id": region, "variable": "air_temperature", "season": "all"})
        assert res.status_code == 200, region
        assert len(res.json()["result"]["analysis"]["fit"]) >= 9 * 12
    # Vital signs read the catalogue themes.
    catalog = real_client.get("/api/v1/catalog").json()["result"]
    assert {"air", "heat", "water", "land", "ice", "ocean"} <= set(catalog["themes"])
    assert sum(v["available_now"] for v in catalog["variables"]) == 4


def test_guided_ux_sections_and_glossary_terms(client):
    html = client.get("/").text
    for section in ("investigate", "demos", "glossary"):
        assert f'id="{section}"' in html, section
    assert client.get("/static/guide.js").status_code == 200
    guide = (FRONTEND / "guide.js").read_text(encoding="utf-8")
    glossary_block = guide[guide.index("export const GLOSSARY"):guide.index("// ----", guide.index("export const GLOSSARY"))]
    known = set(re.findall(r'^\s+"?([\w-]+)"?: \[', glossary_block, flags=re.M))
    used = set(re.findall(r'data-term="([\w-]+)"', html)) | set(re.findall(r'term\("([\w-]+)"', guide))
    assert used and used <= known, used - known


def test_wizard_choices_match_the_discover_api(client):
    guide = (FRONTEND / "guide.js").read_text(encoding="utf-8")
    choices = client.get("/api/v1/discover/questions").json()["result"]["choices"]
    themes = set(re.findall(r'\["(\w+)", "[^"]+", "[^"]+"\]', guide[guide.index("const THEMES"):guide.index("const PLACE_ICON")]))
    places = set(re.findall(r'\["(\w+)", "[^"]+", "[^"]+"\]', guide[guide.index("const PLACES"):guide.index("export const GLOSSARY")]))
    assert themes == set(choices["themes"])
    assert places == set(choices["place_types"])


def test_demo_player_can_play_every_demo(real_client):
    for demo in real_client.get("/api/v1/demos").json()["result"]:
        for step in demo["steps"]:
            if not step.get("method"):
                continue
            res = (real_client.post(step["path"], json=step["body"]) if step["method"] == "POST" else real_client.get(step["path"]))
            assert res.status_code == 200, (demo["id"], step["path"], res.text[:200])
