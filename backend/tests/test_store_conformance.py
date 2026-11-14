"""Audit M6: the rules in the DataStore docstring, checked on any store.

Runs on MockStore and on the dev stub today, and on Adrian's real loader as soon as
app/services/real_store.py exists (``python -m pytest backend/tests/test_store_conformance.py``).
Each checker returns a list of problems, so a failure says exactly which rule broke.
"""

from __future__ import annotations

import importlib.util
import io
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

import pytest

from app.config import REPO_ROOT, load_settings
from app.errors import ApiError
from app.schemas import Period
from app.services.advanced import INDICATORS
from app.services.store import DataStore, MockStore, regions_path
from app.services.unavailable_store import UnavailableRealStore

UNKNOWN = "NO_SUCH_REGION"
PARALLEL_CALLS = 40  # FastAPI's default thread pool size
DEFAULT_PERIOD = Period(start="2003-01", end="2024-12")
MOCK_DIR = REPO_ROOT / "data" / "mock" / "normal"

Call = tuple[str, Callable[[], Any]]


def _calls(store: DataStore, region_id: str | None = None) -> list[Call]:
    """One call per method: a real selection when regions() works, else IGP/aod (or ``region_id``)."""
    try:
        region = store.regions().regions[0]
    except ApiError:
        region = None
    rid = region_id or (region.region_id if region else "IGP")
    variable = region.variables[0] if region else "aod"
    period = region.period_available if region else DEFAULT_PERIOD
    return [("variables", store.variables), ("regions", store.regions), ("sources", store.sources),
            ("series", lambda: store.series(rid, variable, "month")),
            ("trend", lambda: store.trend(rid, variable, period, "all")),
            ("anomalies", lambda: store.anomalies(rid, variable, period, False)),
            ("interaction", lambda: store.interaction(rid, "JJAS")),
            ("indicator", lambda: store.indicator(rid, INDICATORS[0], "annual"))]


def _outcome(call: Callable[[], Any]) -> Any:
    """Comparable result: JSON-ready data, or the ApiError code. Other exceptions propagate."""
    try:
        value = call()
    except ApiError as err:
        return f"ApiError:{err.code}"
    items = value if isinstance(value, list) else [value]
    return [item.model_dump(mode="json") for item in items]


def info_problems(store: DataStore) -> list[str]:
    info = store.info
    problems = [] if info.data_status in ("mock", "real") else [f"info.data_status {info.data_status!r}"]
    return problems + [f"info.{name} is empty" for name in ("data_version", "contract_version")
                       if not getattr(info, name)]


def error_problems(store: DataStore) -> list[str]:
    """Unknown selections must raise ApiError, never KeyError/FileNotFoundError/IndexError."""
    problems = []
    for name, call in _calls(store, region_id=UNKNOWN)[3:]:  # the per-region methods
        try:
            call()
            problems.append(f"{name}({UNKNOWN}) returned data instead of an error")
        except ApiError:
            continue
        except Exception as exc:  # noqa: BLE001 - the point of the check
            problems.append(f"{name}({UNKNOWN}) raised {type(exc).__name__}, not ApiError")
    return problems


def repeat_read_problems(store: DataStore, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """After a first call, a repeated call must be served from memory (no file is opened)."""
    calls = _calls(store)
    first = {name: _outcome(call) for name, call in calls}

    def guard(file: Any, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"store opened {file} on a repeated call")

    with monkeypatch.context() as patch:
        patch.setattr("builtins.open", guard)
        patch.setattr(io, "open", guard)
        problems = []
        for name, call in calls:
            try:
                again = _outcome(call)
            except AssertionError:
                problems.append(f"{name}() reads files on every call")
                continue
            if again != first[name]:
                problems.append(f"{name}() returned something different the second time")
    return problems


def parallel_problems(store: DataStore) -> list[str]:
    """40 simultaneous requests get exactly what one request gets."""
    calls = _calls(store)
    expected = [_outcome(call) for _, call in calls]
    with ThreadPoolExecutor(max_workers=PARALLEL_CALLS) as pool:
        futures = [pool.submit(lambda: [_outcome(call) for _, call in calls]) for _ in range(PARALLEL_CALLS)]
        try:
            results = [future.result() for future in futures]
        except Exception as exc:  # noqa: BLE001 - reported as a problem
            return [f"parallel calls raised {type(exc).__name__}: {exc}"]
    return [] if all(result == expected for result in results) else ["parallel calls returned different results"]


# ----------------------------------------------------------------- the stores


def _real_store() -> DataStore:
    if importlib.util.find_spec("app.services.real_store") is None:
        pytest.skip("app/services/real_store.py not delivered yet (Adrian)")
    from app.services.real_store import create_store

    return create_store(load_settings(env={"APP_ENV": "dev", "DATA_MODE": "real"}, env_file=None))


STORES: dict[str, Callable[[], DataStore]] = {
    "mock": lambda: MockStore(MOCK_DIR),
    "dev-stub": lambda: UnavailableRealStore("1.0"),
    "real": _real_store,
}


@pytest.fixture(params=sorted(STORES))
def store(request) -> DataStore:
    return STORES[request.param]()


def test_store_info_is_complete(store):
    assert info_problems(store) == []


def test_unknown_selections_raise_only_api_errors(store):
    assert error_problems(store) == []


def test_repeated_calls_are_served_from_memory(store, monkeypatch):
    assert repeat_read_problems(store, monkeypatch) == []


def test_parallel_calls_are_safe_and_consistent(store):
    assert parallel_problems(store) == []


# ----------------------------------------------------------------- the checkers catch bad stores


class ReadsEveryTime(MockStore):
    def regions(self):
        return self._load_uncached(regions_path()).result


class LeaksKeyError(MockStore):
    def interaction(self, region_id, season):
        return {"IGP": super().interaction("IGP", season)}[region_id]


def test_checker_catches_a_store_that_rereads_files(monkeypatch):
    assert repeat_read_problems(ReadsEveryTime(MOCK_DIR), monkeypatch) == ["regions() reads files on every call"]


def test_checker_catches_a_raw_key_error():
    assert error_problems(LeaksKeyError(MOCK_DIR)) == [f"interaction({UNKNOWN}) raised KeyError, not ApiError"]
