"""Light metadata endpoints: /variables, /regions, /meta/sources.

Thin routers: the store returns validated contract objects (or raises
DATA_NOT_AVAILABLE); text and units are served exactly as stored.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..openapi_errors import error_responses
from ..schemas import Envelope, RegionsResult, SourceInfo, VariableInfo
from ..services.store import DataStore, get_store
from .common import envelope

router = APIRouter(tags=["metadata"])
ERRORS = error_responses("DATA_NOT_AVAILABLE")


@router.get("/variables", response_model=Envelope[list[VariableInfo]], responses=ERRORS)
def list_variables(request: Request, store: DataStore = Depends(get_store)) -> Envelope[list[VariableInfo]]:
    return envelope(request, store.variables(), store=store)


@router.get("/regions", response_model=Envelope[RegionsResult], responses=ERRORS)
def list_regions(request: Request, store: DataStore = Depends(get_store)) -> Envelope[RegionsResult]:
    return envelope(request, store.regions(), store=store)


@router.get("/meta/sources", response_model=Envelope[list[SourceInfo]], responses=ERRORS)
def list_sources(request: Request, store: DataStore = Depends(get_store)) -> Envelope[list[SourceInfo]]:
    return envelope(request, store.sources(), store=store)
