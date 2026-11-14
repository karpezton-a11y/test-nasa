"""Real-mode guard: a report built from real data must not contain mock or placeholder text.

The builder collects the plain text of every flowable it will draw (plus the
footer) and asks this module for problems before rendering. In mock mode the
MOCK labels are intended, so nothing is checked.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from reportlab.platypus import Paragraph, Table

# Markers that only development/mock content uses. Matched case-insensitively as whole words.
FORBIDDEN_IN_REAL = ("mock", "placeholder", "illustrative", "lorem", "todo", "tbd", "yyyy", "member 1's")


class UnintendedPlaceholder(RuntimeError):
    """Raised when a real-data report would print mock or placeholder text (-> REPORT_FAILED)."""


def story_text(items: Iterable[Any]) -> list[str]:
    """Plain text of Paragraphs, including those nested in tables. Images carry no checked text."""
    texts: list[str] = []
    for item in items:
        if isinstance(item, Paragraph):
            texts.append(item.getPlainText())
        elif isinstance(item, Table):
            for row in item._cellvalues:  # noqa: SLF001 (ReportLab keeps cell contents here)
                texts += story_text(row)
        elif isinstance(item, (list, tuple)):
            texts += story_text(item)
        elif isinstance(item, str):
            texts.append(item)
    return texts


def unintended_placeholders(texts: Iterable[str]) -> list[str]:
    """Forbidden markers found in the texts, in FORBIDDEN_IN_REAL order (empty list = clean)."""
    joined = "\n".join(texts).lower()
    return [m for m in FORBIDDEN_IN_REAL if re.search(rf"(?<![a-z]){re.escape(m)}(?![a-z])", joined)]


def require_no_placeholders(texts: Iterable[str]) -> None:
    found = unintended_placeholders(texts)
    if found:
        raise UnintendedPlaceholder(f"real-data report contains development text markers: {found}")
