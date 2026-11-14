#!/usr/bin/env python
"""Generate one sample MOCK Discovery Report into reports/ and print its path + timing.

    python scripts/make_sample_report.py                 # IGP, rainfall + AOD, all sections
    python scripts/make_sample_report.py --region TN --max-seconds 10

Measures the full creation path (store reads + charts + PDF build + atomic write),
the same work POST /api/v1/report does. Exit code 1 if slower than --max-seconds.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.advanced_schemas import ReportRequest  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.reports.pdf import build_pdf  # noqa: E402
from app.reports.service import assemble_report  # noqa: E402
from app.reports.store import ReportFileStore  # noqa: E402
from app.schemas import now_ist  # noqa: E402
from app.services.store import build_store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--region", default="IGP")
    parser.add_argument("--max-seconds", type=float, default=10.0)
    args = parser.parse_args()
    settings = load_settings()
    request = ReportRequest(region_id=args.region, variables=["rainfall", "aod"], start="2003-01", end="2024-12",
                            season="all", include=["trend", "anomalies", "interaction", "indicators"],
                            include_ai_summary=True)
    started = time.perf_counter()
    store = build_store(settings)
    content = assemble_report(store, request, app_name=settings.app_name,
                              contract_version=settings.contract_version, generated_at=now_ist().isoformat())
    artifact = build_pdf(content)
    files = ReportFileStore(settings.reports_dir)
    report_id = files.new_id()
    files.save(report_id, artifact.content)
    elapsed = time.perf_counter() - started
    print(f"{settings.reports_dir / (report_id + '.pdf')}  pages={artifact.pages}  "
          f"data_status={content.data_status}  seconds={elapsed:.2f}")
    if elapsed > args.max_seconds:
        print(f"SLOW: report took longer than {args.max_seconds} s", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
