"""GET /api/v1/export/csv: download the exact stored numbers as CSV."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from ..openapi_errors import error_responses
from ..schemas import now_ist
from ..services.csv_export import ExportRequest, build_csv_export
from ..services.store import DataStore, get_store

router = APIRouter(tags=["export"])


@router.get(
    "/export/csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "CSV with # metadata header lines"},
               **error_responses("INVALID_REGION", "INVALID_VARIABLE", "INVALID_PERIOD", "INVALID_EXPORT_TYPE",
                                 "PERIOD_TOO_SHORT", "INSUFFICIENT_DATA", "VALIDATION_ERROR", "DATA_NOT_AVAILABLE")},
)
def export_csv(
    request: Request,
    region_id: str = Query(...),
    variable: str = Query(...),
    frequency: str = Query("month"),
    start: str | None = Query(None, description="YYYY-MM"),
    end: str | None = Query(None, description="YYYY-MM"),
    what: str = Query("series", description="series | trend | anomalies"),
    store: DataStore = Depends(get_store),
) -> Response:
    settings = request.app.state.settings
    export = build_csv_export(
        store, ExportRequest(region_id, variable, frequency, start, end, what),
        app_name=settings.app_name, contract_version=settings.contract_version,
        generated_at=now_ist().isoformat(),
    )
    return Response(
        content=export.content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{export.filename}"'},
    )
