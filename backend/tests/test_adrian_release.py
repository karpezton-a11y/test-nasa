"""Release requirements: configuration, secret scanning and frozen compatibility."""
import importlib.util
import json

import pytest
from pydantic import ValidationError

from app.config import ConfigError, REPO_ROOT, load_settings
from app.ai.facts import build_facts
from app.ai.guardrails import NUMBER, check
from app.core_schemas import LlmOutput
from app.schemas import Period
from app.services.store import MockStore


@pytest.mark.parametrize("origin", ["*", "null", "https://*.example", "https://one.example/path", "https://one.example/",
    "https://user:password@one.example", "https://one.example?x=y", "https://one.example#fragment",
    "https://one.example,https://two.example", "file:///path", "https://one.example:99999"])
def test_invalid_cors_configuration_refused(origin):
    with pytest.raises(ConfigError): load_settings(env={"ALLOWED_ORIGIN": origin}, env_file=None)


@pytest.mark.parametrize("port", ["0", "-1", "65536", "not-a-number"])
def test_invalid_port_refused(port):
    with pytest.raises(ConfigError): load_settings(env={"PORT": port}, env_file=None)


def test_secret_scanner_does_not_echo_values():
    spec = importlib.util.spec_from_file_location("security_audit", REPO_ROOT / "scripts/security_audit.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    secret = "sk-" + "x" * 40  # constructed test-only token, not a real credential
    findings = module.scan_bytes(secret.encode(), "test-only")
    assert findings and secret not in json.dumps(findings)
    assert module.scan_bytes(b"LLM_API_KEY=\n", ".env.example") == []


def test_p_value_cannot_be_replaced_by_a_unit_or_year():
    trend = MockStore(REPO_ROOT / "data/mock/normal").trend("IGP", "aod", Period(start="2003-01", end="2024-12"), "all")
    facts = build_facts([trend], data_status="mock", data_version="MOCK-test")
    item = facts["items"][0]
    text = item["significance_statement"] + " p = 1. " + item["limitations"][0]
    output = LlmOutput(text=text, key_points=[], caveats=[], numbers_used=NUMBER.findall(text))
    assert "p_value_mismatch" in check(output, facts)


def test_evidence_cannot_disagree_with_its_trend():
    from app.schemas import TrendResult
    trend = MockStore(REPO_ROOT / "data/mock/normal").trend("IGP", "aod", Period(start="2003-01", end="2024-12"), "all")
    raw = trend.model_dump()
    raw["evidence"]["p_value"] = 0.99
    with pytest.raises(ValidationError, match="evidence.p_value"):
        TrendResult.model_validate(raw)
