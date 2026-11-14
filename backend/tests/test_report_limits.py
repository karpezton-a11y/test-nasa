"""Audit M1: PDF generation is limited (concurrency, per-client rate) and saved reports are cleaned up."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.errors import ApiError
from app.main import create_app
from app.reports.store import ReportFileStore
from app.services.rate_limit import RequestLimiter

API = "/api/v1"
REPORT_BODY = {"region_id": "IGP", "variables": ["aod"], "start": "2003-01", "end": "2024-12",
               "season": "all", "include": ["trend"]}


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


# ----------------------------------------------------------------- the limiter on its own


def test_rate_limit_counts_per_client_and_frees_up_after_the_window():
    clock = FakeClock()
    limiter = RequestLimiter(max_concurrent=2, max_per_window=2, window_s=60, clock=clock)
    for _ in range(2):
        with limiter.slot("1.1.1.1"):
            pass
    with pytest.raises(ApiError) as limited:
        with limiter.slot("1.1.1.1"):
            pass
    assert limited.value.code == "RATE_LIMITED" and limited.value.http_status == 429
    assert limited.value.details["retry_after_s"] == 60
    with limiter.slot("2.2.2.2"):  # another client is not affected
        pass
    clock.now += 60.5
    with limiter.slot("1.1.1.1"):
        pass


def test_busy_when_all_slots_are_taken_and_a_busy_request_uses_no_quota():
    limiter = RequestLimiter(max_concurrent=1, max_per_window=1, window_s=60, clock=FakeClock())
    with limiter.slot("1.1.1.1"):
        with pytest.raises(ApiError) as busy:
            with limiter.slot("2.2.2.2"):
                pass
    assert busy.value.code == "REPORT_BUSY" and busy.value.http_status == 503
    assert busy.value.details["retry_after_s"] >= 1
    with limiter.slot("2.2.2.2"):  # the refused attempt did not count against 2.2.2.2
        pass


def test_a_failing_request_releases_its_slot():
    limiter = RequestLimiter(max_concurrent=1, max_per_window=10, window_s=60, clock=FakeClock())
    with pytest.raises(RuntimeError):
        with limiter.slot("1.1.1.1"):
            raise RuntimeError("PDF failed")
    with limiter.slot("1.1.1.1"):
        pass


def test_forgotten_clients_are_dropped_so_memory_stays_small():
    clock = FakeClock()
    limiter = RequestLimiter(max_concurrent=1, max_per_window=5, window_s=60, clock=clock)
    for i in range(50):
        with limiter.slot(f"10.0.0.{i}"):
            pass
    clock.now += 61
    with limiter.slot("10.0.1.1"):
        pass
    assert limiter.tracked_clients() == 1


@pytest.mark.parametrize("kwargs", [{"max_concurrent": 0}, {"max_per_window": 0}, {"window_s": 0}])
def test_limits_must_be_positive(kwargs):
    with pytest.raises(ValueError):
        RequestLimiter(**{"max_concurrent": 1, "max_per_window": 1, "window_s": 1, **kwargs})


# ----------------------------------------------------------------- POST /report uses it


@pytest.fixture
def app_client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield app, c


def test_report_route_returns_429_with_retry_after(app_client):
    app, c = app_client
    app.state.report_limiter = RequestLimiter(max_concurrent=2, max_per_window=1, window_s=60)
    assert c.post(f"{API}/report", json=REPORT_BODY).status_code == 200
    response = c.post(f"{API}/report", json=REPORT_BODY)
    assert (response.status_code, response.json()["error"]["code"]) == (429, "RATE_LIMITED")
    assert int(response.headers["retry-after"]) >= 1


def test_report_route_returns_503_when_busy(app_client):
    app, c = app_client
    limiter = RequestLimiter(max_concurrent=1, max_per_window=10, window_s=60)
    app.state.report_limiter = limiter
    with limiter.slot("someone-else"):
        response = c.post(f"{API}/report", json=REPORT_BODY)
    assert (response.status_code, response.json()["error"]["code"]) == (503, "REPORT_BUSY")
    assert response.headers["retry-after"].isdigit()
    assert c.post(f"{API}/report", json=REPORT_BODY).status_code == 200  # slot released afterwards


def test_default_limits_allow_normal_use(client):
    for _ in range(3):
        assert client.post(f"{API}/report", json=REPORT_BODY).status_code == 200


# ----------------------------------------------------------------- saved reports are cleaned up


def _fake_report(folder: Path, index: int, age_s: float) -> Path:
    path = folder / f"rpt_{index:032x}.pdf"
    path.write_bytes(b"%PDF-test")
    stamp = time.time() - age_s
    os.utime(path, (stamp, stamp))
    return path


def test_saving_a_report_deletes_reports_older_than_the_max_age(tmp_path):
    old = _fake_report(tmp_path, 1, age_s=2 * 3600)
    recent = _fake_report(tmp_path, 2, age_s=60)
    unrelated = tmp_path / "notes.txt"
    unrelated.write_text("keep me", encoding="utf-8")
    files = ReportFileStore(tmp_path, max_age_s=3600, max_files=100)
    new_id = files.new_id()
    files.save(new_id, b"%PDF-new")
    assert not old.exists() and recent.exists() and unrelated.exists()
    assert files.load(new_id) == b"%PDF-new"


def test_saving_keeps_at_most_max_files_newest_first(tmp_path):
    paths = [_fake_report(tmp_path, i, age_s=100 - i) for i in range(5)]  # index 4 is the newest
    files = ReportFileStore(tmp_path, max_age_s=3600, max_files=3)
    new_id = files.new_id()
    files.save(new_id, b"%PDF-new")
    kept = sorted(p.name for p in tmp_path.glob("rpt_*.pdf"))
    assert kept == sorted([paths[3].name, paths[4].name, f"{new_id}.pdf"])


def test_a_report_deleted_by_cleanup_is_reported_as_not_found(tmp_path):
    files = ReportFileStore(tmp_path)
    report_id = files.new_id()
    with pytest.raises(ApiError) as missing:
        files.load(report_id)
    assert missing.value.code == "REPORT_NOT_FOUND"


def test_error_examples_for_frontend_use_the_live_messages():
    from app.config import REPO_ROOT
    from app.services.rate_limit import BUSY_MESSAGE, RATE_MESSAGE

    examples = REPO_ROOT / "docs" / "examples"
    for code, message in (("REPORT_BUSY", BUSY_MESSAGE), ("RATE_LIMITED", RATE_MESSAGE)):
        body = json.loads((examples / f"error_{code}.json").read_text(encoding="utf-8"))
        assert body["error"]["message"] == message and "retry_after_s" in body["error"]["details"]
