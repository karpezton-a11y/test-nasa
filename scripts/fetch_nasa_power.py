"""Download a regional monthly series from NASA POWER and save it as a Giovanni-style CSV.

NASA POWER (https://power.larc.nasa.gov) serves MERRA-2- and CERES-based meteorology with
no login, which makes it the quickest way to get *real* NASA data for any box on Earth.
The output uses Giovanni's area-averaged CSV layout, so the same file can be

* uploaded to ``POST /api/v1/analyze/series`` as ``giovanni_csv``, or
* loaded into real mode with ``scripts/import_giovanni.py``.

The box average is the mean of a regular grid of POWER points (default 1 degree spacing,
at most 36 points). Fill values (-999) stay missing; no gaps are filled.

Examples::

    python scripts/fetch_nasa_power.py --bbox 76 24 88 30 --parameter T2M --start 2003 --end 2024 -o data/raw/IGP_T2M.csv
    python scripts/fetch_nasa_power.py --bbox 76.8 28.3 77.6 28.9 --parameter PRECTOTCORR -o data/raw/DELHI_rain.csv

Common parameters: T2M (air temperature, C), PRECTOTCORR (rain, mm/day), RH2M (humidity, %),
WS2M (wind, m/s), ALLSKY_SFC_SW_DWN (sunlight at the surface, kWh/m2/day),
GWETROOT (root-zone soil wetness, 0-1).
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import httpx

API = "https://power.larc.nasa.gov/api/temporal/monthly/point"
FILL = -999.0
MAX_POINTS = 36


def grid_points(bbox: list[float], step: float) -> list[tuple[float, float]]:
    west, south, east, north = bbox
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise SystemExit("bbox must be west south east north")
    nx = max(1, int(math.floor((east - west) / step)) + 1)
    ny = max(1, int(math.floor((north - south) / step)) + 1)
    while nx * ny > MAX_POINTS:
        step *= 1.25
        nx = max(1, int(math.floor((east - west) / step)) + 1)
        ny = max(1, int(math.floor((north - south) / step)) + 1)
    xs = [west + (east - west) * (i + 0.5) / nx for i in range(nx)]
    ys = [south + (north - south) * (j + 0.5) / ny for j in range(ny)]
    return [(round(x, 4), round(y, 4)) for y in ys for x in xs]


def fetch(parameter: str, bbox: list[float], start: int, end: int, step: float = 1.0,
          client: httpx.Client | None = None) -> tuple[dict[str, float | None], str, str, int]:
    """Return ({YYYY-MM: box mean or None}, units, long name, number of points)."""
    points = grid_points(bbox, step)
    own = client is None
    client = client or httpx.Client(timeout=60)
    sums: dict[str, list[float]] = {}
    units, longname = "", parameter
    try:
        for lon, lat in points:
            response = client.get(API, params={"parameters": parameter, "community": "AG", "longitude": lon,
                                               "latitude": lat, "start": start, "end": end, "format": "JSON"})
            response.raise_for_status()
            body = response.json()
            values = body["properties"]["parameter"][parameter]
            meta = body.get("parameters", {}).get(parameter, {})
            units, longname = meta.get("units", units), meta.get("longname", longname)
            for key, value in values.items():
                if key.endswith("13"):  # month 13 = annual value
                    continue
                month = f"{key[:4]}-{key[4:6]}"
                sums.setdefault(month, [])
                if value is not None and float(value) != FILL:
                    sums[month].append(float(value))
    finally:
        if own:
            client.close()
    series = {m: (sum(v) / len(v) if v else None) for m, v in sorted(sums.items())}
    return series, units, longname, len(points)


def to_giovanni_csv(series: dict[str, float | None], parameter: str, units: str, longname: str,
                    bbox: list[float], n_points: int) -> str:
    first, last = next(iter(series)), next(reversed(series))
    column = f"mean_POWER_{parameter}"
    lines = [
        f"Title:,Time Series, Area-Averaged of {longname} monthly [NASA POWER {parameter}] {units.replace(' ', '')} over {first} - {last}, "
        f"Region {bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}",
        f"Data Source:,NASA POWER monthly point API (box mean of {n_points} grid points)",
        f'Bounding Box:,"{",".join(str(b) for b in bbox)}"',
        f"Fill Value ({column}):,-9999.9",
        "",
        f"time,{column}",
    ]
    lines += [f"{m}-01,{'-9999.9' if v is None else f'{v:.6f}'}" for m, v in series.items()]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    parser.add_argument("--parameter", required=True)
    parser.add_argument("--start", type=int, default=2003)
    parser.add_argument("--end", type=int, default=2024)
    parser.add_argument("--step", type=float, default=1.0, help="grid spacing in degrees")
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args(argv)
    series, units, longname, n = fetch(args.parameter, args.bbox, args.start, args.end, args.step)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(to_giovanni_csv(series, args.parameter, units, longname, args.bbox, n), encoding="utf-8")
    missing = sum(v is None for v in series.values())
    print(f"Wrote {len(series)} months ({missing} missing) of {args.parameter} [{units}] from {n} points to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
