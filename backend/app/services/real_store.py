"""Read-only, startup-loaded real store behind Karnish's unchanged DataStore protocol.

See docs/implementation/real-data-layout.md. Every loaded byte has explicit real
provenance. Missing assets remain unavailable; corrupt/mixed assets fail startup.
No synthetic data, conversion, interpolation or statistics are performed here.
"""
from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import TypeAdapter

from ..advanced_schemas import AnomalyBothResult, AnomalyResult, IndicatorResult, InteractionResult
from ..config import ConfigError, Settings
from ..errors import api_error
from ..schemas import Envelope, Period, RegionsResult, SourceInfo, TimeSeries, TrendResult, VariableInfo
from .science import compute_trend
from .store import DatasetInfo, SERIES_DATASET, window_anomalies
from .validation import require_min_years, require_coverage, slice_series

COLUMNS = ["date", "region_id", "variable", "frequency", "value", "unit", "source_id", "valid_fraction", "qc_flag"]
UNITS = {("rainfall", "month"): "mm/month", ("rainfall", "day"): "mm/day",
         ("aod", "month"): "1", ("aod", "day"): "1",
         ("aod_terra", "month"): "1", ("aod_merra2", "month"): "1"}


def _missing(dataset: str, **ids):
    raise api_error("DATA_NOT_AVAILABLE", "This real data is not available yet.", {"dataset": dataset, **ids})


def _reject_mock(value: Any, asset: str) -> None:
    if "mock" in json.dumps(value, default=str).lower():
        raise ConfigError(f"Mock marker in real asset {asset}")


