"""Audit M5: scripts/smoke_test.py really checks what it claims (run in-process against the mock app)."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.reports.store import ReportFileStore
from scripts import smoke_test
from scripts.smoke_test import GUARDRAIL, check_advanced, check_download, summary

BASE = "http://testserver"


@pytest.fixture
def test_client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def _json(status: int, body: dict) -> httpx.Response:
    return httpx.Response(status, json=body)


def test_every_check_passes_against_the_mock_app(test_client):
    checks = smoke_test.run(BASE, "mock", client=test_client)
    assert [c.name for c in checks if not c.ok] == []
    assert len(checks) == 26 and not any(c.skipped for c in checks)
    assert {"GET /timeseries", "POST /analyze (< 2 s)", "POST /explain"} <= {c.name for c in checks}
    assert sum(c.name.startswith("GET /interaction") for c in checks) == 2  # guardrail checked on both


def test_wrong_data_status_fails(test_client):
    checks = smoke_test.run(BASE, "real", client=test_client)
    assert any(not c.ok and "data_status" in c.detail for c in checks)


def test_a_download_that_is_not_a_pdf_fails(test_client, monkeypatch):
    monkeypatch.setattr(ReportFileStore, "load", lambda self, report_id: b"<html>oops</html>")
    checks = {c.name: c for c in smoke_test.run(BASE, "mock", client=test_client)}
    assert not checks["GET /report/{id}"].ok and "not a PDF" in checks["GET /report/{id}"].detail


def test_pdf_header_check_on_its_own():
    good = httpx.Response(200, content=b"%PDF-1.4 ...", headers={"content-type": "application/pdf"})
    bad = httpx.Response(200, content=b"PK\x03\x04", headers={"content-type": "application/pdf"})
    assert check_download("pdf", good, 0.1, "application/pdf", 10, "mock").ok
    assert not check_download("pdf", bad, 0.1, "application/pdf", 10, "mock").ok


def _interaction(guardrail: str) -> httpx.Response:
    return _json(200, {"data_status": "mock", "result": {"guardrail": guardrail}})


def test_every_interaction_answer_needs_the_exact_guardrail():
    assert check_advanced("i", _interaction(GUARDRAIL), 0.1, "mock", False, path="/interaction").ok
    changed = check_advanced("i", _interaction("Rain causes clean air."), 0.1, "mock", False, path="/interaction")
    assert not changed.ok and "guardrail" in changed.detail


NOT_AVAILABLE = {"error": {"code": "DATA_NOT_AVAILABLE", "message": "m", "details": {}}}
ROUTE_MISSING = {"error": {"code": "NOT_FOUND", "message": "No such endpoint.", "details": {}}}


def test_not_available_is_skip_only_with_the_flag_and_a_missing_route_always_fails():
    allowed = check_advanced("a", _json(404, NOT_AVAILABLE), 0.1, "real", True)
    assert allowed.ok and allowed.skipped and allowed.label == "SKIP"
    assert not check_advanced("a", _json(404, NOT_AVAILABLE), 0.1, "real", False).ok
    assert not check_advanced("a", _json(404, ROUTE_MISSING), 0.1, "real", True).ok


def test_summary_warns_when_checks_were_skipped():
    checks = [smoke_test.Check("x", True, 0.1, "ok"),
              smoke_test.Check("a", True, 0.1, "not available yet", skipped=True)]
    text = "\n".join(summary(checks))
    assert "1/2 checks passed, 1 skipped, 0 failed" in text
    assert "WARNING" in text and "--allow-unavailable" in text
    assert "SKIP" in text.splitlines()[1]


def test_main_exit_code_follows_failures(monkeypatch, capsys):
    monkeypatch.setattr(smoke_test, "run", lambda *a, **k: [smoke_test.Check("x", False, 0.1, "status 500")])
    assert smoke_test.main([BASE]) == 1
    monkeypatch.setattr(smoke_test, "run", lambda *a, **k: [smoke_test.Check("x", True, 0.1, "ok")])
    assert smoke_test.main([BASE, "--expect-status", "real"]) == 0
    assert "1/1 checks passed" in capsys.readouterr().out
