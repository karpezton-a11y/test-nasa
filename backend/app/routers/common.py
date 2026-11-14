"""Helpers shared by routers: wrap a result in the envelope exactly once."""

from __future__ import annotations

from datetime import datetime
from typing import TypeVar

from fastapi import Request

from ..schemas import Envelope, make_envelope
from ..services.store import DataStore

T = TypeVar("T")


def envelope(request: Request, result: T, generated_at: datetime | None = None,
             store: DataStore | None = None) -> Envelope[T]:
    """Provenance comes from the loaded data (store.info), never from DATA_MODE alone.

    Pass the same ``store`` the route got from ``Depends(get_store)`` so the label always matches the data
    that was served (audit M8). Without it, the store loaded at startup is used.
    """
    info = (store if store is not None else request.app.state.store).info
    return make_envelope(result, data_status=info.data_status, data_version=info.data_version,
                         contract_version=request.app.state.settings.contract_version, generated_at=generated_at)
