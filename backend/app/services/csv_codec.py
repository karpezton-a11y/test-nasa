"""TrendTrace CSV codec: the ONE place that defines how export cells are written and read back.

Standard library only, no app imports: this file can be copied and used on its own
(Group 3 validation scripts, judges) to read any /api/v1/export/csv download exactly.

Why a custom decoder is needed
------------------------------
``pandas.read_csv(path, comment="#")`` treats '#' as a comment start ANYWHERE in a line,
even inside a quoted cell, so text containing '#' would be cut off. Text cells are
therefore written with two reversible escapes:

    backslash  \\  ->  \\\\
    hash       #   ->  \\u0023

Everything else (commas, quotes, newlines, carriage returns, accents, non-Latin
scripts, emoji, degree signs, minus signs ...) is written as UTF-8 and quoted by the
standard ``csv`` module. ``read_export`` undoes all of it and also restores types:

    empty cell  -> None (never 0)          ("" for the `note` column, where "" means "no note")
    numbers     -> float / int (exact round-trip; floats are written with repr)
    true/false  -> bool
    JSON cells  -> list / dict (trend fields period, method, slope_ci, ols_ci, limitations, evidence)

Quick use:
    from csv_codec import read_export
    decoded = read_export("TrendTrace_IGP_aod_month_series_2003-01_2024-12.csv")
    decoded.metadata["data_status"], decoded.rows[0]["value"]
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HEADER_PREFIX = "#"
FIELD_SEPARATOR = " | "
_DECODE = re.compile(r"\\\\|\\u0023")

INTEGER_COLUMNS = frozenset({"n_expected", "n_valid"})
NUMERIC_COLUMNS = frozenset({
    "value", "valid_fraction", "baseline_median", "score", "sen_slope", "p_value", "ols_slope",
    "change_over_period", "baseline_mean", "percent_change_per_decade", "missing_pct", "record_years",
    "lag1_autocorrelation",
})
BOOL_COLUMNS = frozenset({"significant"})
JSON_COLUMNS = frozenset({"period", "method", "slope_ci", "ols_ci", "limitations", "evidence"})
EMPTY_IS_TEXT_COLUMNS = frozenset({"note"})  # contract G: note is a string, "" = no note


# ----------------------------------------------------------------- encoding (used by the exporter)


def encode_text_cell(text: str) -> str:
    return text.replace("\\", "\\\\").replace("#", "\\u0023")


def decode_text_cell(text: str) -> str:
    """Exact inverse of encode_text_cell (left-to-right, so an escaped backslash is never re-read)."""
    return _DECODE.sub(lambda m: "\\" if m.group(0) == "\\\\" else "#", text)


def encode_cell(value: Any) -> str:
    """One Python value -> one CSV cell (the csv module adds quoting)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (list, tuple, dict)):
        return encode_text_cell(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    return encode_text_cell(str(value))


def encode_header_value(value: Any) -> str:
    """Header lines are human metadata: collapse whitespace/newlines and keep ' | ' as the separator."""
    return " ".join(str(value).split()).replace(FIELD_SEPARATOR, " / ")


# ----------------------------------------------------------------- decoding


def decode_cell(column: str, raw: str) -> Any:
    if raw == "":
        return "" if column in EMPTY_IS_TEXT_COLUMNS else None
    if column in INTEGER_COLUMNS:
        return int(raw)
    if column in NUMERIC_COLUMNS:
        return float(raw)
    if column in BOOL_COLUMNS:
        if raw not in ("true", "false"):
            raise ValueError(f"column {column!r}: expected true/false, got {raw!r}")
        return raw == "true"
    if column in JSON_COLUMNS:
        return json.loads(decode_text_cell(raw))
    return decode_text_cell(raw)


@dataclass(frozen=True)
class DecodedCsv:
    metadata: dict[str, str]
    notes: list[str]
    columns: list[str]
    rows: list[dict[str, Any]] = field(default_factory=list)

    def to_dataframe(self):  # pandas is optional for the codec itself
        import pandas as pd

        return pd.DataFrame(self.rows, columns=self.columns)


def parse_header_lines(lines: list[str]) -> tuple[dict[str, str], list[str]]:
    """'# a=1 | b=2' -> {a: 1, b: 2}; 'baseline: start=x | end=y' -> {baseline.start, baseline.end}."""
    metadata: dict[str, str] = {}
    notes: list[str] = []
    for line in lines:
        body = line[len(HEADER_PREFIX):].strip()
        prefix = ""
        for part in body.split(FIELD_SEPARATOR):
            head, sep, rest = part.partition(": ")
            if sep and "=" in rest and "=" not in head:
                prefix, part = head.strip() + ".", rest
            key, eq, value = part.partition("=")
            if eq and " " not in key.strip():
                metadata[prefix + key.strip()] = value.strip()
            else:
                notes.append(part.strip())
    return metadata, notes


def _text(source: str | Path | bytes) -> str:
    if isinstance(source, bytes):
        raw = source
    else:
        raw = Path(source).read_bytes()
    return raw.decode("utf-8-sig")  # tolerate a BOM added by spreadsheet programs


def read_export(source: str | Path | bytes) -> DecodedCsv:
    """Read a TrendTrace CSV export (path or bytes) with metadata, exact values and types."""
    text = _text(source)
    header: list[str] = []
    offset = 0
    for line in text.split("\n"):
        if not line.startswith(HEADER_PREFIX):
            break
        header.append(line.rstrip("\r"))
        offset += len(line) + 1
    reader = csv.reader(io.StringIO(text[offset:], newline=""))
    try:
        columns = next(reader)
    except StopIteration:
        raise ValueError("no column header after the # metadata lines") from None
    rows = []
    for number, cells in enumerate(reader, start=1):
        if len(cells) != len(columns):
            raise ValueError(f"row {number}: {len(cells)} cells, expected {len(columns)}")
        rows.append({col: decode_cell(col, cell) for col, cell in zip(columns, cells)})
    metadata, notes = parse_header_lines(header)
    return DecodedCsv(metadata=metadata, notes=notes, columns=columns, rows=rows)
