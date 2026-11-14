"""Explanation text must retain the exact p-value relation and contain no links."""
import pytest

from app.ai.facts import build_facts
from app.ai.guardrails import check
from app.ai.templates import render
from app.config import REPO_ROOT
from app.schemas import Period
from app.services.store import MockStore


@pytest.fixture
def facts():
    store = MockStore(REPO_ROOT / 'data/mock/normal')
    trend = store.trend('IGP', 'aod', Period(start='2003-01', end='2024-12'), 'all')
    return build_facts([trend], data_status='mock', data_version='MOCK-test')


@pytest.mark.parametrize('claim', [
    'p > 0.004', 'p >= 0.004', 'p <= 0.004', 'p ≤ 0.004', 'p ≥ 0.004',
    'p != 0.004', 'p ≠ 0.004', 'p ≈ 0.004', 'p ~ 0.004',
    'p-value: 0.004', 'p value is 0.004',
    'p_value > 0.004', 'p is greater than 0.004', 'p less than 0.004',
    'p at least 0.004', 'p at most 0.004', 'p not equal to 0.004',
    'p above 0.004', 'p below 0.004', 'p approximately 0.004',
])
def test_changed_p_value_relation_is_rejected(facts, claim):
    output = render(facts)
    assert 'p = 0.004' in output.text
    output.text = output.text.replace('p = 0.004', claim)
    assert 'p_value_mismatch' in check(output, facts)


@pytest.mark.parametrize('link', [
    '[Read more](https://example.invalid)',
    '[Read more][external]',
    'https://example.invalid',
    'java\u200bscript:alert()',
    'data:text/html,unsafe',
])
def test_link_or_active_uri_is_rejected(facts, link):
    output = render(facts)
    output.text += ' ' + link
    assert 'markup' in check(output, facts)


def test_canonical_facts_still_pass(facts):
    assert check(render(facts), facts) == []


@pytest.mark.parametrize('unsafe,issue', [
    ('p > 0.004', 'p_value_mismatch'),
    ('[Read more](https://example.invalid)', 'markup'),
])
def test_unsafe_provider_output_uses_guarded_template(make_settings, unsafe, issue):
    from app.ai.service import ExplanationService

    class UnsafeClient:
        def generate(self, facts):
            output = render(facts)
            output.text = (output.text.replace('p = 0.004', unsafe) if unsafe.startswith('p ')
                           else output.text + ' ' + unsafe)
            return output.model_dump()

    store = MockStore(REPO_ROOT / 'data/mock/normal')
    trend = store.trend('IGP', 'aod', Period(start='2003-01', end='2024-12'), 'all')
    service = ExplanationService(make_settings(LLM_API_KEY='test-only'), UnsafeClient())
    result = service.explain([trend], data_status='mock', data_version='MOCK-test')
    assert result.source == 'template' and result.guardrail.passed
    assert issue in result.guardrail.issues
    assert 'p = 0.004' in result.text
    assert unsafe not in result.text
