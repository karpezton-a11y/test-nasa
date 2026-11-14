"""STUB used only when DATA_MODE=real and Adrian's loader (app/services/real_store.py) is not installed.

It loads nothing and answers every data request with DATA_NOT_AVAILABLE, so the
app can start in dev to show the real-mode UI states. It never serves mock data.
In APP_ENV=prod, verify_store() refuses to start because no real asset is loaded.
When the real loader lands, build_store() stops using this stub automatically.
"""

from __future__ import annotations

from typing import NoReturn

from ..errors import api_error
from ..schemas import Period
from .store import DatasetInfo

STUB_DATA_VERSION = "REAL-DATA-NOT-LOADED"


class UnavailableRealStore:
    """DataStore with no data. Provenance says 'real' because DATA_MODE=real; nothing is ever served."""

    def __init__(self, contract_version: str) -> None:
        self.info = DatasetInfo(data_status="real", data_version=STUB_DATA_VERSION, contract_version=contract_version)

    @staticmethod
    def _missing(dataset: str, **ids: object) -> NoReturn:
        raise api_error("DATA_NOT_AVAILABLE", "Real data is not loaded yet.", {"dataset": dataset, **ids})

    def asset_statuses(self) -> dict[str, str | None]:
        return {}

    def variables(self) -> NoReturn:
        self._missing("variables")

    def regions(self) -> NoReturn:
        self._missing("regions")

    def sources(self) -> NoReturn:
        self._missing("sources")

    def series(self, region_id: str, variable: str, frequency: str) -> NoReturn:
        self._missing("timeseries_monthly" if frequency == "month" else "timeseries_daily",
                      region_id=region_id, variable=variable)

    def trend(self, region_id: str, variable: str, period: Period, season: str) -> NoReturn:
        self._missing("trend", region_id=region_id, variable=variable, season=season, **period.model_dump())

    def anomalies(self, region_id: str, variable: str, period: Period, detrended: bool) -> NoReturn:
        self._missing("anomalies", region_id=region_id, variable=variable, detrended=detrended)

    def interaction(self, region_id: str, season: str) -> NoReturn:
        self._missing("interaction_summary", region_id=region_id, season=season)

    def indicator(self, region_id: str, indicator: str, season: str) -> NoReturn:
        self._missing("rainfall_indicators", region_id=region_id, indicator=indicator, season=season)
