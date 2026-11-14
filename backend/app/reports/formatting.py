"""Display formatting for reports. Formats copies only; stored values are never changed.

Rules (DOCX section 6-A): AOD 3 d.p., rainfall 1 d.p., p-values 3 d.p. or "< 0.001".
Missing -> "n/a" (never 0). A real 0 prints as 0.
"""

from __future__ import annotations

NA = "n/a"
DECIMALS_BY_UNIT = {"1": 3, "mm/month": 1, "mm/day": 1, "mm": 1, "%": 1, "days": 0}


def decimals_for(unit: str) -> int:
    return DECIMALS_BY_UNIT.get(unit.replace(" per decade", ""), 3)


def fmt_number(value: float | None, unit: str) -> str:
    if value is None:
        return NA
    return f"{value:.{decimals_for(unit)}f}"


def fmt_with_unit(value: float | None, unit: str) -> str:
    text = fmt_number(value, unit)
    if text == NA:
        return text
    if unit == "1":
        return f"{text} (unitless)"
    if unit == "1 per decade":
        return f"{text} per decade (unitless)"
    return f"{text} {unit}"


def fmt_interval(interval: tuple[float, float] | None, unit: str) -> str:
    if interval is None:
        return NA
    return f"{fmt_number(interval[0], unit)} to {fmt_number(interval[1], unit)}"


def fmt_p(p: float | None) -> str:
    if p is None:
        return NA
    return "< 0.001" if p < 0.001 else f"{p:.3f}"


def fmt_pct(value: float | None) -> str:
    return NA if value is None else f"{value:.1f}%"


def fmt_fraction(value: float | None) -> str:
    return NA if value is None else f"{value:.2f}"


def fmt_bool(value: bool | None) -> str:
    return NA if value is None else ("yes" if value else "no")
