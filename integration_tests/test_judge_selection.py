"""Apple bridge readiness as reported to the settings screen; the judge choice itself stays env-only."""
import httpx
from code_agent import ai_config

READY = {'apple_judge_state': 'ready', 'apple_judge_available': True}
DOWN = {'apple_judge_state': 'unavailable', 'apple_judge_available': False}


def test_judge_apple_status_reads_bridge_health(monkeypatch):
    monkeypatch.delenv('CODE_APPLE_BRIDGE_TOKEN', raising=False)
    assert ai_config.judge_apple_status() == {'apple_judge_state': 'unconfigured', 'apple_judge_available': False}
    monkeypatch.setenv('CODE_APPLE_BRIDGE_TOKEN', 'synthetic-bridge-token')
    monkeypatch.setenv('CODE_LLM_JUDGE_BASE_URL', 'http://bridge.test:8787/v1')
    calls = []

    def get(url, timeout, follow_redirects):
        calls.append(url)
        return httpx.Response(200, json={'ok': True, 'model': 'apple/on-device', 'available': True})
    monkeypatch.setattr(ai_config.httpx, 'get', get)
    assert ai_config.judge_apple_status() == READY and calls == ['http://bridge.test:8787/health']
    monkeypatch.setattr(ai_config.httpx, 'get', lambda *a, **k: httpx.Response(503, json={'ok': False, 'available': False, 'reason': 'appleIntelligenceNotEnabled'}))
    assert ai_config.judge_apple_status()['apple_judge_state'] == 'model_unavailable'

    def down(*a, **k):
        raise httpx.ConnectError('down')
    monkeypatch.setattr(ai_config.httpx, 'get', down)
    assert ai_config.judge_apple_status() == DOWN


def test_settings_body_no_longer_accepts_judge_fields():
    """The screen went back to two sections; a judge choice in the body is an unknown field."""
    import pytest
    from code_agent.store import DomainError
    with pytest.raises(DomainError) as error:
        ai_config.save({'version': 0, 'provider': 'commandcode', 'embedding': 'none', 'judge_mode': 'apple'}, 1)
    assert error.value.status == 422
