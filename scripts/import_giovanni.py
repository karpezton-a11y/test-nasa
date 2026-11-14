"""Load Giovanni (or NASA POWER) area-averaged CSVs into the real-mode data folder.

This is the 'acquire the data for a particular region' step of the challenge, done
without code: download "Time Series, Area-Averaged" as CSV from Giovanni (or run
scripts/fetch_nasa_power.py), then run, for example::

    python scripts/import_giovanni.py data/raw/delhi_no2.csv --region-id DELHI --variable no2
    python scripts/import_giovanni.py data/raw/igp_t2m.csv --region-id IGP --variable air_temperature --conversion k_to_c --unit degC

It writes or merges, under data/processed/ (PROCESSED_DIR):

* timeseries_monthly.csv  (the nine contract columns; missing values stay empty)
* variables.json, sources.json, regions.geojson  (real-provenance envelopes)
* manifest.json  (data_status=real, data_version, SHA-256 of the CSV)

Regions come from the loaded regions or the catalogue presets (data/catalog); variable
labels and definitions come from the catalogue. Restart the API with DATA_MODE=real.
Existing Group 3 rows are kept; a duplicate region/variable/source series is refused
unless --replace is given. Nothing is interpolated or filled.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.giovanni import CONVERSIONS, daily_to_monthly, parse_giovanni_csv  # noqa: E402

COLUMNS = ["date", "region_id", "variable", "frequency", "value", "unit", "source_id", "valid_fraction", "qc_flag"]
IST = timezone(timedelta(hours=5, minutes=30))
FROZEN_UNITS = {"rainfall": "mm/month", "aod": "1"}


def _envelope(result, version: str, contract: str) -> dict:
    return {"data_status": "real", "data_version": version, "contract_version": contract,
            "generated_at": datetime.now(IST).replace(microsecond=0).isoformat(), "result": result}


def _read_envelope(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _polygon(bbox):
    w, s, e, n = bbox
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}


def import_csv(csv_path: Path, *, region_id: str, variable: str, processed: Path, conversion: str = "none",
               unit: str | None = None, source_id: str | None = None, data_version: str | None = None,
               contract_version: str = "1.0", replace: bool = False) -> dict:
    catalog = json.loads((ROOT / "data/catalog/variables_catalog.json").read_text(encoding="utf-8"))
    entry = next((v for v in catalog["variables"] if v["id"] == variable), None)
    if entry is None:
        raise SystemExit(f"Unknown variable {variable!r}; use an id from data/catalog/variables_catalog.json")
    series = parse_giovanni_csv(csv_path.read_text(encoding="utf-8"), conversion, allow_daily=True)
    fractions = None
    if series.frequency == "day":
        # Daily products (e.g. OMI OMNO2d) become monthly means with measured temporal coverage.
        series.dates, series.values, fractions = daily_to_monthly(series)
        series.frequency = "month"
    if series.frequency != "month":
        raise SystemExit("Only monthly or daily series can be imported")
    # Prefer what the file says (e.g. POWER T2M is in C) over the catalogue default, so nothing is mislabelled.
    unit = unit or CONVERSIONS[conversion][0] or series.unit or entry["unit"]
    if variable in FROZEN_UNITS and unit != FROZEN_UNITS[variable]:
        raise SystemExit(f"{variable} must be in {FROZEN_UNITS[variable]} (frozen contract unit)")
    source_id = (source_id or f"GIOVANNI_{series.variable_id}").upper()[:80]
    processed.mkdir(parents=True, exist_ok=True)

    manifest = _read_envelope(processed / "manifest.json") or {}
    version = data_version or manifest.get("data_version") or f"REAL-{date.today().isoformat()}-giovanni"
    contract = manifest.get("contract_version", contract_version)

    # Time series rows (merge with what is already there).
    ts_path = processed / "timeseries_monthly.csv"
    rows = list(csv.DictReader(ts_path.open(encoding="utf-8"))) if ts_path.is_file() else []
    key = (region_id, variable, source_id)
    exists = any((r["region_id"], r["variable"], r["source_id"]) == key for r in rows)
    if exists and not replace:
        raise SystemExit(f"Series {key} already exists; pass --replace to overwrite it")
    rows = [r for r in rows if (r["region_id"], r["variable"], r["source_id"]) != key]
    for i, (d, v) in enumerate(zip(series.dates, series.values)):
        vf = None if fractions is None else fractions[i]
        qc = "missing" if v is None else ("low_coverage" if vf is not None and vf < 0.5 else "ok")
        rows.append({"date": d.isoformat(), "region_id": region_id, "variable": variable, "frequency": "month",
                     "value": "" if v is None else repr(float(v)), "unit": unit, "source_id": source_id,
                     "valid_fraction": "" if vf is None else repr(vf), "qc_flag": qc})
    rows.sort(key=lambda r: (r["region_id"], r["variable"], r["source_id"], r["date"]))
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    ts_path.write_text(buffer.getvalue(), encoding="utf-8")

    # Sources.
    src_env = _read_envelope(processed / "sources.json")
    sources = src_env["result"] if src_env else []
    power = "POWER" in series.metadata.get("Data Source", "")
    param = series.variable_id.removeprefix("POWER_")
    sources = [s for s in sources if s["source_id"] != source_id] + [{
        "source_id": source_id,
        "product": f"NASA POWER monthly {param} (MERRA-2/GEOS-based meteorology)" if power else entry["product"],
        "short_name": param if power else series.variable_id, "version": "as downloaded",
        "doi": None, "access_method": ("NASA POWER monthly point API, box mean" if power
                                       else "NASA Giovanni area-averaged time series CSV"),
        "access_date": date.today().isoformat(), "variable_name": param if power else entry["field"],
        "citation": ("NASA Langley Research Center POWER Project, monthly point API (power.larc.nasa.gov), "
                     f"accessed {date.today().isoformat()}." if power else None)}]

    # Variables.
    var_env = _read_envelope(processed / "variables.json")
    variables = var_env["result"] if var_env else []
    current = next((v for v in variables if v["variable"] == variable), None)
    if current is None:
        variables.append({"variable": variable, "label": entry["name"], "unit": unit, "unit_label": unit,
                          "sources": [source_id], "description": entry["plain_definition"], "caveat": entry["caveat"]})
    else:
        if current["unit"] != unit:
            raise SystemExit(f"{variable} is already loaded in {current['unit']}, not {unit}")
        if source_id not in current["sources"]:
            current["sources"].append(source_id)

    # Regions.
    reg_env = _read_envelope(processed / "regions.geojson")
    regions = reg_env["result"]["regions"] if reg_env else []
    region = next((r for r in regions if r["region_id"] == region_id), None)
    first, last = series.dates[0].strftime("%Y-%m"), series.dates[-1].strftime("%Y-%m")
    if region is None:
        preset = next((p for p in catalog["region_presets"] if p["id"] == region_id), None)
        bbox = preset["bbox"] if preset else series.bbox
        if bbox is None:
            raise SystemExit(f"Region {region_id} is not a preset and the CSV has no bounding box")
        region = {"region_id": region_id, "name": preset["name"] if preset else region_id, "bbox": bbox,
                  "status": "analysis_box", "description": preset["why"] if preset else "Imported analysis box.",
                  "variables": [variable], "period_available": {"start": first, "end": last}}
        regions.append(region)
    else:
        if variable not in region["variables"]:
            region["variables"].append(variable)
        region["period_available"] = {"start": min(first, region["period_available"]["start"]),
                                      "end": max(last, region["period_available"]["end"])}
    geojson = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": r["region_id"], "geometry": _polygon(r["bbox"]),
         "properties": {"region_id": r["region_id"], "name": r["name"], "status": r["status"]}} for r in regions]}

    (processed / "sources.json").write_text(json.dumps(_envelope(sources, version, contract), indent=1), encoding="utf-8")
    (processed / "variables.json").write_text(json.dumps(_envelope(variables, version, contract), indent=1), encoding="utf-8")
    (processed / "regions.geojson").write_text(json.dumps(_envelope({"regions": regions, "geojson": geojson}, version, contract),
                                                          indent=1), encoding="utf-8")
    assets = manifest.get("assets", {})
    assets["timeseries_monthly.csv"] = {"data_status": "real",
                                        "sha256": hashlib.sha256(ts_path.read_bytes()).hexdigest()}
    manifest = {"data_status": "real", "data_version": version, "contract_version": contract, "assets": assets}
    (processed / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return {"rows": len(series.dates), "missing": sum(v is None for v in series.values), "source_id": source_id,
            "low_coverage": sum(1 for r in rows if r["source_id"] == source_id and r["region_id"] == region_id
                                and r["variable"] == variable and r["qc_flag"] == "low_coverage"),
            "unit": unit, "period": (first, last), "data_version": version}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--region-id", required=True)
    parser.add_argument("--variable", required=True, help="catalogue id, e.g. no2, soil_moisture, air_temperature")
    parser.add_argument("--conversion", default="none", choices=sorted(CONVERSIONS))
    parser.add_argument("--unit")
    parser.add_argument("--source-id")
    parser.add_argument("--data-version")
    parser.add_argument("--processed-dir", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args(argv)
    info = import_csv(args.csv, region_id=args.region_id, variable=args.variable, processed=args.processed_dir,
                      conversion=args.conversion, unit=args.unit, source_id=args.source_id,
                      data_version=args.data_version, replace=args.replace)
    print(f"Imported {info['rows']} months ({info['missing']} missing) as {info['source_id']} [{info['unit']}] "
          f"{info['period'][0]}..{info['period'][1]} into {args.processed_dir} (data_version {info['data_version']}).")
    print("Restart the API with DATA_MODE=real to serve it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
