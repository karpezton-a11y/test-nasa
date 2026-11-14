"""No real provider requests: injected fakes exercise the complete AI pipeline."""
import json

import httpx
import pytest

from app.ai.facts import build_facts
from app.ai.guardrails import NUMBER, check
from app.ai.service import ExplanationService, RateLimiter
from app.ai.resolve import ResultRegistry
from app.core_schemas import Explanation, LlmOutput
from app.config import REPO_ROOT
from app.schemas import Period, Envelope, TrendResult
from app.services.store import MockStore


@pytest.fixture
def trend():
    store = MockStore(REPO_ROOT / "data/mock/normal")
    return store.trend("IGP", "aod", Period(start="2003-01", end="2024-12"), "all")


@pytest.fixture
def facts(trend):
    return build_facts([trend], data_status="mock", data_version="MOCK-test")


def valid_output(facts):
    item = facts["items"][0]
    text = f"{item['significance_statement']} Slope: {item['slope']}; {item['p_value']}. Limitation: {item['limitations'][0]}"
    return LlmOutput(text=text, key_points=[], caveats=[], numbers_used=NUMBER.findall(text))


def test_valid_response_guardrails(facts):
    assert check(valid_output(facts), facts) == []


@pytest.mark.parametrize("extra,issue", [
    ("This was caused by pollution.", "causal_language"),
    ("This was because of rainfall.", "causal_language"),
    ("This leads to lower AOD.", "causal_language"),
    ("The value was 987654.321.", "unsupported_number"),
    ("AOD is PM2.5.", "aod_pm25_equivalence"),
    ("It is statistically significant.", "significance_mismatch"),
    ("<script>alert('x')</script>", "markup"),
])
def test_guardrails_reject_bad_claims(facts, extra, issue):
    output = valid_output(facts)
    output.text += " " + extra
    assert issue in check(output, facts)


def test_guardrails_reject_rounded_number_and_missing_limit(facts):
    facts["items"][0]["slope"] = "0.021 1 per decade"
    output = valid_output(facts)
    output.text = output.text.replace("0.021", "0.02")
    assert "unsupported_number" in check(output, facts)
    output = valid_output(facts)
    output.text = facts["items"][0]["significance_statement"]
    assert "limitation_missing" in check(output, facts)


def test_word_limit_and_numbers_used(facts):
    output = valid_output(facts)
    output.text += " word" * 121
    assert "word_limit" in check(output, facts)
    output = valid_output(facts); output.numbers_used = []
    assert "numbers_used_incomplete" in check(output, facts)


class FakeClient:
    def __init__(self, output=None, exc=None): self.output, self.exc, self.calls = output, exc, 0
    def generate(self, facts):
        self.calls += 1
        if self.exc: raise self.exc
        return self.output(facts) if callable(self.output) else self.output


def test_llm_cache_hit_and_defensive_copy(make_settings, trend):
    fake = FakeClient(lambda f: valid_output(f).model_dump())
    service = ExplanationService(make_settings(LLM_API_KEY="test-key"), fake)
    first = service.explain([trend], data_status="mock", data_version="MOCK-test")
    assert first.source == "llm" and first.guardrail.passed
    first.text = "tampered"
    second = service.explain([trend], data_status="mock", data_version="MOCK-test")
    assert fake.calls == 1 and second.text != "tampered"


@pytest.mark.parametrize("mode", ["timeout", "malformed", "causal"])
def test_provider_failure_uses_template(make_settings, trend, mode):
    fake = FakeClient(exc=httpx.ReadTimeout("secret-provider-details")) if mode == "timeout" else FakeClient("not JSON")
    if mode == "causal":
        def unsafe(f):
            raw = valid_output(f).model_dump(); raw["text"] += " This was caused by rain."; return raw
        fake = FakeClient(unsafe)
    service = ExplanationService(make_settings(LLM_API_KEY="test-key"), fake)
    result = service.explain([trend], data_status="mock", data_version="MOCK-test")
    assert result.source == "template" and "secret-provider-details" not in result.text
    assert result.guardrail.issues


