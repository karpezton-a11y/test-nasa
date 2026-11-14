"""POST /api/v1/report (create + save a PDF) and GET /api/v1/report/{report_id} (download it).

Importing this module imports ReportLab and matplotlib; main.py falls back to
routers/reports_fallback.py if that import fails, so CSV and the rest still work.
"""

from __future__ import annotations

import logging
from dataclasses import replace

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from ..advanced_schemas import ReportCreated, ReportRequest
from ..errors import ApiError, api_error
from ..openapi_errors import error_responses
from ..schemas import Envelope, now_ist
from ..reports.hooks import ai_summary_for, load_report_texts
from ..reports.pdf import build_pdf
from ..reports.service import assemble_report
from ..reports.store import ReportFileStore
from ..services.rate_limit import RequestLimiter
from ..services.store import DataStore, get_store
from .common import envelope

logger = logging.getLogger("trendtrace.reports")
router = APIRouter(tags=["reports"])
REPORT_FAILED_MESSAGE = "The PDF report could not be created. Use the CSV download or the printable report page."
CREATE_ERRORS = error_responses(
    "INVALID_REGION", "INVALID_VARIABLE", "INVALID_PERIOD", "INVALID_SEASON", "PERIOD_TOO_SHORT",
    "INSUFFICIENT_DATA", "VALIDATION_ERROR", "PAYLOAD_TOO_LARGE", "DATA_NOT_AVAILABLE", "RATE_LIMITED",
    "REPORT_BUSY", "REPORT_FAILED")
DOWNLOAD_ERRORS = error_responses("INVALID_REPORT_ID", "REPORT_NOT_FOUND")


def _client_key(request: Request) -> str:
    """The connecting address. Behind Render's proxy this may be shared by many users (see docs/deploy.md)."""
    return request.client.host if request.client else "unknown"


def _render_and_save(request: Request, store: DataStore, body: ReportRequest, generated_at: str) -> tuple[str, int]:
    settings = request.app.state.settings
    texts = load_report_texts()  # Group 3 methods.md (H9); absent -> "not available" box
    content = assemble_report(store, body, app_name=settings.app_name, contract_version=settings.contract_version,
                              generated_at=generated_at, methods_text=texts.methods,
                              limitations_text=texts.limitations)  # validation errors propagate unchanged
    try:
        content = replace(content, ai_summary=ai_summary_for(content))  # Adrian's hook; None if absent
        artifact = build_pdf(content)
        files = ReportFileStore(settings.reports_dir)
        report_id = files.new_id()
        files.save(report_id, artifact.content)
    except ApiError:
        raise
    except Exception:
        logger.exception("Report generation failed")
        raise api_error("REPORT_FAILED", REPORT_FAILED_MESSAGE) from None
    return report_id, artifact.pages


@router.post("/report", response_model=Envelope[ReportCreated], responses=CREATE_ERRORS)
def create_report(body: ReportRequest, request: Request,
                  store: DataStore = Depends(get_store)) -> Envelope[ReportCreated]:
    limiter: RequestLimiter = request.app.state.report_limiter
    with limiter.slot(_client_key(request)):  # REPORT_BUSY / RATE_LIMITED before any chart is drawn
        generated_at = now_ist()
        report_id, pages = _render_and_save(request, store, body, generated_at.isoformat())
    result = ReportCreated(report_id=report_id, url=f"/api/v1/report/{report_id}", pages=pages,
                           generated_at=generated_at.isoformat())
    return envelope(request, result, generated_at=generated_at, store=store)


@router.get("/report/{report_id}", response_class=Response,
            responses={200: {"content": {"application/pdf": {}}, "description": "The saved PDF"},
                       **DOWNLOAD_ERRORS})
def download_report(report_id: str, request: Request) -> Response:
    settings = request.app.state.settings
    content = ReportFileStore(settings.reports_dir).load(report_id)  # validates the ID first
    return Response(content=content, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{report_id}.pdf"'})


@router.get("/report", include_in_schema=False)
@router.get("/report/", include_in_schema=False)
def report_id_missing() -> None:
    raise api_error("NOT_FOUND", "Add the report ID: /api/v1/report/{report_id}.")
