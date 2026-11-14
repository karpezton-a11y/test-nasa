#!/usr/bin/env python
"""Smoke-test the merged core and advanced API against a running server.

    python scripts/smoke_test.py http://localhost:8000
    python scripts/smoke_test.py https://<your-service>.onrender.com --expect-status mock

Checks HTTP status, content type, data_status, the error format, and timings.
Targets: light endpoints < 1 s (warm), PDF report < 10 s. A free host that was
asleep needs up to about a minute for the first request; that warm-up is timed
separately and not counted against the targets.
Exit code 0 = all checks passed.

With --allow-unavailable, an advanced endpoint that answers DATA_NOT_AVAILABLE is marked SKIP (not PASS)
and the summary warns; a missing route (NOT_FOUND) or any other error still fails. Every /interaction
answer must carry the guardrail, and the downloaded report must really be a PDF (audit M5).
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from typing import Callable

import httpx

LIGHT_TARGET_S = 1.0
PDF_TARGET_S = 10.0
CSV_PARAMS = {"region_id": "IGP", "variable": "aod"}
ADVANCED_REQUESTS = [
    ("/anomalies", {"region_id": "IGP", "variable": "both", "start": "2024-01", "end": "2024-12"}),
    ("/anomalies", {"region_id": "TN", "variable": "rainfall", "start": "2024-01", "end": "2024-12"}),
    ("/interaction", {"region_id": "TN", "season": "OND"}),
    ("/interaction", {"region_id": "IGP", "season": "JJAS"}),
    ("/rainfall/indicators", {"region_id": "IGP", "indicator": "heavy_rain_share", "season": "annual"}),
]
GUARDRAIL = "Association only. AOD is retrieved in clear skies, so rainy days are under-sampled."
REPORT_BODY = {"region_id": "IGP", "variables": ["rainfall", "aod"], "start": "2003-01", "end": "2024-12",
               "season": "all", "include": ["trend", "anomalies", "interaction", "indicators"],
               "include_ai_summary": False}


PDF_MAGIC = b"%PDF-"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    seconds: float
    detail: str
    skipped: bool = False

    @property
    def label(self) -> str:
        return "FAIL" if not self.ok else ("SKIP" if self.skipped else "PASS")


def timed(call: Callable[[], httpx.Response]) -> tuple[httpx.Response, float]:
    started = time.perf_counter()
    response = call()
    return response, time.perf_counter() - started


def check_json(name: str, response: httpx.Response, seconds: float, expect: str, target: float) -> Check:
    problems = []
    if response.status_code != 200:
        problems.append(f"status {response.status_code}")
    elif response.json().get("data_status") != expect:
        problems.append(f"data_status {response.json().get('data_status')!r} != {expect!r}")
    if seconds > target:
        problems.append(f"slow ({seconds:.2f}s > {target}s)")
    return Check(name, not problems, seconds, "; ".join(problems) or "ok")


def check_download(name: str, response: httpx.Response, seconds: float, mime: str, target: float,
                   expect: str) -> Check:
    problems = []
    if response.status_code != 200 or not response.headers.get("content-type", "").startswith(mime):
        problems.append(f"status {response.status_code} / {response.headers.get('content-type')}")
    elif mime == "text/csv" and f"data_status={expect}" not in response.text.splitlines()[0]:
        problems.append("CSV header lacks the expected data_status")
    elif mime == "application/pdf" and not response.content.startswith(PDF_MAGIC):
        problems.append("body is not a PDF (no %PDF- header)")
    if seconds > target:
        problems.append(f"slow ({seconds:.2f}s > {target}s)")
    return Check(name, not problems, seconds, "; ".join(problems) or "ok")


def _not_available(response: httpx.Response) -> bool:
    return (response.status_code == 404
            and response.json().get("error", {}).get("code") == "DATA_NOT_AVAILABLE")


def check_advanced(name: str, response: httpx.Response, seconds: float, expect: str, allow_unavailable: bool,
                   path: str = "") -> Check:
    """Real mode before H7/H9 may answer DATA_NOT_AVAILABLE: SKIP only with --allow-unavailable.

    Every /interaction answer must carry the exact association-only guardrail.
    """
    if allow_unavailable and _not_available(response):
        return Check(name, True, seconds, "not available yet (allowed by --allow-unavailable)", skipped=True)
    check = check_json(name, response, seconds, expect, LIGHT_TARGET_S)
    if check.ok and path == "/interaction" and response.json()["result"].get("guardrail") != GUARDRAIL:
        return Check(name, False, seconds, "guardrail missing or changed")
    return check


def check_error(name: str, response: httpx.Response, seconds: float, status: int, code: str) -> Check:
    body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    actual = body.get("error", {}).get("code")
    ok = response.status_code == status and actual == code and set(body) == {"error"}
    return Check(name, ok, seconds, "ok" if ok else f"got {response.status_code} {actual}")


def run(base: str, expect: str, allow_unavailable: bool = False, client: httpx.Client | None = None) -> list[Check]:
    """``client`` lets tests pass a FastAPI TestClient (base ``http://testserver``)."""
    if client is not None:
        return _run_checks(client, base, expect, allow_unavailable)
    with httpx.Client(timeout=90.0) as own_client:
        return _run_checks(own_client, base, expect, allow_unavailable)


Get = Callable[..., httpx.Response]


def _light_checks(get: Get, api: str, expect: str) -> list[Check]:
    warm, warm_s = timed(lambda: get(f"{api}/health"))
    checks = [Check("warm-up /health (may include cold start)", warm.status_code == 200, warm_s,
                    f"status {warm.status_code}")]
    for path in ("/health", "/variables", "/regions", "/meta/sources"):
        response, seconds = timed(lambda p=path: get(f"{api}{p}"))
        checks.append(check_json(f"GET {path}", response, seconds, expect, LIGHT_TARGET_S))
    return checks


def _advanced_checks(get: Get, api: str, expect: str, allow_unavailable: bool) -> list[Check]:
    checks = []
    for path, params in ADVANCED_REQUESTS:
        response, seconds = timed(lambda p=path, q=params: get(f"{api}{p}", params=q))
        checks.append(check_advanced(f"GET {path} {'/'.join(params.values())}", response, seconds, expect,
                                     allow_unavailable, path=path))
    response, seconds = timed(lambda: get(f"{api}/rainfall/indicators",
                                          params={"region_id": "IGP", "indicator": "cdd", "season": "annual"}))
    checks.append(check_error("GET /rainfall/indicators bad indicator -> INVALID_INDICATOR", response, seconds,
                              400, "INVALID_INDICATOR"))
    return checks


def _csv_checks(get: Get, api: str, expect: str) -> list[Check]:
    checks = []
    for what in ("series", "trend", "anomalies"):
        response, seconds = timed(lambda w=what: get(f"{api}/export/csv", params={**CSV_PARAMS, "what": w}))
        checks.append(check_download(f"GET /export/csv what={what}", response, seconds, "text/csv",
                                     LIGHT_TARGET_S * 2, expect))
    response, seconds = timed(lambda: get(f"{api}/export/csv", params={"region_id": "XX", "variable": "aod"}))
    checks.append(check_error("GET /export/csv bad region -> INVALID_REGION", response, seconds, 400, "INVALID_REGION"))
    return checks


def _report_checks(client: httpx.Client, base: str, api: str, expect: str) -> list[Check]:
    created, seconds = timed(lambda: client.post(f"{api}/report", json=REPORT_BODY))
    checks = [check_json("POST /report", created, seconds, expect, PDF_TARGET_S)]
    if created.status_code == 200:
        url = base.rstrip("/") + created.json()["result"]["url"]
        response, seconds = timed(lambda: client.get(url))
        checks.append(check_download("GET /report/{id}", response, seconds, "application/pdf", PDF_TARGET_S, expect))
    response, seconds = timed(lambda: client.get(f"{api}/report/abc"))
    checks.append(check_error("GET /report/abc -> INVALID_REPORT_ID", response, seconds, 400, "INVALID_REPORT_ID"))
    return checks


def _core_checks(client: httpx.Client, api: str, expect: str, allow_unavailable: bool) -> list[Check]:
    response, seconds = timed(lambda: client.get(f"{api}/timeseries", params=CSV_PARAMS))
    checks = [check_json("GET /timeseries", response, seconds, expect, 2.0)]
    response, seconds = timed(lambda: client.post(f"{api}/analyze", json={**CSV_PARAMS, "season": "all"}))
    if allow_unavailable and _not_available(response):
        checks.append(Check("POST /analyze", True, seconds, "science/evidence not available yet", skipped=True))
    else:
        checks.append(check_json("POST /analyze (< 2 s)", response, seconds, expect, 2.0))
    if response.status_code == 200:
        rid = response.json()["result"]["result_id"]
        explained, elapsed = timed(lambda: client.post(f"{api}/explain", json={"result_type": "trend", "result_id": rid}))
        checks.append(check_json("POST /explain", explained, elapsed, expect, 17.0))
    return checks


def _insight_checks(client: httpx.Client, api: str, expect: str, allow_unavailable: bool) -> list[Check]:
    """Discovery, research series, any-series analysis, chart detail and scan (trendlib routes)."""
    checks = []
    response, seconds = timed(lambda: client.get(f"{api}/catalog"))
    checks.append(check_json("GET /catalog", response, seconds, expect, 2.0))
    response, seconds = timed(lambda: client.post(f"{api}/discover", json={"place_type": "city", "theme": "air"}))
    checks.append(check_json("POST /discover", response, seconds, expect, 2.0))
    response, seconds = timed(lambda: client.post(f"{api}/analyze/series", json={"research_id": "IGP_aod_annual_mean"}))
    checks.append(check_json("POST /analyze/series (research)", response, seconds, expect, 2.0))
    for name, call in (("POST /analyze/detail (< 2 s)", lambda: client.post(f"{api}/analyze/detail", json={**CSV_PARAMS, "season": "all"})),
                       ("GET /scan", lambda: client.get(f"{api}/scan"))):
        response, seconds = timed(call)
        if allow_unavailable and _not_available(response):
            checks.append(Check(name, True, seconds, "science/evidence not available yet", skipped=True))
        else:
            checks.append(check_json(name, response, seconds, expect, 2.0 if "detail" in name else 10.0))
    return checks


def _run_checks(client: httpx.Client, base: str, expect: str, allow_unavailable: bool) -> list[Check]:
    api = base.rstrip("/") + "/api/v1"
    return [*_light_checks(client.get, api, expect),
            *_core_checks(client, api, expect, allow_unavailable),
            *_insight_checks(client, api, expect, allow_unavailable),
            *_advanced_checks(client.get, api, expect, allow_unavailable),
            *_csv_checks(client.get, api, expect),
            *_report_checks(client, base, api, expect)]


def summary(checks: list[Check]) -> list[str]:
    """Report lines: one per check, the totals, and a warning when anything was skipped."""
    failed = [c for c in checks if not c.ok]
    skipped = [c for c in checks if c.ok and c.skipped]
    lines = [f"{c.label}  {c.seconds:6.2f}s  {c.name}  ({c.detail})" for c in checks]
    lines.append(f"\n{len(checks) - len(failed) - len(skipped)}/{len(checks)} checks passed, "
                 f"{len(skipped)} skipped, {len(failed)} failed")
    if skipped:
        lines.append(f"WARNING: {len(skipped)} advanced endpoint check(s) were NOT tested because the data is not "
                     "available yet. Drop --allow-unavailable after H9 so these are really checked.")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the TrendTrace API")
    parser.add_argument("base_url", help="e.g. http://localhost:8000")
    parser.add_argument("--expect-status", default="mock", choices=["mock", "real"])
    parser.add_argument("--allow-unavailable", action="store_true",
                        help="mark DATA_NOT_AVAILABLE from /anomalies, /interaction, /rainfall/indicators as SKIP "
                             "instead of FAIL (real data before H7/H9)")
    args = parser.parse_args(argv)
    checks = run(args.base_url, args.expect_status, args.allow_unavailable)
    print("\n".join(summary(checks)))
    return 1 if any(not c.ok for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
