"""Task 7: PDF real-content integration.

- every included section is the object the API serves for the same request
- Group 3 methods/limitations text (docs/methods.md) and Adrian's summary hook
- correct AI labels; MOCK only in mock mode; real mode refuses mock/placeholder text
"""

from __future__ import annotations

import io
import sys
import types
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.advanced_schemas import ReportRequest
from app.main import create_app
from app.reports import hooks
from app.reports.checks import UnintendedPlaceholder, unintended_placeholders
from app.reports.content import AiSummary
from app.reports.pdf import build_pdf
from app.reports.service import assemble_report

API = "/api/v1"
FULL = {"region_id": "IGP", "variables": ["rainfall", "aod"], "start": "2003-01", "end": "2024-12",
        "season": "all", "include": ["trend", "anomalies", "interaction", "indicators"], "include_ai_summary": True}
METHODS_MD = """# Methods

Mann-Kendall test with Sen's slope on monthly regional means.

## Anomalies

Same-calendar-month percentiles against 2003-2024.

## Limitations

- Clear-sky AOD sampling under-represents rainy days.
- Regional boxes are not administrative boundaries.

## Changelog

- v1 reviewed by Group 3.
"""


def _pdf_text(content: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(content)).pages)


def _content(client, **overrides):
    req = ReportRequest(**{**FULL, **overrides})
    return assemble_report(client.app.state.store, req, app_name="TrendTrace", contract_version="1.0",
                           generated_at="2026-11-14T12:00:00+05:30")


@pytest.fixture
def summary_module(monkeypatch):
    """Installs a fake app.ai.report_summary; returns (module, list of calls received)."""
    calls: list = []
    module = types.ModuleType(hooks.AI_MODULE)

    def summarize(results):
        calls.append(results)
        return module.reply

    module.summarize = summarize
    module.reply = ("Computed results summarised for the selected region.", "template")
    monkeypatch.setitem(sys.modules, hooks.AI_MODULE, module)
    return module, calls


# ----------------------------------------------------------------- same objects as the API


def test_report_sections_are_the_objects_the_api_serves(client):
    content = _content(client)
    anomalies = client.get(f"{API}/anomalies", params={"region_id": "IGP", "variable": "both",
                                                     "start": "2003-01", "end": "2024-12"}).json()["result"]
    interaction = client.get(f"{API}/interaction", params={"region_id": "IGP", "season": "all"}).json()["result"]
    assert content.anomalies.model_dump(mode="json") == anomalies
    assert content.interaction.model_dump(mode="json") == interaction
    for name, result in content.indicators:
        api = client.get(f"{API}/rainfall/indicators",
                         params={"region_id": "IGP", "indicator": name, "season": "annual"}).json()["result"]
        assert result.model_dump(mode="json") == api


def test_report_section_with_other_period_is_not_printed_under_requested_dates(client):
    content = _content(client, start="2010-01")
    assert content.anomalies.period.start == "2010-01"  # sliced to the request, like the API
    assert content.interaction.reason.startswith("The interaction analysis exists only for 2003-01")


# ----------------------------------------------------------------- Group 3 text hook


def test_methods_markdown_splits_methods_and_limitations():
    texts = hooks.parse_methods_markdown(METHODS_MD)
    assert "Mann-Kendall" in texts.methods and "Same-calendar-month" in texts.methods
    assert "Limitations" not in texts.methods and "Changelog" not in texts.methods
    assert texts.limitations == ("Clear-sky AOD sampling under-represents rainy days.",
                                 "Regional boxes are not administrative boundaries.")


def test_missing_methods_file_means_not_delivered(tmp_path):
    assert hooks.load_report_texts(tmp_path / "methods.md") == hooks.ReportTexts(None, None)


def test_report_route_prints_group3_text_and_labelled_summary(client, tmp_path, monkeypatch, summary_module):
    _, calls = summary_module
    methods = tmp_path / "methods.md"
    methods.write_text(METHODS_MD, encoding="utf-8")
    monkeypatch.setattr(hooks, "METHODS_PATH", methods)
    created = client.post(f"{API}/report", json=FULL)
    assert created.status_code == 200, created.text
    text = _pdf_text(client.get(created.json()["result"]["url"]).content)
    assert "Mann-Kendall test with Sen" in text and "under-represents rainy days" in text
    assert "Automatic summary" in text and "Computed results summarised" in text
    assert "AI summary placeholder" not in text and "Placeholder: the reviewed methods" not in text
    assert any(getattr(r, "result_id", "").startswith("interaction_IGP_all") for r in calls[0])


@pytest.mark.parametrize("source,label", [("llm", "AI-generated explanation of computed results"),
                                          ("template", "Automatic summary")])
def test_ai_summary_label_follows_source(client, summary_module, source, label):
    module, _ = summary_module
    module.reply = ("Plain-language explanation.", source)
    content = _content(client)
    content = replace(content, ai_summary=hooks.ai_summary_for(content))
    assert content.ai_summary == AiSummary("Plain-language explanation.", source)
    assert label in _pdf_text(build_pdf(content).content)


def _raise(_results):
    raise RuntimeError("provider down")


@pytest.mark.parametrize("reply", [("text", "gpt"), ("   ", "llm"), None])
def test_bad_or_failing_summary_hook_never_breaks_the_report(client, summary_module, reply):
    module, _ = summary_module
    if reply is None:
        module.summarize = _raise
    else:
        module.reply = reply
    content = _content(client)
    assert hooks.ai_summary_for(content) is None
    assert build_pdf(content).pages >= 1


