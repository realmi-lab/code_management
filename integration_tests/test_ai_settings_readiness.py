"""Readiness is checked against a synthetic HTTP response; no model download."""
import httpx
import pytest
from fastapi.testclient import TestClient
from code_agent import ai_config
from code_agent.embeddings import IDENTITY
from code_agent.store import DomainError
from test_api import app_for,headers


@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setenv('CODE_AI_SETTINGS_FILE',str(tmp_path/'ai.json'))
    monkeypatch.setenv('CODE_EMBEDDING_PROVIDER','none')
    monkeypatch.setenv('LOCAL_EMBEDDING_URL','http://synthetic-local:8080')
    monkeypatch.setenv('LOCAL_EMBEDDING_TOKEN','synthetic-token')
    for name in ai_config.KEYS.values():monkeypatch.delenv(name,raising=False)
    return monkeypatch


@pytest.mark.parametrize('payload,expected',[({'ready':True,'model':IDENTITY},'ready'),({'ready':False,'model':IDENTITY},'unavailable'),({'ready':True,'model':'wrong'},'model_mismatch'),([],'model_mismatch')])
def test_local_probe_validates_identity_and_ready(isolated,payload,expected):
    calls=[]
    def get(url,**kwargs):
        calls.append((url,kwargs))
        return httpx.Response(200,json=payload,request=httpx.Request('GET',url))
    isolated.setattr(ai_config.httpx,'get',get)
    status=ai_config.local_status()
    assert status['local_state']==expected
    assert status['local_available']==(expected=='ready')
    assert calls==[('http://synthetic-local:8080/health',{'timeout':2,'follow_redirects':False})]


def test_unavailable_local_cannot_be_saved_or_leak_exception(isolated):
    def get(*args,**kwargs):raise httpx.ConnectError('private internal connection details')
    isolated.setattr(ai_config.httpx,'get',get)
    result=ai_config.public()
    assert result['local_configured'] and not result['local_available']
    assert 'private internal' not in str(result)
    with pytest.raises(DomainError,match='아직 준비') as exc:
        ai_config.save({'version':0,'provider':'anthropic','embedding':'local','api_key':'synthetic'},1)
    assert exc.value.status==503


def test_url_without_service_token_is_unconfigured(isolated):
    isolated.delenv('LOCAL_EMBEDDING_TOKEN')
    assert ai_config.local_status()=={'local_configured':False,'local_available':False,'local_state':'unconfigured'}


@pytest.mark.parametrize('changes',[{'provider':[]},{'provider':{}},{'version':-1},{'version':True},{'embedding':[]},{'model':[]},{'api_key':42}])
def test_malformed_settings_return_validation_error(seeded,isolated,changes):
    body={'version':0,'provider':'anthropic','embedding':'none','api_key':'synthetic'}|changes
    with TestClient(app_for(seeded)) as client:
        response=client.put('/api/code-catalog/ai-settings',headers=headers('admin'),json=body)
    assert response.status_code==422


def test_oversized_settings_request_blocked(seeded,isolated):
    with TestClient(app_for(seeded)) as client:
        response=client.put('/api/code-catalog/ai-settings',headers=headers('admin'),content=b' '*12001)
    assert response.status_code==413


def test_claude_with_separate_openai_embedding_key(seeded,isolated):
    isolated.delenv('LOCAL_EMBEDDING_TOKEN')
    body={'version':0,'provider':'anthropic','embedding':'openai','api_key':'synthetic-claude','embedding_api_key':'synthetic-embedding'}
    with TestClient(app_for(seeded)) as client:
        response=client.put('/api/code-catalog/ai-settings',headers=headers('admin'),json=body)
        assert response.status_code==200
        assert response.json()['configured']['anthropic'] and response.json()['configured']['openai']
        assert 'synthetic-' not in response.text
    assert ai_config.key('ANTHROPIC_API_KEY')=='synthetic-claude'
    assert ai_config.key('OPENAI_API_KEY')=='synthetic-embedding'