class RealStore:
    def __init__(self, settings: Settings) -> None:
        self._root = settings.processed_dir
        self._statuses: dict[str, str] = {}
        self._metadata: dict[str, Any] = {}
        self._series: dict[tuple[str, str, str, str], TimeSeries] = {}
        self._results: dict[str, list[Any]] = {k: [] for k in ("anomalies", "interaction_summary", "rainfall_indicators")}
        self._manifest: dict[str, Any] = {}
        self._file_metadata: dict[str, dict[str, tuple[str, ...]]] = {}
        self.info = DatasetInfo("real", "REAL-DATA-NOT-LOADED", settings.contract_version)
        manifest = self._root / "manifest.json"
        if manifest.is_file():
            self._manifest = self._read_json(manifest)
            self._provenance(self._manifest, "manifest.json")
        for filename, model, key in (("variables.json", list[VariableInfo], "variables"),
                                     ("regions.geojson", RegionsResult, "regions"),
                                     ("sources.json", list[SourceInfo], "sources")):
            path = self._root / filename
            if path.is_file():
                self._metadata[key] = self._json_result(path, model)
        for frequency in ("month", "day"):
            name = SERIES_DATASET[frequency] + ".csv"
            if (self._root / name).is_file():
                self._load_series(self._root / name, frequency)
        # H7/H9 result envelopes, eagerly loaded once; no user input forms paths.
        for folder, model, key in (("anomalies", None, "anomalies"),
                                   ("interaction", InteractionResult, "interaction_summary"),
                                   ("indicators", IndicatorResult, "rainfall_indicators")):
            for path in sorted((self._root / folder).glob("*.json")):
                if folder == "anomalies":
                    raw = self._read_json(path)
                    model = AnomalyBothResult if raw.get("result", {}).get("variable") == "both" else AnomalyResult
                self._extend(key, self._json_result(path, model))
        path = self._root / "interaction_summary.json"
        if path.is_file():
            for result in self._json_result(path, list[InteractionResult]):
                self._extend("interaction_summary", result)
        self._load_indicators()
        self._check_references()
        if settings.is_prod:
            required = {"variables", "regions", "sources"} - self._metadata.keys()
            if (required or not self._metadata.get("variables") or not self._metadata.get("sources")
                    or not getattr(self._metadata.get("regions"), "regions", [])
                    or not any(key[2] == "month" for key in self._series)):
                raise ConfigError("real_store: production requires real metadata and timeseries_monthly.csv with observations")
        # Per-instance caches prevent cross-release/process-store collisions.
        self._trend_cached = lru_cache(maxsize=256)(self._compute_trend)

    @staticmethod
    def _read_json(path: Path):
        def bad_constant(value):
            raise ConfigError(f"Non-finite JSON constant in {path.name}")
        return json.loads(path.read_text(encoding="utf-8"), parse_constant=bad_constant)

    def _provenance(self, raw, name):
        _reject_mock(raw, name)
        if raw.get("data_status") != "real" or not raw.get("data_version"):
            raise ConfigError(f"Explicit real provenance required: {name}")
        info = DatasetInfo("real", raw["data_version"], raw.get("contract_version", ""))
        if info.contract_version != self.info.contract_version:
            raise ConfigError(f"Contract version mismatch: {name}")
        if self._statuses and info != self.info:
            raise ConfigError(f"Mixed data versions: {name}")
        self.info = info
        self._statuses[name] = "real"

    def _json_result(self, path, model):
        raw = self._read_json(path)
        self._provenance(raw, str(path.relative_to(self._root)))
        return TypeAdapter(Envelope[model]).validate_python(raw).result

    def _csv(self, path: Path, columns: list[str]):
        name = path.name
        asset = self._manifest.get("assets", {}).get(name, {})
        if asset.get("data_status") != "real" or asset.get("sha256") != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ConfigError(f"CSV requires matching real manifest asset + SHA-256: {name}")
        # Read identifiers as strings: pandas must not coerce NA-like region IDs.
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        _reject_mock(frame.to_dict("records"), name)
        extras = set(frame.columns) - set(columns)
        if not set(columns) <= set(frame.columns) or not extras <= {"data_version", "method"}:
            raise ConfigError(f"Unexpected columns in {name}; expected {columns} plus optional data_version/method")
        metadata = {}
        if "data_version" in frame:
            if any(value != self.info.data_version for value in frame["data_version"]):
                raise ConfigError(f"CSV data_version does not match manifest: {name}")
            metadata["data_version"] = tuple(frame["data_version"].unique())
        if "method" in frame:
            if any(not value.strip() for value in frame["method"]):
                raise ConfigError(f"CSV method metadata is empty: {name}")
            metadata["method"] = tuple(frame["method"].unique())
        self._file_metadata[name] = metadata
        self._statuses[name] = "real"
        return frame[columns]

    def _load_series(self, path: Path, frequency: str):
        frame = self._csv(path, COLUMNS)
        for key, group in frame.groupby(["region_id", "variable", "frequency", "source_id"], sort=False):
            rid, variable, freq, sid = key
            if freq != frequency:
                raise ConfigError(f"Wrong frequency in {path.name}")
            units = group["unit"].unique()
            if len(units) != 1 or units[0] != self._expected_unit(variable, freq):
                raise ConfigError(f"Non-canonical unit in {path.name}")
            points = []
            for row in group.to_dict("records"):
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["date"]):
                    raise ConfigError(f"Non-ISO date in {path.name}")
                if row["value"] and float(row["value"]) == -9999:
                    raise ConfigError(f"Missing-value sentinel in {path.name}")
                # Original variables need Group 3's temporal coverage; catalogue variables imported
                # from Giovanni/POWER have no coverage field, which stays unknown (never filled with 1).
                if (frequency == "month" and row["valid_fraction"] == "" and variable in {v for v, _ in UNITS}
                        and sid not in self._coverage_unknown_sources()):
                    raise ConfigError(f"Monthly temporal valid_fraction must be numeric: {path.name}")
                if frequency == "day" and row["valid_fraction"] != "":
                    raise ConfigError(f"Daily valid_fraction is unknown and must be empty: {path.name}")
                points.append({"date": row["date"], "value": None if row["value"] == "" else float(row["value"]),
                               "valid_fraction": None if row["valid_fraction"] == "" else float(row["valid_fraction"]),
                               "qc_flag": row["qc_flag"]})
            self._series[key] = TimeSeries(region_id=rid, variable=variable, frequency=freq,
                                           source_id=sid, unit=units[0], points=points)

    def _coverage_unknown_sources(self) -> set[str]:
        """Area-averaged Giovanni/POWER downloads carry no temporal-coverage field (see import_giovanni.py)."""
        return {s.source_id for s in self._metadata.get("sources", [])
                if s.access_method.startswith(("NASA Giovanni", "NASA POWER"))
                or "temporal coverage not exported" in s.access_method}

    def _expected_unit(self, variable: str, frequency: str) -> str | None:
        """Frozen canonical units for the original variables; catalogue variables added later
        (e.g. NO2, soil moisture, imported from Giovanni) use their variables.json unit, monthly only."""
        if (variable, frequency) in UNITS or variable in {v for v, _ in UNITS}:
            return UNITS.get((variable, frequency))
        if frequency != "month":
            return None
        meta = next((v for v in self._metadata.get("variables", []) if v.variable == variable), None)
        return meta.unit if meta is not None else None

    def _extend(self, key, result):
        def identity(r):
            return (getattr(r, "region_id", None), getattr(r, "variable", None),
                    getattr(r, "indicator", None), getattr(r, "season", None),
                    str(getattr(r, "period", None)),
                    getattr(r, "detrended", getattr(getattr(r, "baseline", None), "detrended", None)))
        if any(identity(old) == identity(result) for old in self._results[key]):
            raise ConfigError(f"Duplicate real result in {key}")
        self._results[key].append(result)

    def _load_indicators(self):
        path = self._root / "rainfall_indicators_annual.csv"
        if not path.is_file():
            return
        frame = self._csv(path, ["region_id", "indicator", "season", "year", "value", "valid_fraction"])
        meta = self._root / "rainfall_indicators_metadata.json"
        if not meta.is_file():
            raise ConfigError("Indicator CSV requires rainfall_indicators_metadata.json definitions/results")
        records = self._json_result(meta, list[IndicatorResult])
        consumed = 0
        for result in records:
            group = frame[(frame.region_id == result.region_id) & (frame.indicator == result.indicator)
                          & (frame.season == result.season)]
            values = [{"year": int(row.year), "value": None if row.value == "" else float(row.value),
                       "valid_fraction": None if row.valid_fraction == "" else float(row.valid_fraction)}
                      for row in group.itertuples(index=False)]
            if [v.model_dump() for v in result.values] != values:
                raise ConfigError("Indicator metadata values must match CSV exactly")
            consumed += len(group)
            self._extend("rainfall_indicators", result)
        if consumed != len(frame):
            raise ConfigError("Unmatched indicator CSV rows")

    def _check_references(self):
        variables = {v.variable: v for v in self._metadata.get("variables", [])}
        regions = {r.region_id: r for r in getattr(self._metadata.get("regions"), "regions", [])}
        sources = {s.source_id for s in self._metadata.get("sources", [])}
        if (len(variables) != len(self._metadata.get("variables", []))
                or len(sources) != len(self._metadata.get("sources", []))
                or len(regions) != len(getattr(self._metadata.get("regions"), "regions", []))):
            raise ConfigError("Duplicate metadata IDs")
        if "regions" in self._metadata:
            features = self._metadata["regions"].geojson.features
            if (len(features) != len(regions) or {f.id for f in features} != set(regions)
                    or any(f.id != f.properties.region_id for f in features)):
                raise ConfigError("GeoJSON features must match the region IDs exactly")
        for v in variables.values():
            if v.variable in {name for name, _ in UNITS} and v.unit != UNITS.get((v.variable, "month")):
                raise ConfigError("Non-canonical variable metadata unit")
            if not v.unit.strip():
                raise ConfigError("Variable metadata unit is empty")
            if not set(v.sources) <= sources:
                raise ConfigError("Unknown source in variables")
        for r in regions.values():
            if not set(r.variables) <= variables.keys():
                raise ConfigError("Unknown variable in regions")
        for series in self._series.values():
            if series.region_id not in regions or series.variable not in variables or series.source_id not in sources:
                raise ConfigError("Unknown region, variable or source in series")
            if series.variable not in regions[series.region_id].variables or series.source_id not in variables[series.variable].sources:
                raise ConfigError("Series does not match metadata associations")
            available = regions[series.region_id].period_available
            if any(not available.start <= p.date.strftime("%Y-%m") <= available.end for p in series.points):
                raise ConfigError("Series outside region period_available")
        for results in self._results.values():
            for result in results:
                self._check_result_sources(result, sources, regions)

    def _check_result_sources(self, result, sources, regions):
        if result.region_id not in regions:
            raise ConfigError("Unknown region in result")
        if hasattr(result, "results"):
            for child in result.results:
                self._check_result_sources(child, sources, regions)
        sid = getattr(result, "source_id", None)
        source_ids = getattr(result, "source_ids", {})
        if hasattr(source_ids, "model_dump"):
            source_ids = source_ids.model_dump()
        ids = set(source_ids.values()) | ({sid} if sid else set())
        if not ids <= sources:
            raise ConfigError("Unknown source in result")
        if getattr(result, "trend", None) is not None:
            self._check_result_sources(result.trend, sources, regions)

    def asset_statuses(self):
        return dict(self._statuses)

    def _meta(self, key):
        if key not in self._metadata:
            _missing(key)
        obj = self._metadata[key]
        return [x.model_copy(deep=True) for x in obj] if isinstance(obj, list) else obj.model_copy(deep=True)

    def variables(self): return self._meta("variables")
    def regions(self): return self._meta("regions")
    def sources(self): return self._meta("sources")

    def series(self, region_id: str, variable: str, frequency: str) -> TimeSeries:
        candidates = [s for (r, v, f, _), s in self._series.items() if (r, v, f) == (region_id, variable, frequency)]
        order = next((v.sources for v in self._metadata.get("variables", []) if v.variable == variable), [])
        candidates.sort(key=lambda s: order.index(s.source_id) if s.source_id in order else len(order))
        if not candidates:
            _missing(SERIES_DATASET.get(frequency, "timeseries"), region_id=region_id, variable=variable)
        return candidates[0].model_copy(deep=True)

    def series_for_source(self, region_id, variable, frequency, source_id):
        result = self._series.get((region_id, variable, frequency, source_id))
        if result is None:
            _missing("timeseries", region_id=region_id, variable=variable, source_id=source_id)
        return result.model_copy(deep=True)

    def trend(self, region_id: str, variable: str, period: Period, season: str) -> TrendResult:
        return self.analysis(region_id, variable, period, season)

    def analysis(self, region_id, variable, period, season, *, alpha=0.05, exclude_low_coverage=False):
        return self._trend_cached(region_id, variable, period.start, period.end, season, alpha,
                                  exclude_low_coverage).model_copy(deep=True)

    def _compute_trend(self, region_id, variable, start, end, season, alpha, exclude_low_coverage):
        period = Period(start=start, end=end)
        series = slice_series(self.series(region_id, variable, "month"), period)
        require_min_years(period)
        require_coverage(series, period, season=season)
        result = compute_trend(series, period, season, alpha=alpha,
                               exclude_low_coverage=exclude_low_coverage)
        result = self._with_comparison_sources(result, region_id, variable, period, season, alpha)
        _reject_mock(result.model_dump(mode="json"), "trendlib result")
        sources = {s.source_id for s in self.sources()}
        self._check_result_sources(result, sources, {r.region_id: r for r in self.regions().regions})
        return result

    # Handbook sensitivity runs: the same test on independent comparison products (never blended into the
    # primary series). Names match the contract fixtures: terra_monthly, merra2.
    COMPARISON_RUNS = {"MODIS_TERRA_C61_MONTHLY": "terra_monthly", "MERRA2_MONTHLY_TOTEXTTAU": "merra2",
                       "NASA_POWER_PRECTOTCORR": "merra2_power_rainfall"}

    def _with_comparison_sources(self, result, region_id, variable, period, season, alpha):
        from .science import _trendlib, quality_errors, series_frame
        runs = []
        for source_id, name in self.COMPARISON_RUNS.items():
            series = self._series.get((region_id, variable, "month", source_id))
            if series is None or source_id == result.source_id:
                continue
            try:
                other = _trendlib().compute_trend(series_frame(slice_series(series, period), period), season=season, alpha=alpha)
            except quality_errors():
                runs.append({"name": name, "sen_slope": None, "p_value": None, "same_sign": None})
                continue
            same = None if result.sen_slope == 0 else (other["sen_slope"] > 0) == (result.sen_slope > 0) and other["sen_slope"] != 0
            runs.append({"name": name, "sen_slope": other["sen_slope"], "p_value": other["p_value"], "same_sign": same})
        if not runs:
            return result
        evidence = result.evidence.model_dump()
        evidence["sensitivity"] = evidence["sensitivity"] + runs
        evidence["evidence_label"] = _trendlib().evidence_label(
            record_years=evidence["record_years"], valid_obs_pct=evidence["valid_obs_pct"], p_value=evidence["p_value"],
            alpha=alpha, ci_excludes_zero=evidence["ci_excludes_zero"], sensitivity=evidence["sensitivity"])
        evidence["notes"] = evidence["notes"] + ["Sensitivity includes independent Terra MODIS and/or MERRA-2 comparison products."]
        return TrendResult.model_validate({**result.model_dump(), "evidence": evidence})

    def anomalies(self, region_id, variable, period, detrended):
        for result in self._results["anomalies"]:
            flag = result.detrended if isinstance(result, AnomalyBothResult) else result.baseline.detrended
            if (result.region_id, result.variable, flag) == (region_id, variable, detrended):
                if result.period.start <= period.start and period.end <= result.period.end:
                    return window_anomalies(result.model_copy(deep=True), period)
        _missing("anomalies", region_id=region_id, variable=variable, detrended=detrended)

    def interaction(self, region_id, season):
        for result in self._results["interaction_summary"]:
            if (result.region_id, result.season) == (region_id, season):
                return result.model_copy(deep=True)
        _missing("interaction_summary", region_id=region_id, season=season)

    def indicator(self, region_id, indicator, season):
        for result in self._results["rainfall_indicators"]:
            if (result.region_id, result.indicator, result.season) == (region_id, indicator, season):
                return result.model_copy(deep=True)
        _missing("rainfall_indicators", region_id=region_id, indicator=indicator, season=season)


def create_store(settings: Settings) -> RealStore:
    return RealStore(settings)
