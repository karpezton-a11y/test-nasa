#!/usr/bin/env python
"""Export API responses for the supported selections into a static folder (fallback hosting).

    python scripts/export_static_snapshot.py                    # writes snapshot/ (git-ignored)
    python scripts/export_static_snapshot.py --require-real     # refuses unless the data is real

Runs the app in-process (no server needed) with the current .env / environment, so
the snapshot carries the same data_status as the data it was built from. Every
response is saved under snapshot/api/v1/... and listed in snapshot/manifest.json:

    {"data_status", "data_version", "contract_version", "generated_at",
     "files":       {"/api/v1/...?...": {"file": "api/v1/...", "content_type": "..."}},
     "unavailable": {"/api/v1/...?...": "DATA_NOT_AVAILABLE"},
     "selections":  {"regions": [...], "anomalies": [...], "interaction": [...],
                     "indicators": [...], "reports": ["reports/IGP.pdf", ...]}}

The frontend looks a request URL up in "files" (exact string, parameters in the order
written here); a URL in "unavailable" shows the same empty state as the live API.
One sample PDF per region is included as reports/<region>.pdf.

Only "nothing to serve yet" answers (EXPECTED_UNAVAILABLE) go into "unavailable".
Any other error (a 500, a rejected request, a failed PDF) is a bug: the run fails
with exit code 1, lists every failed request, and the previous snapshot is kept.
The new snapshot is built in a staging folder and swapped in only when complete.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "snapshot"
VARIABLES = ("rainfall", "aod")
INTERACTION_SEASONS = ("all", "JF", "MAM", "JJAS", "OND")
INDICATORS = ("heavy_rain_share", "longest_dry_spell", "rx5day")
INDICATOR_SEASONS = ("annual", "JJAS", "OND")
SELECTION_KEYS = {"anomalies": ("/anomalies", ("region_id", "variable")),
                  "interaction": ("/interaction", ("region_id", "season")),
                  "indicators": ("/rainfall/indicators", ("region_id", "indicator", "season"))}


# Codes meaning "nothing to serve for this selection yet" (the live API answers the same way).
EXPECTED_UNAVAILABLE = ("DATA_NOT_AVAILABLE", "NOT_FOUND", "INSUFFICIENT_DATA", "PERIOD_TOO_SHORT")


class SnapshotRefused(RuntimeError):
    """--require-real was given but the loaded data is not real."""


class SnapshotFailed(RuntimeError):
    """Some responses were errors other than "not available"; the previous snapshot is kept."""

    def __init__(self, failures: dict[str, str]) -> None:
        super().__init__(f"{len(failures)} request(s) failed, e.g. {sorted(failures)[:3]}")
        self.failures = dict(failures)


def _error_code(response: Any) -> str:
    try:
        return str(response.json()["error"]["code"])
    except (ValueError, KeyError, TypeError):
        return f"HTTP_{response.status_code}"


@dataclass
class _Capture:
    files: dict[str, Any] = field(default_factory=dict)
    unavailable: dict[str, str] = field(default_factory=dict)
    failures: dict[str, str] = field(default_factory=dict)

    def error(self, key: str, response: Any) -> None:
        code = _error_code(response)
        target = self.unavailable if code in EXPECTED_UNAVAILABLE else self.failures
        target[key] = code


def requests_to_capture(regions: list[str], variables_by_region: dict[str, list[str]] | None = None) -> list[tuple[str, dict]]:
    """Every request per region, using the variables each region actually holds (catalogue imports included)."""
    items: list[tuple[str, dict]] = [("/health", {}), ("/variables", {}), ("/regions", {}), ("/meta/sources", {})]
    for region in regions:
        variables = (variables_by_region or {}).get(region, list(VARIABLES))
        for variable in variables:
            items.append(("/timeseries", {"region_id": region, "variable": variable, "frequency": "month"}))
            for what in ("series", "trend", "anomalies"):
                items.append(("/export/csv", {"region_id": region, "variable": variable, "what": what}))
        contract = [v for v in VARIABLES if v in variables]  # anomalies exist for rainfall/AOD only (contract G)
        for variable in (*contract, *(["both"] if len(contract) == 2 else [])):
            items.append(("/anomalies", {"region_id": region, "variable": variable}))
        items += [("/interaction", {"region_id": region, "season": s}) for s in INTERACTION_SEASONS]
        items += [("/rainfall/indicators", {"region_id": region, "indicator": i, "season": s})
                  for i in INDICATORS for s in INDICATOR_SEASONS]
    return items


def url_for(path: str, params: dict) -> str:
    return f"/api/v1{path}" + (f"?{urlencode(params)}" if params else "")


def file_name(path: str, params: dict, suffix: str) -> str:
    stem = "_".join(str(v) for v in params.values()) or "index"
    return f"api/v1/{path.strip('/')}/{stem}{suffix}"


def _selections(files: dict[str, Any], regions: list[str]) -> dict[str, list]:
    selections: dict[str, list] = {"regions": regions}
    for name, (path, keys) in SELECTION_KEYS.items():
        prefix = f"/api/v1{path}?"
        selections[name] = [{k: dict(parse_qsl(url[len(prefix):]))[k] for k in keys}
                            for url in files if url.startswith(prefix)]
    selections["reports"] = [entry["file"] for key, entry in files.items() if key.startswith("report:")]
    return selections


def _capture_api(client: TestClient, out: Path, regions: list[str], capture: _Capture,
                 variables_by_region: dict[str, list[str]] | None = None) -> None:
    for path, params in requests_to_capture(regions, variables_by_region):
        url = url_for(path, params)
        response = client.get(url)
        if response.status_code != 200:
            capture.error(url, response)
            continue
        is_csv = response.headers["content-type"].startswith("text/csv")
        relative = file_name(path, params, ".csv" if is_csv else ".json")
        (out / relative).parent.mkdir(parents=True, exist_ok=True)
        (out / relative).write_bytes(response.content)
        capture.files[url] = {"file": relative, "content_type": response.headers["content-type"]}


def _save_reports(client: TestClient, out: Path, regions: list[str], capture: _Capture,
                  variables_by_region: dict[str, list[str]] | None = None) -> None:
    for region in regions:
        key = f"report:{region}"
        held = (variables_by_region or {}).get(region, list(VARIABLES))
        contract = [v for v in VARIABLES if v in held]
        body = {"region_id": region, "variables": contract or held[:1], "start": "2003-01", "end": "2024-12",
                "season": "all",
                "include": ["trend", "anomalies", "interaction", "indicators"] if len(contract) == 2 else ["trend"]}
        created = client.post("/api/v1/report", json=body)
        if created.status_code != 200:
            capture.error(key, created)
            continue
        pdf = client.get(created.json()["result"]["url"])
        if pdf.status_code != 200 or not pdf.content.startswith(b"%PDF"):
            capture.error(key, pdf)
            continue
        target = out / "reports" / f"{region}.pdf"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(pdf.content)
        capture.files[key] = {"file": f"reports/{region}.pdf", "content_type": "application/pdf"}


def _publish(staging: Path, out: Path) -> None:
    """Swap the finished staging folder in; the old snapshot is deleted only after the swap."""
    retired = Path(tempfile.mkdtemp(prefix=f".{out.name}-old-", dir=out.parent))
    if out.exists():
        out.rename(retired / "previous")
    staging.rename(out)
    shutil.rmtree(retired)


def export_snapshot(out: Path = DEFAULT_OUT, *, require_real: bool = False, app: Any = None) -> dict:
    """Build the snapshot in a staging folder and swap it in only when every response is usable.

    Raises SnapshotRefused (--require-real on non-real data) or SnapshotFailed (an error other
    than "not available"). In both cases the previous snapshot at ``out`` is left untouched.
    """
    with TestClient(app or create_app(), raise_server_exceptions=False) as client:
        health = client.get("/api/v1/health").json()
        if require_real and (health["data_status"] != "real" or health["data_version"].upper().startswith("MOCK")):
            raise SnapshotRefused(f"refusing a real snapshot: data_status={health['data_status']}, "
                                  f"data_version={health['data_version']}")
        region_list = client.get("/api/v1/regions").json()["result"]["regions"]
        regions = [r["region_id"] for r in region_list]
        variables_by_region = {r["region_id"]: r["variables"] for r in region_list}
        out.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{out.name}-new-", dir=out.parent))
        try:
            staging.chmod(0o755)
            capture = _Capture()
            _capture_api(client, staging, regions, capture, variables_by_region)
            _save_reports(client, staging, regions, capture, variables_by_region)
            if capture.failures:
                raise SnapshotFailed(capture.failures)
            manifest = {"data_status": health["data_status"], "data_version": health["data_version"],
                        "contract_version": health["contract_version"], "generated_at": health["generated_at"],
                        "files": capture.files, "unavailable": capture.unavailable,
                        "selections": _selections(capture.files, regions)}
            (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    _publish(staging, out)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export a static API snapshot (fallback hosting)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--require-real", action="store_true", help="refuse unless the loaded data is real")
    args = parser.parse_args(argv)
    try:
        manifest = export_snapshot(args.out, require_real=args.require_real)
    except SnapshotRefused as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except SnapshotFailed as exc:
        print(f"ERROR: snapshot not written; the previous snapshot in {args.out} (if any) is unchanged. "
              "These requests failed with errors other than 'not available':", file=sys.stderr)
        for key, code in sorted(exc.failures.items()):
            print(f"  {key}: {code}", file=sys.stderr)
        return 1
    print(f"Saved {len(manifest['files'])} files to {args.out} "
          f"({manifest['data_status']}, {manifest['data_version']}); {len(manifest['unavailable'])} unavailable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
