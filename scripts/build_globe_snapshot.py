#!/usr/bin/env python
"""Bake the 3D globe's first paint: /scan results for each variable, from the real data.

    python scripts/build_globe_snapshot.py      # writes frontend/data/globe_snapshot.json

The landing page colours the globe from this file at once (labelled "last computed"),
then asks the live API and replaces it (labelled "live"). Run it again after the data
changes; a test checks the file still matches the live answer.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DATA_MODE", "real")
os.environ.setdefault("APP_ENV", "dev")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402

KEEP = ("region_id", "region_name", "variable", "status", "sen_slope", "slope_unit",
        "percent_change_per_decade", "p_value", "q_value", "headline")


def build() -> dict:
    with TestClient(create_app()) as client:  # the lifespan loads the data store
        return _collect(client)


def _collect(client: TestClient) -> dict:
    regions = client.get("/api/v1/regions").json()["result"]["regions"]
    variables = client.get("/api/v1/variables").json()
    layers = {}
    for v in variables["result"]:
        scan = client.get(f"/api/v1/scan?season=all&variable={v['variable']}").json()
        layers[v["variable"]] = {
            "label": v["label"],
            "summary": scan["result"]["summary"],
            "rows": [{k: r.get(k) for k in KEEP} for r in scan["result"]["rows"]],
        }
    return {
        "data_status": variables["data_status"],
        "data_version": variables["data_version"],
        "regions": [{"region_id": r["region_id"], "name": r["name"], "bbox": r["bbox"],
                     "variables": r["variables"]} for r in regions],
        "layers": layers,
    }


if __name__ == "__main__":
    out = ROOT / "frontend" / "data" / "globe_snapshot.json"
    out.write_text(json.dumps(build(), indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")
