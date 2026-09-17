from __future__ import annotations
import json
import os
from fastapi.testclient import TestClient
from catalog.config import Settings
from catalog.main import create_app


def test_general_access_can_be_unlocked_by_configuration(tmp_path):
    settings = Settings(data_dir=tmp_path / 'data', access_token='', admin_password='test-admin-secret')
    with TestClient(create_app(settings)) as client:
        assert client.get('/api/meta').status_code == 200
        assert client.get('/api/meta').json()['authenticated'] is False


def test_admin_password_protects_runtime_ai_config_and_never_returns_key(tmp_path):
    data_dir = tmp_path / 'data'
    settings = Settings(data_dir=data_dir, access_token='', admin_password='test-admin-secret')
    with TestClient(create_app(settings)) as client:
        wrong = client.post('/api/admin/ai/state', json={'password': 'bad'})
        assert wrong.status_code == 403

        state = client.post('/api/admin/ai/state', json={'password': 'test-admin-secret'})
        assert state.status_code == 200
        assert state.json()['key_configured'] is False

        secret = 'test-api-secret-never-return'
        saved = client.post('/api/admin/ai/config', json={
            'password': 'test-admin-secret', 'enabled': True, 'provider': 'claude-code',
            'model': 'claude-sonnet-5', 'api_key': secret, 'base_url': '',
            'reasoning_effort': 'low',
        })
        assert saved.status_code == 200, saved.text
        body = saved.json()
        assert body['provider'] == 'claude-code'
        assert body['model'] == 'claude-sonnet-5'
        assert body['key_configured'] is True
        assert secret not in saved.text

        meta = client.get('/api/meta').json()
        assert meta['ai']['provider'] == 'claude-code'
        assert meta['ai']['chat_model'] == 'claude-sonnet-5'
        assert secret not in json.dumps(meta)

    path = data_dir / '.ai-runtime.json'
    assert path.exists()
    assert oct(path.stat().st_mode & 0o777) == '0o600'
    assert secret in path.read_text()

    # Persisted runtime configuration wins after a process restart.
    reloaded = Settings(data_dir=data_dir, access_token='', admin_password='test-admin-secret')
    with TestClient(create_app(reloaded)) as client:
        state = client.post('/api/admin/ai/state', json={'password': 'test-admin-secret'}).json()
        assert state['provider'] == 'claude-code'
        assert state['model'] == 'claude-sonnet-5'
        assert state['key_configured'] is True
        assert secret not in json.dumps(state)


def test_empty_key_keeps_existing_admin_key(tmp_path):
    settings = Settings(data_dir=tmp_path / 'data', access_token='', admin_password='test-admin-secret')
    with TestClient(create_app(settings)) as client:
        first = client.post('/api/admin/ai/config', json={
            'password': 'test-admin-secret', 'enabled': True, 'provider': 'claude-code',
            'model': 'claude-sonnet-5', 'api_key': 'first-secret', 'base_url': '',
            'reasoning_effort': 'low',
        })
        assert first.status_code == 200
        second = client.post('/api/admin/ai/config', json={
            'password': 'test-admin-secret', 'enabled': True, 'provider': 'claude-code',
            'model': 'claude-opus-5', 'api_key': None, 'base_url': '',
            'reasoning_effort': 'high',
        })
        assert second.status_code == 200
        assert settings.ai_key == 'first-secret'
        assert settings.ai_chat_model == 'claude-opus-5'
