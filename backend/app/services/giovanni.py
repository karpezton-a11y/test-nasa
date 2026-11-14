"""Parse NASA Giovanni 'Time Series, Area-Averaged' CSV downloads.

Giovanni (https://giovanni.gsfc.nasa.gov) can export an area-averaged time series for
almost every variable the challenge names (MODIS, OMI, AIRS, GPM, MERRA-2, GLDAS) with
no code. This parser turns that file into dates/values for trendlib, so a student can
test any variable in any region today. Fill values and NaN stay missing; nothing is filled.

Typical file::

    Title:,Time Series, Area-Averaged of Precipitation monthly 0.1 deg. [GPM GPM_3IMERGM v07] mm/hr over 2003-Jan - 2024-Dec, Region 76E, 24N, 88E, 30N
    User Start Date:,2003-01-01T00:00:00Z
    Bounding Box:,"76,24,88,30"
    Fill Value (mean_GPM_3IMERGM_07_precipitation):,-9999.9

    time,mean_GPM_3IMERGM_07_precipitation
    2003-01-01,0.0243
"""
from __future__ import annotations

import calendar
import csv
import io
import math
import re
from dataclasses import dataclass, field
from datetime import date

from ..errors import api_error

MAX_ROWS = 2000

# Unit conversions a student commonly needs; each is exact arithmetic on calendar days.
CONVERSIONS = {
    "none": ("", lambda v, d: v),
    "mmhr_to_mm_month": ("mm/month", lambda v, d: v * 24 * calendar.monthrange(d.year, d.month)[1]),
    "mmday_to_mm_month": ("mm/month", lambda v, d: v * calendar.monthrange(d.year, d.month)[1]),
    "kgm2s_to_mm_month": ("mm/month", lambda v, d: v * 86400 * calendar.monthrange(d.year, d.month)[1]),
    "k_to_c": ("degC", lambda v, d: v - 273.15),
}


@dataclass
class GiovanniSeries:
    dates: list[date]
    values: list[float | None]
    variable_id: str
    unit: str
    title: str
    bbox: list[float] | None
    frequency: str
    metadata: dict[str, str] = field(default_factory=dict)


def native_unit(variable_id: str) -> str:
    """Native unit of a known Giovanni data ID from data/catalog (e.g. IMERG monthly -> mm/hr)."""
    from .catalog import load_catalog
    entry = next((v for v in load_catalog()["variables"] if v.get("giovanni_id") == variable_id), None)
    return entry["native_unit"].split(" ")[0] if entry else ""


def _bad(message: str) -> None:
    raise api_error("VALIDATION_ERROR", message, {"param": "giovanni_csv"})


def _parse_date(text: str) -> date:
    text = text.strip()
    m = re.match(r"^(\d{4})-(\d{2})(?:-(\d{2}))?", text)
    if not m:
        _bad(f"Unrecognised date {text[:20]!r} in Giovanni CSV.")
    return date(int(m[1]), int(m[2]), int(m[3] or 1))


def parse_giovanni_csv(text: str, conversion: str = "none") -> GiovanniSeries:
    if conversion not in CONVERSIONS:
        _bad(f"Unknown conversion; choose one of {', '.join(CONVERSIONS)}.")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    meta: dict[str, str] = {}
    fills: set[float] = set()
    header_at = None
    for i, line in enumerate(lines):
        if re.match(r"^\s*\"?time\"?\s*,", line, flags=re.IGNORECASE):
            header_at = i
            break
        if ":," in line:
            key, _, value = line.partition(":,")
            key, value = key.strip().strip('"'), value.strip().strip('"')
            meta[key] = value
            if key.lower().startswith("fill value"):
                try:
                    fills.add(float(value))
                except ValueError:
                    pass
    if header_at is None:
        _bad("No 'time,<variable>' header found. Download 'Time Series, Area-Averaged' as CSV from Giovanni.")
    rows = list(csv.reader(io.StringIO("\n".join(lines[header_at:]))))
    header, body = rows[0], [r for r in rows[1:] if r and any(c.strip() for c in r)]
    if len(header) < 2:
        _bad("The Giovanni CSV needs a time column and one value column.")
    if len(body) > MAX_ROWS:
        _bad(f"At most {MAX_ROWS} rows; use monthly data.")
    variable_id = header[1].strip().removeprefix("mean_")
    convert_unit, convert = CONVERSIONS[conversion]
    dates, values = [], []
    for row in body:
        d = _parse_date(row[0])
        raw = row[1].strip() if len(row) > 1 else ""
        try:
            v = float(raw)
        except ValueError:
            v = math.nan
        if not math.isfinite(v) or any(abs(v - f) < 1e-9 * max(1.0, abs(f)) for f in fills) or v <= -9999:
            values.append(None)
        else:
            values.append(convert(v, d))
        dates.append(d)
    if len(set(dates)) != len(dates):
        _bad("Duplicate dates in the Giovanni CSV.")
    title = meta.get("Title", "")
    unit_match = re.search(r"\]\s*([^\s,]+)\s+over", title)
    # Current Giovanni exports do not print units; fall back to the catalogue's native unit for the data ID.
    unit = convert_unit or (unit_match.group(1) if unit_match else "") or native_unit(variable_id)
    bbox = None
    for key in ("User Bounding Box", "Bounding Box", "Data Bounding Box"):
        if key in meta:
            try:
                bbox = [float(x) for x in meta[key].split(",")]
                break
            except ValueError:
                bbox = None
    gaps = sorted({(b - a).days for a, b in zip(dates, dates[1:])})
    frequency = "month" if gaps and 27 <= gaps[0] and gaps[-1] <= 31 * 12 and all(d.day == 1 for d in dates) else (
        "year" if gaps and gaps[0] >= 365 else "day")
    if frequency == "day":
        _bad("Daily Giovanni series are not supported here; download the monthly product.")
    return GiovanniSeries(dates=dates, values=values, variable_id=variable_id, unit=unit, title=title,
                          bbox=bbox, frequency=frequency, metadata=meta)
