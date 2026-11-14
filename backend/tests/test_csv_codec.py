"""CSV codec: exports decode back to the exact original values, including special characters."""

from __future__ import annotations

import io
import json
import subprocess
import sys

import pandas as pd
import pytest

from app.config import REPO_ROOT
from app.schemas import Period, TrendResult
from app.services import csv_codec
from app.services.csv_codec import decode_cell, decode_text_cell, encode_cell, read_export
from app.services.csv_export import ExportRequest, build_csv_export
from app.services.store import MockStore

NORMAL = REPO_ROOT / "data" / "mock" / "normal"
FULL = Period(start="2003-01", end="2024-12")
TRICKY = [
    "hash #1 and ## two",
    "back\\slash and trailing\\",
    "literal \\u0023 must stay literal",
    "double \\\\u0023 too",
    'comma, and "double quotes"',
    "line\nbreak",
    "windows\r\nline end",
    "°C – rain 雨 🌧 é ü ñ",
    "  leading and trailing spaces  ",
    "|pipe| = equals : colon",
    "#starts with hash",
    "",
]


def export(store, what: str, start: str = "2024-01", end: str = "2024-12", variable: str = "aod") -> bytes:
    req = ExportRequest("IGP", variable, "month", start, end, what)
    return build_csv_export(store, req, app_name="TrendTrace", contract_version="1.0",
                            generated_at="2026-11-13T12:00:00+05:30").content


class TrickyStore(MockStore):
    """Puts one difficult string in each anomaly note and in the source product name."""

    def anomalies(self, region_id, variable, period, detrended):
        result = super().anomalies(region_id, variable, period, detrended)
        rows = [a.model_copy(update={"note": TRICKY[i % len(TRICKY)]}) for i, a in enumerate(result.anomalies)]
        return result.model_copy(update={"anomalies": rows})

    def sources(self):
        return [s.model_copy(update={"product": "MOCK A | B #1\nsecond line"}) for s in super().sources()]


@pytest.mark.parametrize("text", TRICKY)
def test_text_cell_encoding_is_exactly_reversible(text):
    encoded = encode_cell(text)
    assert "#" not in encoded
    assert decode_text_cell(encoded) == text


def test_special_characters_survive_full_export_and_decode():
    content = export(TrickyStore(NORMAL), "anomalies")
    decoded = read_export(content)
    assert [row["note"] for row in decoded.rows] == TRICKY  # 12 months, 12 strings, in order
    assert len(pd.read_csv(io.BytesIO(content), comment="#")) == 12  # pandas is not cut short by '#'
    assert decoded.metadata["source"] == "MOCK A / B #1 second line"  # header text is collapsed, not split


def test_series_decodes_to_exact_stored_values():
    decoded = read_export(export(MockStore(NORMAL), "series", "2003-01", "2024-12", "rainfall"))
    series = MockStore(NORMAL).series("IGP", "rainfall", "month")
    assert [r["date"] for r in decoded.rows] == [p.date.isoformat() for p in series.points]
    assert [r["value"] for r in decoded.rows] == [p.value for p in series.points]  # None stays None, 0.0 stays 0.0
    assert [r["valid_fraction"] for r in decoded.rows] == [p.valid_fraction for p in series.points]
    assert any(r["value"] is None for r in decoded.rows) and any(r["value"] == 0.0 for r in decoded.rows)


def test_trend_row_decodes_back_into_the_same_trend_result():
    decoded = read_export(export(MockStore(NORMAL), "trend", "2003-01", "2024-12"))
    assert len(decoded.rows) == 1
    trend = TrendResult.model_validate(decoded.rows[0])
    assert trend == MockStore(NORMAL).trend("IGP", "aod", FULL, "all")


def test_metadata_header_is_parsed_into_keys():
    decoded = read_export(export(MockStore(NORMAL), "anomalies"))
    meta = decoded.metadata
    assert (meta["data_status"], meta["region"], meta["variable"], meta["what"]) == ("mock", "IGP", "aod", "anomalies")
    assert (meta["start"], meta["end"], meta["data_version"]) == ("2024-01", "2024-12", "MOCK-2026-11-13-normal")
    assert (meta["baseline.start"], meta["baseline.statistic"], meta["thresholds.high"]) == ("2003-01", "z_log", "2.0")
    assert "MOCK" in decoded.notes


def test_empty_cells_mean_none_except_note():
    assert decode_cell("value", "") is None and decode_cell("category", "") is None
    assert decode_cell("note", "") == ""
    assert decode_cell("significant", "true") is True and decode_cell("n_valid", "264") == 264


def test_spreadsheet_bom_is_tolerated():
    content = export(MockStore(NORMAL), "series")
    assert read_export(b"\xef\xbb\xbf" + content) == read_export(content)


def test_malformed_input_fails_loudly():
    with pytest.raises(ValueError):
        decode_cell("significant", "yes")
    with pytest.raises(ValueError, match="row 1"):
        read_export(b"# x=1\na,b\n1,2,3\n")
    with pytest.raises(ValueError, match="column header"):
        read_export(b"# only metadata\n")


def test_codec_is_standard_library_only():
    source = (REPO_ROOT / "backend" / "app" / "services" / "csv_codec.py").read_text()
    assert "from ." not in source and "import app" not in source
    for heavy in ("pydantic", "fastapi", "reportlab", "matplotlib"):
        assert f"import {heavy}" not in source and f"from {heavy}" not in source
    assert csv_codec.read_export.__module__ == "app.services.csv_codec"


def test_decode_cli_writes_exact_json(tmp_path):
    csv_path = tmp_path / "export.csv"
    csv_path.write_bytes(export(TrickyStore(NORMAL), "anomalies"))
    out = tmp_path / "decoded.json"
    subprocess.run([sys.executable, "scripts/decode_csv.py", str(csv_path), "--json", str(out)],
                   cwd=REPO_ROOT, check=True, capture_output=True)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert [row["note"] for row in payload["rows"]] == TRICKY
    assert payload["metadata"]["data_status"] == "mock"