def test_missing_key_never_calls_provider(make_settings, trend):
    fake = FakeClient(exc=AssertionError("must not call"))
    service = ExplanationService(make_settings(), fake)
    result = service.explain([trend], data_status="mock", data_version="MOCK-test")
    assert result.source == "template" and fake.calls == 0


def test_explain_id_refetch_and_inline_validation(client):
    trend = client.post("/api/v1/analyze", json={"region_id": "IGP", "variable": "aod"}).json()["result"]
    by_id = client.post("/api/v1/explain", json={"result_type": "trend", "result_id": trend["result_id"]})
    assert by_id.status_code == 200
    assert Envelope[Explanation].model_validate(by_id.json()).result.source == "template"
    bad = {**trend, "sen_slope": "invented"}
    response = client.post("/api/v1/explain", json={"result_type": "trend", "result": bad})
    assert response.status_code == 422 and response.json()["error"]["code"] == "VALIDATION_ERROR"
    response = client.post("/api/v1/explain", json={"result_type": "trend", "result_id": "../../secrets"})
    assert response.status_code == 404 and response.json()["error"]["code"] == "DATA_NOT_AVAILABLE"


def test_all_templates_and_server_advanced_ids(client):
    anomaly = client.get("/api/v1/anomalies", params={"region_id": "IGP", "variable": "both", "start": "2024-01", "end": "2024-12"}).json()["result"]
    interaction = client.get("/api/v1/interaction", params={"region_id": "IGP", "season": "JJAS"}).json()["result"]
    for kind, result in [("anomaly", anomaly), ("interaction", interaction)]:
        response = client.post("/api/v1/explain", json={"result_type": kind, "result_id": result["result_id"]})
        assert response.status_code == 200, response.text
        text = response.json()["result"]["text"]
        assert len(text.split()) <= 120
        if kind == "interaction": assert interaction["guardrail"] in text
    response = client.post("/api/v1/explain", json={"result_type": "summary", "result": {"results": [anomaly, interaction]}})
    assert response.status_code == 200 and interaction["guardrail"] in response.json()["result"]["text"]


def test_rate_limit_cannot_be_bypassed_with_cache_or_forwarded_ip(client):
    body = {"result_type": "trend", "result_id": "trend_IGP_aod_all_2003-01_2024-12"}
    for i in range(10):
        response = client.post("/api/v1/explain", json=body, headers={"X-Forwarded-For": f"1.2.3.{i}"})
        assert response.status_code == 200
    response = client.post("/api/v1/explain", json=body)
    assert response.status_code == 429 and response.json()["error"]["code"] == "RATE_LIMITED"


def test_rate_window_expires():
    now = [0.0]
    limiter = RateLimiter(clock=lambda: now[0])
    for _ in range(10): limiter.consume("peer")
    now[0] = 60
    limiter.consume("peer")
    assert len(limiter.clients["peer"]) == 1


def test_key_is_not_in_settings_repr(make_settings):
    settings = make_settings(LLM_API_KEY="should-never-appear", LLM_PROVIDER="openai", LLM_MODEL="selected-model")
    assert "should-never-appear" not in repr(settings)
    assert settings.llm_provider == "openai" and settings.llm_model == "selected-model"


def test_causal_or_spelled_number_in_free_text_does_not_break_template(make_settings, trend):
    trend = trend.model_copy(update={"limitations": ["One sensor has missing data due to clouds."]})
    service = ExplanationService(make_settings())
    result = service.explain([trend], data_status="mock", data_version="MOCK-test")
    # The unsafe limitation is never quoted; a safe caveat is used instead.
    assert result.source == "template" and "due to clouds" not in result.text and "Limitation:" in result.text


