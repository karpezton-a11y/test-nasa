"""Integrate source-qualified methods and shared runtime without inventing science."""
import io

from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.config import REPO_ROOT
from app.main import create_app
from app.reports.hooks import load_report_texts
from app.reports.service import assemble_report
from app.advanced_schemas import ReportRequest
from app.core_schemas import LlmOutput
from app.ai.guardrails import NUMBER

BODY = {"region_id": "IGP", "variables": ["rainfall", "aod"], "start": "2003-01", "end": "2024-12",
        "season": "all", "include": ["trend"], "include_ai_summary": True}


def test_methods_document_is_source_qualified_and_keeps_limits():
    text = (REPO_ROOT / "docs/methods.md").read_text()
    assert "not a record that the statistical analysis has been independently validated" in text
    assert "Implemented trend engine" in text
    parsed = load_report_texts()
    assert "Hamed" in parsed.methods and len(parsed.limitations) >= 8
    assert "AOD" in " ".join(parsed.limitations)


def test_pdf_uses_immediate_template_without_provider_call(make_settings, tmp_path):
    with TestClient(create_app(make_settings(LLM_API_KEY="test-only", REPORTS_DIR=str(tmp_path)))) as client:
        class NeverCall:
            def generate(self, facts): raise AssertionError("PDF must not call the provider")
        client.app.state.explanations.client = NeverCall()
        response = client.post("/api/v1/report", json=BODY)
        assert response.status_code == 200, response.text
        pdf = client.get(response.json()["result"]["url"]).content
        text = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
        assert "Automatic summary" in text and "Hamed" in text and "MOCK" in text
        assert client.app.state.explanations.cache == {}


def test_pdf_reuses_guarded_cached_llm_text(make_settings, tmp_path):
    with TestClient(create_app(make_settings(LLM_API_KEY="test-only", REPORTS_DIR=str(tmp_path)))) as client:
        calls = []
        class Fake:
            def generate(self, facts):
                calls.append(facts)
                text = " ".join(i["significance_statement"] for i in facts["items"])
                text += " Limitation: " + facts["items"][0]["limitations"][0]
                return LlmOutput(text=text, key_points=[], caveats=[], numbers_used=NUMBER.findall(text)).model_dump()
        service = client.app.state.explanations
        service.client = Fake()
        content = assemble_report(client.app.state.store, ReportRequest(**BODY), app_name="TrendTrace",
                                  contract_version="1.0", generated_at="2026-11-14T09:00:00+00:00")
        info = client.app.state.store.info
        explained = service.explain(content.result_objects(), data_status=info.data_status, data_version=info.data_version)
        assert explained.source == "llm" and len(calls) == 1
        response = client.post("/api/v1/report", json=BODY)
        assert response.status_code == 200, response.text
        text = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(client.get(response.json()["result"]["url"]).content)).pages)
        assert "AI-generated explanation of computed results" in text and len(calls) == 1


def test_methods_text_is_safe_for_real_reports():
    """docs/methods.md is printed in real-data PDFs, which refuse development wording (checks.py)."""
    from app.reports.checks import unintended_placeholders
    assert unintended_placeholders([(REPO_ROOT / "docs/methods.md").read_text()]) == []
