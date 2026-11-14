"""Task 11: static snapshot fallback (scripts/export_static_snapshot.py)."""

from __future__ import annotations

import functools
import json
import threading
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from app.main import create_app
from app.services.store import MockStore
from scripts import export_static_snapshot
from scripts.export_static_snapshot import SnapshotFailed, SnapshotRefused, export_snapshot


@pytest.fixture
def exported(settings, tmp_path) -> tuple[Path, dict]:
    out = tmp_path / "snapshot"
    return out, export_snapshot(out, app=create_app(settings))


def test_manifest_lists_every_file_and_the_supported_selections(exported):
    out, manifest = exported
    assert manifest["data_status"] == "mock" and manifest["data_version"].startswith("MOCK-")
    for url, entry in manifest["files"].items():
        path = out / entry["file"]
        assert path.is_file(), url
        if entry["content_type"].startswith("application/json"):
            body = json.loads(path.read_text(encoding="utf-8"))
            assert (body["data_status"], body["data_version"]) == (manifest["data_status"], manifest["data_version"])
        elif entry["content_type"].startswith("text/csv"):
            assert path.read_text(encoding="utf-8").startswith("# TrendTrace export | MOCK")
        else:
            assert path.read_bytes().startswith(b"%PDF")
    selections = manifest["selections"]
    assert selections["regions"] == ["IGP", "TN"]
    assert len(selections["indicators"]) == 2 * 3 * 3
    assert {"region_id": "IGP", "variable": "both"} in selections["anomalies"]
    assert selections["reports"] == ["reports/IGP.pdf", "reports/TN.pdf"]


def test_unavailable_selections_are_listed_not_faked(exported):
    _, manifest = exported
    assert manifest["unavailable"]["/api/v1/interaction?region_id=IGP&season=MAM"] == "DATA_NOT_AVAILABLE"
    assert all(url not in manifest["files"] for url in manifest["unavailable"])
    assert "/api/v1/timeseries?region_id=IGP&variable=aod&frequency=month" in manifest["files"]


def test_snapshot_is_self_contained_and_served_by_a_plain_static_server(exported):
    out, manifest = exported
    for entry in manifest["files"].values():
        if not entry["content_type"].startswith("application/pdf"):
            text = (out / entry["file"]).read_text(encoding="utf-8")
            assert "localhost" not in text and "onrender.com" not in text and "127.0.0.1" not in text
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(out))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.RequestHandlerClass.log_message = lambda *args: None
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        served = json.loads(urllib.request.urlopen(f"{base}/manifest.json").read())
        entry = served["files"]["/api/v1/interaction?region_id=IGP&season=JJAS"]
        body = json.loads(urllib.request.urlopen(f"{base}/{entry['file']}").read())
        assert body["result"]["guardrail"].startswith("Association only.")
    finally:
        server.shutdown()


def _leftover_staging(parent: Path) -> list[str]:
    return [p.name for p in parent.iterdir() if p.name.startswith(".snapshot")]


def test_server_errors_fail_the_snapshot_and_keep_the_previous_one(settings, tmp_path, monkeypatch):
    out = tmp_path / "snapshot"
    out.mkdir()
    (out / "previous.txt").write_text("last good snapshot", encoding="utf-8")

    def crash(self, region_id, season):
        raise RuntimeError("bug in the interaction loader")

    monkeypatch.setattr(MockStore, "interaction", crash)
    with pytest.raises(SnapshotFailed) as failed:
        export_snapshot(out, app=create_app(settings))
    failures = failed.value.failures
    assert failures["/api/v1/interaction?region_id=IGP&season=JJAS"] == "INTERNAL_ERROR"
    assert failures["report:IGP"] == "INTERNAL_ERROR"  # the PDF needs the interaction result too
    assert "/api/v1/interaction?region_id=IGP&season=MAM" in failures  # a crash is never "not available yet"
    assert (out / "previous.txt").read_text(encoding="utf-8") == "last good snapshot"
    assert not (out / "manifest.json").exists() and _leftover_staging(tmp_path) == []


def test_rerun_replaces_the_old_snapshot_only_when_complete(settings, tmp_path):
    out = tmp_path / "snapshot"
    out.mkdir()
    (out / "stale.json").write_text("{}", encoding="utf-8")
    manifest = export_snapshot(out, app=create_app(settings))
    assert not (out / "stale.json").exists()
    assert json.loads((out / "manifest.json").read_text(encoding="utf-8")) == manifest
    assert _leftover_staging(tmp_path) == []


def test_command_exits_nonzero_and_lists_every_failure(monkeypatch, capsys):
    def failing(*args, **kwargs):
        raise SnapshotFailed({"/api/v1/interaction?region_id=IGP&season=JJAS": "INTERNAL_ERROR"})

    monkeypatch.setattr(export_static_snapshot, "export_snapshot", failing)
    assert export_static_snapshot.main([]) == 1
    err = capsys.readouterr().err
    assert "/api/v1/interaction?region_id=IGP&season=JJAS: INTERNAL_ERROR" in err
    assert "previous snapshot" in err


def test_real_snapshot_mode_refuses_mock_data_and_writes_nothing(settings, tmp_path):
    out = tmp_path / "snapshot"
    with pytest.raises(SnapshotRefused, match="data_status=mock"):
        export_snapshot(out, require_real=True, app=create_app(settings))
    assert not out.exists()