def test_no_summary_hook_installed_returns_none(client, monkeypatch):
    original = hooks.importlib.import_module
    def without_summary(name, *args, **kwargs):
        if name == hooks.AI_MODULE:
            raise ModuleNotFoundError(name)
        return original(name, *args, **kwargs)
    monkeypatch.setattr(hooks.importlib, "import_module", without_summary)
    assert hooks.ai_summary_for(_content(client)) is None


BROKEN_SUMMARY_MODULES = {
    "missing_dependency": "import trendtrace_missing_dependency_xyz\n",
    "syntax_error": "def summarize(:\n",
    "fails_at_import": "raise RuntimeError('provider client could not start')\n",
}


@pytest.fixture
def broken_summary_module(monkeypatch, tmp_path):
    """Places a real app/ai/report_summary.py with the given source on the app.ai package path."""
    import app.ai

    monkeypatch.setattr(app.ai, "__path__", [str(tmp_path), *app.ai.__path__])
    monkeypatch.delitem(sys.modules, hooks.AI_MODULE, raising=False)

    def install(source: str) -> None:
        (tmp_path / "report_summary.py").write_text(source, encoding="utf-8")

    yield install
    sys.modules.pop(hooks.AI_MODULE, None)


@pytest.mark.parametrize("kind", sorted(BROKEN_SUMMARY_MODULES))
def test_broken_summary_module_is_logged_and_never_breaks_the_report(client, broken_summary_module, caplog, kind):
    broken_summary_module(BROKEN_SUMMARY_MODULES[kind])
    with caplog.at_level("ERROR", logger="trendtrace.reports.hooks"):
        assert hooks.ai_summary_for(_content(client)) is None
    assert any(hooks.AI_MODULE in record.getMessage() for record in caplog.records), kind
    created = client.post(f"{API}/report", json=FULL)
    assert created.status_code == 200, created.text
    assert "AI summary placeholder" in _pdf_text(client.get(created.json()["result"]["url"]).content)


# ----------------------------------------------------------------- MOCK labels and the real-mode guard


def _as_real(content):
    """Same results relabelled real with mock wording scrubbed (stands in for G3's real files)."""
    sections = tuple(replace(s, trend=s.trend.model_copy(update={"limitations": [
        t for t in s.trend.limitations if "MOCK" not in t]})) for s in content.variables)
    sources = tuple(s.model_copy(update={"product": s.product.replace("MOCK stand-in for ", ""),
                                         "version": s.version.replace("MOCK", "V-test")})
                    for s in content.sources)
    return replace(content, data_status="real", data_version="2026-11-14a", variables=sections,
                   sources=sources, include=("trend",), anomalies=None, interaction=None, indicators=None,
                   include_ai_summary=False)


def test_real_mode_report_has_no_mock_label_and_honest_missing_text(client):
    content = _as_real(_content(client, include=["trend"], include_ai_summary=False))
    text = _pdf_text(build_pdf(content).content)
    assert "MOCK" not in text and "Results computed from NASA data" in text
    assert "Not available yet: the reviewed methods text from Group 3 has not been delivered" in text


def test_real_mode_refuses_mock_text_leaking_into_the_report(client):
    leaking = replace(_content(client, include=["trend"], include_ai_summary=False),
                      data_status="real", data_version="2026-11-14a")
    with pytest.raises(UnintendedPlaceholder, match="mock"):
        build_pdf(leaking)


@pytest.mark.parametrize("text", ["These are real values, not mock values.", "TODO: add the AOD sentence."])
def test_real_mode_summary_with_development_markers_is_dropped_not_fatal(client, summary_module, caplog, text):
    module, _ = summary_module
    module.reply = (text, "llm")
    content = replace(_as_real(_content(client, include=["trend"], include_ai_summary=False)),
                      include_ai_summary=True)
    with caplog.at_level("ERROR", logger="trendtrace.reports.hooks"):
        summary = hooks.ai_summary_for(content)
    assert summary is None and "development markers" in caplog.text
    pdf_text = _pdf_text(build_pdf(replace(content, ai_summary=summary)).content)
    assert "no automatic summary could be produced" in pdf_text and text not in pdf_text


def test_mock_mode_summary_may_mention_mock_data(client, summary_module):
    module, _ = summary_module
    module.reply = ("These MOCK values are illustrative only.", "template")
    assert hooks.ai_summary_for(_content(client)) == AiSummary("These MOCK values are illustrative only.", "template")


def test_real_mode_refuses_placeholder_methods_text(client):
    content = replace(_as_real(_content(client, include=["trend"], include_ai_summary=False)),
                      methods_text="TODO: Group 3 to write this.")
    with pytest.raises(UnintendedPlaceholder, match="todo"):
        build_pdf(content)


def test_mock_mode_keeps_mock_labels(client):
    text = _pdf_text(build_pdf(_content(client)).content)
    assert "MOCK DATA" in text and "MOCK sample report" in text


@pytest.mark.parametrize("text,found", [
    ("Results computed from NASA data", []), ("Mockingbird region", []), ("a MOCK value", ["mock"]),
    ("date YYYY-MM-01", ["yyyy"]), ("Placeholder text", ["placeholder"]),
])
def test_placeholder_markers_match_whole_words(text, found):
    assert unintended_placeholders([text]) == found


def test_real_mode_placeholder_becomes_report_failed(make_settings, tmp_path, monkeypatch):
    from app.routers import reports as reports_router

    def leak(*args, **kwargs):
        raise UnintendedPlaceholder("real-data report contains development text markers: ['mock']")

    monkeypatch.setattr(reports_router, "build_pdf", leak)
    with TestClient(create_app(make_settings(REPORTS_DIR=str(tmp_path)))) as c:
        response = c.post(f"{API}/report", json=FULL)
    assert response.status_code == 500 and response.json()["error"]["code"] == "REPORT_FAILED"
    assert "printable report" in response.json()["error"]["message"] and "mock" not in response.text
