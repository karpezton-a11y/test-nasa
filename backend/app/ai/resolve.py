"""Resolve server-known IDs without using client text as file paths."""
from collections import OrderedDict
import re
from threading import Lock

from pydantic import ValidationError

from ..advanced_schemas import AnomalyBothResult, AnomalyResult, InteractionResult
from ..core_schemas import AnalyzeRequest, CompareResult, ExplainRequest, SummaryResult
from ..errors import api_error
from ..schemas import TrendResult
from ..services.advanced import anomalies_for, interaction_for
from ..services.core import analyze_for
from ..services.validation import SEASONS


class ResultRegistry:
    def __init__(self):
        self.items = OrderedDict()
        self.lock = Lock()
        self.ambiguous = set()

    def remember(self, result_type, result):
        key = (result_type, result.result_id)
        with self.lock:
            if key in self.items:
                old = self.items[key].model_dump(exclude={"computed_at"})
                if old != result.model_dump(exclude={"computed_at"}):
                    self.ambiguous.add(key)
            self.items[key] = result.model_copy(deep=True)
            self.items.move_to_end(key)
            while len(self.items) > 512:
                removed, _ = self.items.popitem(last=False)
                self.ambiguous.discard(removed)

    def get(self, kind, result_id):
        with self.lock:
            key = (kind, result_id)
            if key in self.ambiguous:
                raise api_error("DATA_NOT_AVAILABLE", "This result ID is ambiguous; send the validated result object.",
                                {"dataset": "explanation_result"})
            result = self.items.get(key)
            return result.model_copy(deep=True) if result is not None else None


def inline_result(kind, raw):
    try:
        if kind == "trend": return [TrendResult.model_validate(raw)]
        if kind == "anomaly":
            return [(AnomalyBothResult if raw.get("variable") == "both" else AnomalyResult).model_validate(raw)]
        if kind == "interaction": return [InteractionResult.model_validate(raw)]
        if "mode" in raw: return CompareResult.model_validate(raw).results
        return SummaryResult.model_validate(raw).results
    except ValidationError:
        raise api_error("VALIDATION_ERROR", "The result does not match its scientific contract.", {"param": "result"}) from None


def resolve(req: ExplainRequest, store, registry: ResultRegistry):
    if req.result is not None:
        # Schema validation does not authenticate client-supplied science; never
        # place inline results in the server-verified ID registry.
        return inline_result(req.result_type, req.result)
    found = registry.get(req.result_type, req.result_id)
    if found is not None: return [found]
    if req.result_type == "summary":
        raise api_error("DATA_NOT_AVAILABLE", "Send a summary result object.", {"dataset": "explanation_result"})
    for region in store.regions().regions:
        for variable in region.variables + ["both"]:
            if req.result_type == "anomaly":
                prefix = f"anomalies_{region.region_id}_{variable}_"
                tail = req.result_id.removeprefix(prefix)
                match = re.fullmatch(r"(\d{4}-\d{2})_(\d{4}-\d{2})_(raw|detrended)", tail) if tail != req.result_id else None
                if match:
                    result = anomalies_for(store, region.region_id, variable, match[1], match[2], match[3] == "detrended")
                    if result.result_id == req.result_id: return [result]
            if req.result_type == "trend" and variable != "both":
                for season in SEASONS:
                    prefix = f"trend_{region.region_id}_{variable}_{season}_"
                    tail = req.result_id.removeprefix(prefix)
                    match = re.fullmatch(r"(\d{4}-\d{2})_(\d{4}-\d{2})", tail) if tail != req.result_id else None
                    if match:
                        result = analyze_for(store, AnalyzeRequest(region_id=region.region_id, variable=variable,
                            start=match[1], end=match[2], season=season))
                        if result.result_id == req.result_id: return [result]
        if req.result_type == "interaction":
            for season in SEASONS:
                prefix = f"interaction_{region.region_id}_{season}_"
                if req.result_id.startswith(prefix):
                    result = interaction_for(store, region.region_id, season)
                    if result.result_id == req.result_id: return [result]
    raise api_error("DATA_NOT_AVAILABLE", "This computed result is not available; request it again or send the result object.",
                    {"dataset": "explanation_result"})
