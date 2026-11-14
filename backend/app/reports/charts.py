"""Static PNG charts for the PDF (matplotlib, Agg, object-oriented API only).

- Missing values are gaps: nulls become NaN and absent timestamps insert a NaN.
- No fitted line or confidence band is drawn: contract E has a slope and its CI
  but no intercept or pointwise band (decision R-4). The slope is shown as text.
- Uses Figure + FigureCanvasAgg directly: no pyplot global state, safe per request.
"""

from __future__ import annotations

import io
from datetime import date, timedelta

import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from ..schemas import TimeSeries  # noqa: E402

COLORS = {"rainfall": "#0072B2", "aod": "#E69F00"}
STYLES = {"rainfall": "-", "aod": "--"}


def _next_step(day: date, frequency: str) -> date:
    if frequency == "day":
        return day + timedelta(days=1)
    return date(day.year + (day.month == 12), day.month % 12 + 1, 1)


def gap_arrays(series: TimeSeries) -> tuple[list[date], np.ndarray]:
    """Dates and values with NaN wherever a value is null or a timestamp is absent."""
    dates: list[date] = []
    values: list[float] = []
    for point in series.points:
        if dates and point.date > _next_step(dates[-1], series.frequency):
            dates.append(_next_step(dates[-1], series.frequency))
            values.append(np.nan)
        dates.append(point.date)
        values.append(np.nan if point.value is None else float(point.value))
    return dates, np.asarray(values, dtype=float)


def build_series_figure(series: TimeSeries, label: str, unit_label: str, annotation: str | None) -> Figure:
    fig = Figure(figsize=(7.2, 2.9), dpi=150)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot()
    dates, values = gap_arrays(series)
    color = COLORS.get(series.variable, "#333333")
    ax.plot(dates, values, color=color, linestyle=STYLES.get(series.variable, "-"), linewidth=1.0,
            label=f"{label}: observed monthly values (gaps = missing)")
    if np.isnan(values).all():
        ax.text(0.5, 0.5, "No valid values in this period", transform=ax.transAxes, ha="center", va="center")
    ax.set_ylabel(f"{label} ({unit_label})", fontsize=8)
    ax.set_xlabel("Date", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", fontsize=7, frameon=True)
    if annotation:
        ax.set_title(annotation, fontsize=7.5, loc="left")  # text only: no fitted line or band
    fig.tight_layout()
    return fig


def series_chart_png(series: TimeSeries, label: str, unit_label: str, annotation: str | None) -> bytes:
    fig = build_series_figure(series, label, unit_label, annotation)
    buffer = io.BytesIO()
    try:
        fig.savefig(buffer, format="png")
        return buffer.getvalue()
    finally:
        buffer.close()
        fig.clear()
