"""TrendTrace trend statistics package (``pip install -e analysis``).

The backend's science adapter (backend/app/services/science.py) calls
``compute_trend`` and ``compute_evidence``; only ``InsufficientDataError`` and
``DataQualityError`` map to INSUFFICIENT_DATA (decision SCI-02).
"""
from . import exceptions, stats
from .api import (LABEL_RULE_VERSION, VERSION, analyze_frame, analyze_values, compute_annual_trend, compute_evidence, compute_trend,
                  evidence_label)
from .exceptions import DataQualityError, InsufficientDataError

__version__ = VERSION
__all__ = ["compute_trend", "compute_annual_trend", "compute_evidence", "analyze_frame", "analyze_values", "evidence_label",
           "InsufficientDataError", "DataQualityError", "LABEL_RULE_VERSION", "stats", "exceptions", "__version__"]
