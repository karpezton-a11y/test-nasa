"""Integration hooks for report text that other people own.

1. Group 3 (H9): ``docs/methods.md``. Everything except the ``## Limitations``
   section becomes the Methods text; each ``- `` bullet under ``## Limitations``
   becomes one limitation. A missing file means "not delivered yet".
2. Adrian (/explain): an optional module ``app.ai.report_summary`` with
   ``summarize(results: Sequence[BaseModel]) -> tuple[str, Literal["llm", "template"]]``.
   ``results`` are the exact result objects printed in the report. If the module
   is absent, fails to import, raises, or returns another source label, the report
   still builds and says that no summary is available. Every failure except "not
   installed yet" is logged. In real-data mode a summary containing development
   markers ("mock", "placeholder", "TODO", ...) is dropped the same way, so an AI
   sentence can never turn the whole report into REPORT_FAILED.
"""

from __future__ import annotations

import importlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from ..config import REPO_ROOT
from .checks import unintended_placeholders
from .content import AiSummary, ReportContent

logger = logging.getLogger("trendtrace.reports.hooks")

METHODS_PATH = REPO_ROOT / "docs" / "methods.md"
AI_MODULE = "app.ai.report_summary"
AI_SOURCES = ("llm", "template")
_LIMITATIONS_HEADING = re.compile(r"^##\s+limitations\s*$", re.IGNORECASE | re.MULTILINE)


@dataclass(frozen=True)
class ReportTexts:
    methods: str | None
    limitations: tuple[str, ...] | None


def parse_methods_markdown(text: str) -> ReportTexts:
    """Split G3's methods.md into methods paragraphs and limitation bullets (no rewording)."""
    body = re.sub(r"^#\s+.*\n", "", text.strip() + "\n", count=1)  # drop the document title
    match = _LIMITATIONS_HEADING.search(body)
    methods_part, limits_part = (body[:match.start()], body[match.end():]) if match else (body, "")
    limits_part = re.split(r"^##\s", limits_part, maxsplit=1, flags=re.MULTILINE)[0]
    bullets = tuple(line[2:].strip() for line in limits_part.splitlines() if line.startswith("- "))
    methods = re.sub(r"^#+\s*", "", methods_part, flags=re.MULTILINE).strip()
    return ReportTexts(methods=methods or None, limitations=bullets or None)


def load_report_texts(path: Path | None = None) -> ReportTexts:
    path = path or METHODS_PATH
    if not path.is_file():
        return ReportTexts(methods=None, limitations=None)
    return parse_methods_markdown(path.read_text(encoding="utf-8"))


def _load_summary_module() -> ModuleType | None:
    """Import Adrian's module. None if it is not installed yet (silent) or fails to import (logged)."""
    try:
        return importlib.import_module(AI_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name == AI_MODULE:
            return None  # not delivered yet: the normal state until Adrian adds it
        logger.exception("Report summary module %s needs %r, which is not installed; no summary printed",
                         AI_MODULE, exc.name)
    except Exception:  # noqa: BLE001 - a broken module (syntax error, failing import) must not break the PDF
        logger.exception("Report summary module %s failed to import; no summary printed", AI_MODULE)
    return None


def ai_summary_for(content: ReportContent) -> AiSummary | None:
    """Ask Adrian's summary module, if installed, to explain the printed results."""
    if not content.include_ai_summary:
        return None
    module = _load_summary_module()
    if module is None:
        return None
    try:
        text, source = module.summarize(content.result_objects())
    except Exception:  # noqa: BLE001 - an explanation failure must never break the PDF
        logger.exception("Report summary hook failed; the report states that no summary is available")
        return None
    if source not in AI_SOURCES or not str(text).strip():
        logger.error("Report summary hook returned an unusable result (source=%r)", source)
        return None
    markers = [] if content.is_mock else unintended_placeholders([str(text)])
    if markers:
        logger.error("Report summary contained development markers %s in a real-data report; "
                     "printed as not available", markers)
        return None
    return AiSummary(text=str(text), source=source)
