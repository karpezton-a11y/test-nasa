"""Used only when the PDF stack (ReportLab/matplotlib) cannot be imported.

Keeps the same routes so the UI gets REPORT_FAILED (and offers CSV / print)
instead of a crashed app. Imports nothing heavy.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..advanced_schemas import ReportRequest
from ..errors import api_error

router = APIRouter(tags=["reports"])
MESSAGE = "PDF reports are unavailable on this server. Use the CSV download or the printable report page."


@router.post("/report")
def create_report_unavailable(body: ReportRequest) -> None:
    raise api_error("REPORT_FAILED", MESSAGE)


@router.get("/report/{report_id}")
def download_report_unavailable(report_id: str) -> None:
    raise api_error("REPORT_FAILED", MESSAGE)