def test_provider_http_contract_with_mock_transport(make_settings, monkeypatch, facts):
    from app.ai.client import ProviderClient
    real_client = httpx.Client
    captured = []
    def handler(request):
        captured.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": valid_output(facts).model_dump_json()}}]})
    def factory(**kwargs):
        assert kwargs["timeout"] == 15.0 and kwargs["follow_redirects"] is False
        return real_client(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(httpx, "Client", factory)
    settings = make_settings(LLM_API_KEY="test-only", LLM_PROVIDER="openai", LLM_MODEL="chosen-model")
    raw = ProviderClient(settings).generate(facts)
    assert LlmOutput.model_validate_json(raw)
    payload = json.loads(captured[0].content)
    assert payload["temperature"] == 0.1 and payload["model"] == "chosen-model"
    assert "test-only" not in captured[0].content.decode()


def test_inline_cannot_poison_verified_result_id(client):
    raw = client.post("/api/v1/analyze", json={"region_id": "IGP", "variable": "aod"}).json()["result"]
    forged = {**raw, "limitations": ["Injected but schema-valid limitation."]}
    assert client.post("/api/v1/explain", json={"result_type": "trend", "result": forged}).status_code == 200
    response = client.post("/api/v1/explain", json={"result_type": "trend", "result_id": raw["result_id"]})
    assert response.status_code == 200 and "Injected" not in response.json()["result"]["text"]


@pytest.mark.parametrize("extra,issue", [
    ("This was caus\u200bed by rain.", "causal_language"),
    ("The value was 987654.321.", "unsupported_number"),
    ("AOD is PM2.5. AOD is a column optical measurement, not ground-level PM2.5.", "aod_pm25_equivalence"),
])
def test_guardrails_reject_visual_bypasses(facts, extra, issue):
    output = valid_output(facts); output.text += " " + extra
    assert issue in check(output, facts)


def test_template_failure_is_the_only_ai_unavailable_path(client, monkeypatch):
    from app.ai import service
    def broken(*args): raise RuntimeError("private template details")
    monkeypatch.setattr(service, "render", broken)
    response = client.post("/api/v1/explain", json={"result_type": "trend", "result_id": "trend_IGP_aod_all_2003-01_2024-12"})
    assert response.status_code == 503 and response.json()["error"]["code"] == "AI_UNAVAILABLE"
    assert "private template details" not in response.text


@pytest.mark.parametrize("provider,origin,field", [
    ("groq", "https://api.groq.com/openai/v1/chat/completions", "max_completion_tokens"),
    ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "max_tokens"),
])
def test_free_tier_providers_use_fixed_origins(make_settings, monkeypatch, facts, provider, origin, field):
    from app.ai.client import ProviderClient
    real_client = httpx.Client
    captured = []
    def handler(request):
        captured.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": valid_output(facts).model_dump_json()}}]})
    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    settings = make_settings(LLM_API_KEY="test-only", LLM_PROVIDER=provider, LLM_MODEL="m")
    assert LlmOutput.model_validate_json(ProviderClient(settings).generate(facts))
    assert str(captured[0].url) == origin and field in json.loads(captured[0].content)


def test_unknown_provider_falls_back_to_template(make_settings, trend):
    service = ExplanationService(make_settings(LLM_API_KEY="k", LLM_PROVIDER="grok", LLM_MODEL="m"))
    assert service.explain([trend], data_status="mock", data_version="MOCK-test").source == "template"


def test_llm_text_passes_guardrails_on_a_real_trendlib_result(make_settings):
    """Regression: trendlib limitations (PM2.5, 'significance' wording) made every provider answer fail."""
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.ai.facts import build_facts
    with TestClient(create_app(make_settings())) as c:
        trend = TrendResult.model_validate(c.post("/api/v1/analyze", json={"region_id": "IGP", "variable": "aod"}).json()["result"])
    facts = build_facts([trend], data_status="real", data_version="REAL-x")
    item = facts["items"][0]
    assert not any("PM2.5" in lim or "ignifican" in lim for lim in item["limitations"])

    class Model:  # a typical well-behaved model answer
        def generate(self, f):
            i = f["items"][0]
            return json.dumps({"text": f"{i['significance_statement']} Over {i['period']} the haze level changed by about "
                                       f"{i['slope']} ({i['p_value']}). Limitation: {i['limitations'][0]}",
                               "key_points": [], "caveats": [], "numbers_used": []})
    service = ExplanationService(make_settings(LLM_API_KEY="k", LLM_PROVIDER="groq", LLM_MODEL="openai/gpt-oss-120b"), client=Model())
    result = service.explain([trend], data_status="real", data_version="REAL-x")
    assert result.source == "llm", result.guardrail.issues
