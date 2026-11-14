"""PDF Discovery Report builder (ReportLab, A4). Section order follows DOCX section 8.1:
Cover, 1 Summary, 2 Charts, 3 Results tables, 4 Data quality and confidence,
5 Datasets, 6 Methods, 7 Limitations. All text from data is XML-escaped.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, Iterable
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..advanced_schemas import AnomalyBothResult, AnomalyResult, IndicatorResult, InteractionResult
from ..schemas import TimeSeries, TrendResult
from . import charts
from .checks import require_no_placeholders, story_text
from .content import ReportContent, Unavailable, VariableSection
from .formatting import (
    NA, fmt_bool, fmt_fraction, fmt_interval, fmt_number, fmt_p, fmt_pct, fmt_with_unit,
)

MARGIN = 18 * mm
MOCK_FOOTER = ("MOCK sample report by the {app} team; illustrative values, not NASA-derived results. "
               "Not an official NASA product.")
REAL_FOOTER = "Results computed from NASA data by the {app} team; not an official NASA product."
MOCK_BANNER = ("MOCK DATA: illustrative values for development only. "
               "These are not scientific results and not NASA data.")
LABEL_RULE = ("Label rule defined by the team; see Methods. "
              "It is not an official NASA or scientific confidence score.")
EVIDENCE_RULES = [
    ("insufficient_data", "record_years < 10, or valid_obs_pct < 70."),
    ("strong", "p < 0.05 AND CI excludes 0 AND every sensitivity run has the same sign AND at least two-thirds "
               "of sensitivity runs have p < 0.05 AND valid_obs_pct >= 90."),
    ("moderate", "p < 0.05 AND CI excludes 0 AND at least two-thirds of sensitivity runs have the same sign."),
    ("weak", "Everything else (including no significant trend): evidence for a trend is weak or absent."),
]
GENERAL_LIMITATIONS = [
    "Clear-sky sampling: MODIS retrieves AOD only without clouds, so rainy and monsoon days are under-sampled.",
    "AOD is a column measure of haze and particles seen from space, not ground-level PM2.5.",
    "Record length: about 22 years of data limits statistical power; only fairly strong changes are detectable.",
    "Sensor drift: recent orbit drift of Terra and Aqua may affect AOD; it is not quantified in this report.",
    "Regions are rectangular analysis boxes, not administrative boundaries.",
]
METHODS_PLACEHOLDER = ("Placeholder: the reviewed methods text from Group 3 (docs/methods.md) is pending "
                       "handoff H9 (Sun 11:00 IST). Methods are not described here yet.")
AI_PLACEHOLDER = ("AI summary placeholder - not generated. Member 1's /explain output will appear here, "
                  "labelled 'AI-generated explanation of computed results' or 'Automatic summary'.")
METHODS_PENDING = ("Not available yet: the reviewed methods text from Group 3 has not been delivered, "
                   "so the statistical methods are not described in this report.")
AI_NOT_AVAILABLE = "Not available: no automatic summary could be produced for this report."
NA_LEGEND = "n/a = not available (missing or not computed); never a zero. A real zero is printed as 0."
AI_LABELS = {"llm":"AI-generated explanation of computed results", "template": "Automatic summary"}


@dataclass(frozen=True)
class PdfArtifact:
    content: bytes
    pages: int


# ----------------------------------------------------------------- styles and small helpers


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    body = ParagraphStyle("Body", parent=base["BodyText"], fontName="Helvetica", fontSize=9.5, leading=12.5)
    return {
        "title": ParagraphStyle("T", parent=base["Title"], fontName="Helvetica-Bold", fontSize=22, leading=27),
        "h1": ParagraphStyle("H1", parent=base["Heading1"], fontName="Helvetica-Bold", fontSize=14, spaceBefore=6),
        "h2": ParagraphStyle("H2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=11, spaceBefore=6),
        "body": body,
        "small": ParagraphStyle("Small", parent=body, fontSize=8, leading=10, textColor=colors.HexColor("#444444")),
        "cell": ParagraphStyle("Cell", parent=body, fontSize=7.5, leading=9),
        "cellb": ParagraphStyle("CellB", parent=body, fontName="Helvetica-Bold", fontSize=7.5, leading=9),
        "banner": ParagraphStyle("Banner", parent=body, fontName="Helvetica-Bold", fontSize=11, leading=14,
                                 textColor=colors.HexColor("#8A6D00")),
        "guard": ParagraphStyle("Guard", parent=body, fontName="Helvetica-Bold"),
    }


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(text)), style)


def _table(header: list[str], rows: Iterable[list[str]], widths: list[float], st: dict) -> Table:
    data = [[_p(h, st["cellb"]) for h in header]] + [[_p(c, st["cell"]) for c in row] for row in rows]
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#BBBBBB")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEEE")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _widths(width: float, fractions: list[float]) -> list[float]:
    total = sum(fractions)
    return [width * f / total for f in fractions]


def _kv(pairs: list[tuple[str, str]], width: float, st: dict) -> Table:
    return _table(["Item", "Value"], [[k, v] for k, v in pairs], _widths(width, [0.35, 0.65]), st)


def _box(text: str, width: float, st: dict, background: str = "#F2F2F2", style: str = "body") -> Table:
    table = Table([[_p(text, st[style])]], colWidths=[width])
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(background)),
                               ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
                               ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return table


def _unavailable(item: Unavailable, width: float, st: dict) -> Table:
    return _box(f"Not available: {item.reason}", width, st)


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" + ("" if n == 1 else "s")


def _p_phrase(p: float | None) -> str:
    text = fmt_p(p)
    return f"p {text}" if text.startswith("<") else f"p = {text}"


# ----------------------------------------------------------------- cover and summary


def cover(c: ReportContent, st: dict, width: float) -> list[Any]:
    w, s, e, n = c.region.bbox
    story: list[Any] = [Spacer(1, 30 * mm), _p(f"{c.app_name} Discovery Report", st["title"]), Spacer(1, 6 * mm)]
    if c.is_mock:
        story += [_box(MOCK_BANNER, width, st, background="#FFF4CC", style="banner"), Spacer(1, 6 * mm)]
    story.append(_kv([
        ("Region", f"{c.region.name} ({c.region.region_id})"),
        ("Analysis box", f"[{w}, {s}, {e}, {n}] (lon/lat degrees; status: {c.region.status})"),
        ("Variables", ", ".join(v.label for v in c.variables)),
        ("Period", f"{c.period.start} to {c.period.end}"), ("Season", c.season),
        ("Sections", ", ".join(c.include)), ("Generated at", c.generated_at),
        ("data_version", c.data_version), ("data_status", c.data_status),
        ("contract_version", c.contract_version),
    ], width, st))
    return story + [PageBreak()]


def trend_verdict(section: VariableSection, c: ReportContent) -> str:
    t = section.trend  # the result's own period and season, never the request's
    head = f"{section.label}, {c.region.name}, {t.period.start} to {t.period.end} (season: {t.season}): "
    slope, ci = fmt_with_unit(t.sen_slope, t.slope_unit), fmt_interval(t.slope_ci, t.slope_unit)
    if t.significant:
        return f"{head}{t.direction} by about {slope} (95% CI {ci}); statistically significant ({_p_phrase(t.p_value)})."
    return (f"{head}slope {slope} (95% CI {ci}) is not statistically significant ({_p_phrase(t.p_value)}); "
            "no clear evidence of change.")


def _interaction_verdict(r: InteractionResult) -> str:
    events = f"{r.n_events_used} of {r.n_events} events usable"
    when = f"{r.season}, {r.period.start} to {r.period.end}"
    if r.status != "ok":
        return f"Interaction ({when}): {r.note}; {events}, so no test result is reported."
    return (f"Interaction ({when}): median AOD change after minus before heavy-rain days "
            f"{fmt_number(r.median_change, '1')} (95% CI {fmt_interval(r.median_change_ci, '1')}), "
            f"{_p_phrase(r.p_value)}; {events}.")


def _anomaly_results(result: AnomalyResult | AnomalyBothResult) -> list[AnomalyResult]:
    return list(result.results) if isinstance(result, AnomalyBothResult) else [result]


def _anomaly_verdict(result: AnomalyResult | AnomalyBothResult) -> str:
    parts = [_count(sum(a.category is not None for a in r.anomalies), f"{r.variable} month") + " flagged"
             for r in _anomaly_results(result)]
    both = (f"; {_count(len(result.combined_flags), 'month')} flagged in both variables"
            if isinstance(result, AnomalyBothResult) else "")
    return f"Anomalies ({result.period.start} to {result.period.end}): {', '.join(parts)}{both}."


def summary(c: ReportContent, st: dict, width: float) -> list[Any]:
    story: list[Any] = [_p("1. Summary of findings", st["h1"])]
    for section in c.variables:
        if section.trend is None:
            continue
        if isinstance(section.trend, Unavailable):
            story.append(_unavailable(section.trend, width, st))
            continue
        story += [_p(trend_verdict(section, c), st["body"]),
                  _p(f"Evidence (team rule v1): {section.trend.evidence.evidence_label}. {LABEL_RULE}", st["small"]),
                  Spacer(1, 3 * mm)]
    if c.anomalies is not None and not isinstance(c.anomalies, Unavailable):
        story.append(_p(_anomaly_verdict(c.anomalies), st["body"]))
    if c.interaction is not None and not isinstance(c.interaction, Unavailable):
        story += [_p(_interaction_verdict(c.interaction), st["body"]), _p(c.interaction.guardrail, st["guard"])]
    if c.include_ai_summary:
        story.append(Spacer(1, 3 * mm))
        if c.ai_summary is None:
            story.append(_box(AI_PLACEHOLDER if c.is_mock else AI_NOT_AVAILABLE, width, st))
        else:
            story += [_p(AI_LABELS[c.ai_summary.source], st["h2"]), _p(c.ai_summary.text, st["body"])]
    return story


# ----------------------------------------------------------------- charts


def _annotation(trend: TrendResult | Unavailable | None) -> str | None:
    if not isinstance(trend, TrendResult):
        return None
    note = "" if trend.significant else "; not statistically significant"
    return (f"Sen slope {fmt_with_unit(trend.sen_slope, trend.slope_unit)} "
            f"(95% CI {fmt_interval(trend.slope_ci, trend.slope_unit)}); {_p_phrase(trend.p_value)}{note}")


def charts_section(c: ReportContent, st: dict, width: float, keep_alive: list[io.BytesIO]) -> list[Any]:
    story: list[Any] = [PageBreak(), _p("2. Charts", st["h1"])]
    for section in c.variables:
        story.append(_p(f"{section.label} ({section.unit_label})", st["h2"]))
        if isinstance(section.series, Unavailable):
            story.append(_unavailable(section.series, width, st))
            continue
        png = io.BytesIO(charts.series_chart_png(section.series, section.label, section.unit_label,
                                                 _annotation(section.trend)))
        keep_alive.append(png)
        story += [Image(png, width=width, height=width * 2.9 / 7.2), Spacer(1, 2 * mm)]
    story.append(_p("Missing values are shown as gaps, never as zero. No trend line or band is drawn: the "
                    "results provide a slope and its range, not a fitted line (decision R-4).", st["small"]))
    return story


# ----------------------------------------------------------------- results tables


def _trend_rows(sections: Iterable[VariableSection]) -> list[list[str]]:
    rows = []
    for s in sections:
        t = s.trend
        if isinstance(t, TrendResult):
            rows.append([s.label, fmt_with_unit(t.sen_slope, t.slope_unit), fmt_interval(t.slope_ci, t.slope_unit),
                         fmt_p(t.p_value), t.direction.replace("_", " "), f"{t.n_valid} / {t.n_expected}",
                         fmt_pct(t.missing_pct), t.evidence.evidence_label])
    return rows


def _anomaly_tables(result: AnomalyResult | AnomalyBothResult, st: dict, width: float) -> list[Any]:
    story: list[Any] = []
    for r in _anomaly_results(result):
        flagged = [a for a in r.anomalies if a.category is not None]
        b, t = r.baseline, r.thresholds
        unit = "unitless" if r.unit == "1" else r.unit
        story.append(_p(f"{r.variable} ({unit}): baseline {b.start} to {b.end}, {b.method}, {b.statistic}, "
                        f"thresholds high {t.high} / low {t.low}; {len(r.anomalies)} months listed, "
                        f"{len(flagged)} flagged.", st["small"]))
        if not flagged:
            story.append(_p("No months met the threshold (a valid result).", st["body"]))
            continue
        rows = [[a.date.isoformat(), fmt_number(a.value, r.unit), fmt_number(a.baseline_median, r.unit),
                 NA if a.score is None else f"{a.score:.2f}", a.category or "", a.note] for a in flagged]
        story += [_table(["Date", "Value", "Baseline median", "Score", "Category", "Note"], rows,
                         _widths(width, [0.13, 0.11, 0.14, 0.09, 0.2, 0.33]), st), Spacer(1, 3 * mm)]
    if isinstance(result, AnomalyBothResult) and result.combined_flags:
        rows = [[f.date.isoformat(), f.category, f.rainfall_category, f.aod_category] for f in result.combined_flags]
        story += [_p("Months flagged in both variables", st["h2"]),
                  _table(["Date", "Combined flag", "Rainfall flag", "AOD flag"], rows,
                         _widths(width, [0.18, 0.3, 0.26, 0.26]), st)]
    return story


def _interaction_table(r: InteractionResult, st: dict, width: float) -> list[Any]:
    ma = r.monthly_association
    pairs = [
        ("Analysis period", f"{r.period.start} to {r.period.end}"),
        ("Season / status", f"{r.season} / {r.status}"), ("Note", r.note or "none"),
        ("Events found / usable", f"{r.n_events} / {r.n_events_used}"),
        ("Valid AOD days before / after", f"{fmt_pct(r.valid_aod_pct_before)} / {fmt_pct(r.valid_aod_pct_after)}"),
        ("AOD median before / after (unitless)",
         f"{fmt_number(r.aod_before_median, '1')} / {fmt_number(r.aod_after_median, '1')}"),
        ("Median change, after minus before (unitless)", fmt_number(r.median_change, "1")),
        (f"{int(r.ci_level * 100)}% CI ({r.ci_method})", fmt_interval(r.median_change_ci, "1")),
        (f"Test: {r.test}", f"p-value {fmt_p(r.p_value)}"),
        ("Control (random non-event days)", f"n = {r.control.n}, median change {fmt_number(r.control.median_change, '1')}"),
        ("Monthly association (Spearman)",
         f"rho {NA if ma.rho is None else f'{ma.rho:.2f}'}, n = {ma.n}, p-value {fmt_p(ma.p_value)}"),
    ]
    return [_kv(pairs, width, st), Spacer(1, 2 * mm), _p(r.guardrail, st["guard"])]


def _indicator_rows(items: Iterable[tuple[str, IndicatorResult | Unavailable]]) -> list[list[str]]:
    rows = []
    for name, item in items:
        if isinstance(item, Unavailable) or item.trend is None:
            continue
        t, valid = item.trend, sum(v.value is not None for v in item.values)
        years = f"{item.values[0].year}-{item.values[-1].year}" if item.values else NA
        rows.append([f"{name} ({item.season})", years, item.unit, f"{valid} / {len(item.values)}",
                     fmt_with_unit(t.sen_slope, t.slope_unit), fmt_interval(t.slope_ci, t.slope_unit),
                     fmt_p(t.p_value), t.direction.replace("_", " "), t.evidence.evidence_label])
    return rows


def results_tables(c: ReportContent, st: dict, width: float) -> list[Any]:
    story: list[Any] = [PageBreak(), _p("3. Results tables", st["h1"]), _p(NA_LEGEND, st["small"])]
    trend_rows = _trend_rows(c.variables)
    if trend_rows:
        story += [_p("3.1 Trends", st["h2"]),
                  _table(["Variable", "Sen slope", "95% CI", "p-value", "Direction", "Valid / expected",
                          "Missing", "Evidence"], trend_rows, _widths(width, [14, 17, 15, 8, 13, 11, 9, 11]), st)]
    if c.anomalies is not None:
        story.append(_p("3.2 Anomalies (flagged months)", st["h2"]))
        story += ([_unavailable(c.anomalies, width, st)] if isinstance(c.anomalies, Unavailable)
                  else _anomaly_tables(c.anomalies, st, width))
    if c.interaction is not None:
        story.append(_p("3.3 Rainfall-aerosol interaction", st["h2"]))
        story += ([_unavailable(c.interaction, width, st)] if isinstance(c.interaction, Unavailable)
                  else _interaction_table(c.interaction, st, width))
    if c.indicators is not None:
        story.append(_p("3.4 Rainfall indicators (regional mean)", st["h2"]))
        story += [_unavailable(i, width, st) for _, i in c.indicators if isinstance(i, Unavailable)]
        rows = _indicator_rows(c.indicators)
        if rows:
            story.append(_table(["Indicator (season)", "Years", "Unit", "Valid years", "Sen slope", "95% CI",
                                 "p-value", "Direction", "Evidence"], rows,
                                _widths(width, [18, 10, 6, 7, 15, 12, 7, 14, 9]), st))
    return story


# ----------------------------------------------------------------- data quality, datasets, methods, limitations


def quality(c: ReportContent, st: dict, width: float) -> list[Any]:
    story: list[Any] = [PageBreak(), _p("4. Data quality and confidence", st["h1"])]
    for section in c.variables:
        t = section.trend
        if not isinstance(t, TrendResult):
            continue
        e = t.evidence
        story += [_p(section.label, st["h2"]), _kv([
            ("Record length", f"{e.record_years:.1f} years"),
            ("Valid observations", f"{e.n_valid} of {e.n_expected} ({fmt_pct(e.valid_obs_pct)})"),
            ("Mean valid fraction", fmt_fraction(e.mean_valid_fraction)),
            ("Low-coverage months", str(e.low_coverage_months)),
            ("95% CI excludes zero", fmt_bool(e.ci_excludes_zero)),
            ("Evidence label (team rule v1)", e.evidence_label),
        ], width, st), Spacer(1, 2 * mm)]
        rows = [[r.name, fmt_with_unit(r.sen_slope, t.slope_unit), fmt_p(r.p_value), fmt_bool(r.same_sign)]
                for r in e.sensitivity]
        if rows:
            story.append(_table(["Sensitivity run", "Sen slope", "p-value", "Same sign as main result"], rows,
                                _widths(width, [0.3, 0.3, 0.15, 0.25]), st))
    story += [_p("Evidence label rule v1", st["h2"]),
              _table(["Label", "Rule"], [list(r) for r in EVIDENCE_RULES], _widths(width, [0.2, 0.8]), st),
              _p(LABEL_RULE, st["small"])]
    return story


def _used_source_ids(c: ReportContent) -> set[str]:
    ids = set()
    for s in c.variables:
        ids |= {x.source_id for x in (s.series, s.trend) if isinstance(x, (TimeSeries, TrendResult))}
    if isinstance(c.anomalies, (AnomalyResult, AnomalyBothResult)):
        ids |= {r.source_id for r in _anomaly_results(c.anomalies)}
    if isinstance(c.interaction, InteractionResult):
        ids |= set(c.interaction.source_ids.model_dump().values())
    ids |= {i.source_id for _, i in (c.indicators or ()) if isinstance(i, IndicatorResult)}
    return ids


def datasets(c: ReportContent, st: dict, width: float) -> list[Any]:
    used = _used_source_ids(c)
    rows = [[s.source_id, s.product, s.version, s.doi or NA,
             s.access_date.isoformat() if s.access_date else NA, s.citation or NA]
            for s in c.sources if s.source_id in used]
    return [PageBreak(), _p("5. Datasets", st["h1"]),
            _table(["Source ID", "Product", "Version", "DOI", "Access date", "Citation"], rows,
                   _widths(width, [0.27, 0.3, 0.08, 0.1, 0.11, 0.14]), st), _p(NA_LEGEND, st["small"])]


def methods(c: ReportContent, st: dict, width: float) -> list[Any]:
    story: list[Any] = [_p("6. Methods", st["h1"])]
    if not c.methods_text:
        return story + [_box(METHODS_PLACEHOLDER if c.is_mock else METHODS_PENDING, width, st)]
    return story + [_p(block.strip(), st["body"]) for block in c.methods_text.split("\n\n") if block.strip()]


def limitations(c: ReportContent, st: dict) -> list[Any]:
    items: list[str] = []
    trends = [s.trend for s in c.variables if isinstance(s.trend, TrendResult)]
    trends += [i.trend for _, i in (c.indicators or ()) if isinstance(i, IndicatorResult) and i.trend]
    general = list(c.limitations_text) if c.limitations_text else GENERAL_LIMITATIONS
    for text in [t for trend in trends for t in trend.limitations] + general:
        if text not in items:
            items.append(text)
    return [_p("7. Limitations", st["h1"])] + [_p(f"- {text}", st["body"]) for text in items]


# ----------------------------------------------------------------- footer + assembly


def _canvas_class(footer: str, is_mock: bool, pages: list[int]) -> type[Canvas]:
    class NumberedCanvas(Canvas):
        """Two-pass page numbering: 'Page X of Y' with the real total."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._page_states: list[dict] = []

        def showPage(self) -> None:  # noqa: N802 (ReportLab API)
            self._page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self) -> None:
            total = len(self._page_states)
            pages.append(total)
            for state in self._page_states:
                self.__dict__.update(state)
                self._draw_footer(total)
                super().showPage()
            super().save()

        def _draw_footer(self, total: int) -> None:
            width, height = A4
            self.setFont("Helvetica", 7)
            self.setFillColor(colors.HexColor("#555555"))
            self.drawString(MARGIN, 10 * mm, footer)
            self.drawRightString(width - MARGIN, 10 * mm, f"Page {self._pageNumber} of {total}")
            if is_mock:
                self.setFont("Helvetica-Bold", 9)
                self.setFillColor(colors.HexColor("#8A6D00"))
                self.drawRightString(width - MARGIN, height - 10 * mm, "MOCK DATA")

    return NumberedCanvas


def build_pdf(content: ReportContent) -> PdfArtifact:
    """Build the report. Returns the PDF bytes and the real page count."""
    buffer, pages, keep_alive = io.BytesIO(), [], []
    st = _styles()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN,
                            bottomMargin=20 * mm, title=f"{content.app_name} Discovery Report",
                            author=f"{content.app_name} team")
    width = doc.width
    story = [*cover(content, st, width), *summary(content, st, width),
             *charts_section(content, st, width, keep_alive), *results_tables(content, st, width),
             *quality(content, st, width), *datasets(content, st, width), *methods(content, st, width),
             *limitations(content, st)]
    footer = (MOCK_FOOTER if content.is_mock else REAL_FOOTER).format(app=content.app_name)
    if not content.is_mock:
        require_no_placeholders([*story_text(story), footer])  # real data: no mock/placeholder text
    try:
        doc.build(story, canvasmaker=_canvas_class(footer, content.is_mock, pages))
        return PdfArtifact(content=buffer.getvalue(), pages=pages[-1])
    finally:
        for png in keep_alive:
            png.close()
        buffer.close()
