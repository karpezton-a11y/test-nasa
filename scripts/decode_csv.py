#!/usr/bin/env python
"""Decode a TrendTrace CSV export exactly (special characters, empty cells, JSON cells).

    python scripts/decode_csv.py export.csv                 # print metadata + first rows
    python scripts/decode_csv.py export.csv --json out.json # full decoded file as JSON

Uses backend/app/services/csv_codec.py, which is standard-library only: you can also
copy that single file into your own scripts and call ``read_export(path)``.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

CODEC_PATH = Path(__file__).resolve().parents[1] / "backend" / "app" / "services" / "csv_codec.py"


def load_codec():
    """Load the codec file directly, without importing the FastAPI app."""
    spec = importlib.util.spec_from_file_location("trendtrace_csv_codec", CODEC_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses need the module registered
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description="Decode a TrendTrace CSV export")
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--json", type=Path, help="write the decoded file as JSON here")
    parser.add_argument("--rows", type=int, default=5, help="rows to print when --json is not given")
    args = parser.parse_args()
    decoded = load_codec().read_export(args.csv_file)
    payload = {"metadata": decoded.metadata, "notes": decoded.notes, "columns": decoded.columns,
               "rows": decoded.rows}
    if args.json:
        args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                             encoding="utf-8")
        print(f"Decoded {len(decoded.rows)} rows -> {args.json}")
        return 0
    print(json.dumps({**payload, "rows": decoded.rows[: args.rows]}, ensure_ascii=False, indent=2))
    print(f"... {len(decoded.rows)} rows in total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
