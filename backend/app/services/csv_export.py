"""CSV export builder (DOCX section 8.2). No PDF imports here: CSV must work alone.

File layout:
    # <APP_NAME> export | MOCK | data_status=... | region=... | ...   (metadata, every line starts with '#')
    <column header>
    <rows>

Readable with ``pandas.read_csv(path, comment="#")``. Encoding rules:
- missing value -> empty cell (never 0, never -9999, never "null"/"nan"); real 0 stays 0
- floats are written with Python's shortest round-trip repr (no rounding)
- nested trend fields -> compact JSON in one quoted cell (decision C-1)
- text cells: pandas treats '#' anywhere as a comment start, so '\\' is written as '\\\\'
  and '#' as '\\u0023'. Cell encoding and the matching decoder (``read_export``) live in
  csv_codec.py, which is standard-library only and can be used without the backend.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from typing import Any, Iterable

from pydantic import BaseModel

from ..advanced_schemas import AnomalyResult
from .csv_codec import decode_text_cell, encode_cell, encode_header_value  # noqa: F401 (re-export)
from ..errors import api_error
from ..schemas import Period, Region, SourceInfo, TimeSeries, TrendResult
from .advanced import anomalies_for, find_region
from .store import DataStore, DatasetInfo
from .validation import (
    FREQUENCIES, require_choice, require_coverage, require_daily_limit, require_min_years, resolve_period,
    slice_series,
)

EXPORT_TYPES = ("series", "trend", "anomalies")
SERIES_COLUMNS = ["date", "region_id", "variable", "frequency", "value", "unit", "source_id", "valid_fraction", "qc_flag"]
TREND_COLUMNS = list(TrendResult.model_fields)
ANOMALY_COLUMNS = ["region_id", "variable", "source_id", "unit", "date", "value", "baseline_median", "score",
                   "score_type", "category", "valid_fraction", "qc_flag", "note"]


@dataclass(frozen=True)
class ExportRequest:
    region_id: str
    variable: str
    frequency: str
    start: str | None
    end: str | None
    what: str


@dataclass(frozen=True)
class CsvExport:
    filename: str
    content: bytes


# ----------------------------------------------------------------- cell encoding


def _cell(value: Any) -> str:
    """Pydantic objects become plain JSON data; everything else goes straight to the codec."""
    return encode_cell(value.model_dump(mode="json") if isinstance(value, BaseModel) else value)


def _header_line(parts: Iterable[str]) -> str:
    return "# " + " | ".join(encode_header_value(part) for part in parts)


# ----------------------------------------------------------------- validation (shared helpers only)


def _validate(store: DataStore, req: ExportRequest) -> tuple[Region, Period]:
    region = find_region(store, req.region_id)
    require_choice(req.variable, region.variables, "INVALID_VARIABLE", "variable")
    if req.frequency not in FREQUENCIES:
        raise api_error("VALIDATION_ERROR", "frequency must be month or day.",
                        {"fields": [{"loc": ["query", "frequency"], "msg": "must be month or day", "type": "enum"}]})
    require_choice(req.what, EXPORT_TYPES, "INVALID_EXPORT_TYPE", "what")
    if req.what != "series" and req.frequency != "month":
        raise api_error("VALIDATION_ERROR", "Trend and anomaly exports use monthly data (frequency=month).",
                        {"fields": [{"loc": ["query", "frequency"], "msg": "must be month for this export", "type": "enum"}]})
    period = resolve_period(req.start, req.end, region.period_available)
    if req.frequency == "day":
        require_daily_limit(period)
    return region, period


# ----------------------------------------------------------------- builders


def _source(store: DataStore, source_id: str) -> SourceInfo | None:
    return next((s for s in store.sources() if s.source_id == source_id), None)


def _metadata_lines(app_name: str, info: DatasetInfo, contract_version: str, generated_at: str,
                    req: ExportRequest, period: Period, source_id: str, store: DataStore,
                    units: str, extra: Iterable[str]) -> list[str]:
    status = info.data_status
    source = _source(store, source_id)
    product = source.product if source else "unknown source"
    doi = (source.doi if source and source.doi else
           "not available (MOCK data)" if status == "mock" else "not recorded")
    lines = [
        [f"{app_name} export", "MOCK" if status == "mock" else "REAL", f"data_status={status}",
         f"region={req.region_id}", f"variable={req.variable}", f"frequency={req.frequency}", f"what={req.what}",
         f"start={period.start}", f"end={period.end}"],
        [f"source={product}", f"source_id={source_id}", f"doi={doi}", f"data_version={info.data_version}"],
        [f"units: {units}", "missing values are empty cells (never zero)"],
        *extra,
        [f"contract_version={contract_version}", f"generated_at={generated_at}"],
    ]
    return [_header_line(parts) for parts in lines]


def _units(variable: str, unit: str) -> str:
    return f"{variable} {unit}" + (" (dimensionless; shown as unitless)" if unit == "1" else "")


def _series_rows(series: TimeSeries) -> list[list[str]]:
    return [[_cell(p.date.isoformat()), _cell(series.region_id), _cell(series.variable), _cell(series.frequency),
             _cell(p.value), _cell(series.unit), _cell(series.source_id), _cell(p.valid_fraction), _cell(p.qc_flag)]
            for p in series.points]


def _trend_rows(trend: TrendResult) -> list[list[str]]:
    wire = trend.model_dump(mode="json")  # same serialisation as the API (ISO datetimes, plain JSON)
    return [[_cell(wire[name]) for name in TREND_COLUMNS]]


def _anomaly_rows(result: AnomalyResult) -> list[list[str]]:
    return [[_cell(result.region_id), _cell(result.variable), _cell(result.source_id), _cell(result.unit),
             _cell(a.date.isoformat()), _cell(a.value), _cell(a.baseline_median), _cell(a.score),
             _cell(a.score_type), _cell(a.category), _cell(a.valid_fraction), _cell(a.qc_flag), _cell(a.note)]
            for a in result.anomalies]


def _anomaly_header(result: AnomalyResult) -> list[list[str]]:
    b, t = result.baseline, result.thresholds
    return [
        [f"baseline: start={b.start}", f"end={b.end}", f"method={b.method}", f"statistic={b.statistic}",
         f"detrended={'true' if b.detrended else 'false'}"],
        [f"thresholds: high={t.high!r}", f"low={t.low!r}",
         f"min_valid_fraction={_cell(t.min_valid_fraction) or 'none'}",
         f"dry_suppression_median={_cell(t.dry_suppression_median) or 'none'}"],
        [f"result_id={result.result_id}"],
    ]


def _select(store: DataStore, req: ExportRequest,
            period: Period) -> tuple[list[str], list[list[str]], str, str, list[list[str]]]:
    """Returns columns, rows, source_id, units text, extra header lines."""
    series = store.series(req.region_id, req.variable, req.frequency)
    if req.what == "series":
        require_coverage(series, period)  # decision C-2: 70% gate for CSV series export
        sliced = slice_series(series, period)
        return SERIES_COLUMNS, _series_rows(sliced), series.source_id, _units(req.variable, series.unit), []
    if req.what == "trend":
        require_min_years(period)
        require_coverage(series, period)
        trend = store.trend(req.region_id, req.variable, period, "all")
        units = f"{_units(req.variable, series.unit)} | slopes in {trend.slope_unit}"
        return TREND_COLUMNS, _trend_rows(trend), trend.source_id, units, [
            ["nested fields (period, method, slope_ci, ols_ci, limitations, evidence) are JSON in one cell"]]
    result = anomalies_for(store, req.region_id, req.variable, period.start, period.end, False)
    return (ANOMALY_COLUMNS, _anomaly_rows(result), result.source_id, _units(req.variable, result.unit),
            _anomaly_header(result))


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", text).strip("-") or "export"


def build_csv_export(store: DataStore, req: ExportRequest, *, app_name: str, contract_version: str,
                     generated_at: str) -> CsvExport:
    """Validate first, build the whole file in memory, then return it (no partial downloads)."""
    _, period = _validate(store, req)
    columns, rows, source_id, units, extra = _select(store, req, period)
    buffer = io.StringIO()
    buffer.write("\n".join(_metadata_lines(app_name, store.info, contract_version, generated_at, req, period,
                                           source_id, store, units, extra)) + "\n")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    filename = "_".join([_slug(app_name), req.region_id, req.variable, req.frequency, req.what,
                         period.start, period.end]) + ".csv"
    return CsvExport(filename=filename, content=buffer.getvalue().encode("utf-8"))
