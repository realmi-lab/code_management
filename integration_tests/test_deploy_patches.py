"""Build-patch regression checks using minimal pinned-source CONTRACT fixtures.
Not a downloaded full upstream tree or a full upstream regression suite.
"""
from pathlib import Path
import importlib.util,sys,types,os,subprocess,json
from unittest.mock import AsyncMock
import httpx,pytest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('deployment_patch',ROOT/'deploy/patch_backend.py');patch=importlib.util.module_from_spec(spec);spec.loader.exec_module(patch)

EVALUATOR='''class RAGASEvaluator:
    async def evaluate(self, db):
                settings = RAGSettings()
    async def _run_search(self, question):
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "http://localhost:8000/api/search",
                json={"query": question, "generate_answer": True},
                timeout=60.0,
            )
            data = resp.json()
            return {"answer": data.get("answer", ""), "contexts": [r["content"] for r in data.get("results", [])]}
'''
@pytest.fixture
def patched(tmp_path):
    sources={
      'app/api/search.py':'a = CacheService.compute_settings_hash(settings.model_dump())\nb = CacheService.compute_settings_hash(settings.model_dump())\n',
      'app/main.py':'llm = OpenAILLM(api_key=env.openai_api_key, model="gpt-4.1-mini")\n',
      'app/api/evaluation.py':'run_evaluation_task.delay(str(run.dataset_id), str(run.id))\n',
      'app/tasks/evaluation.py':'def run_evaluation_task(dataset_id: str, run_id: str):\n    evaluator = RAGASEvaluator()\n',
      'app/services/evaluation/ragas.py':EVALUATOR,
      'app/api/documents.py':'async def remove(doc):\n    # 파일 삭제\n    await delete(doc)\n'}
    for path,content in sources.items():p=tmp_path/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content)
    patch.apply(tmp_path);return tmp_path

def test_cache_and_model_patch(patched):
    assert (patched/'app/api/search.py').read_text().count('"generate_answer": search_request.generate_answer')==2
    assert 'model=_rag.llm_model, temperature=_rag.llm_temperature' in (patched/'app/main.py').read_text()
    assert len(json.loads((patched/'catalog-patches.json').read_text()))==10

def test_patch_fails_closed_when_reapplied(patched):
    with pytest.raises(RuntimeError,match='contract changed'):patch.apply(patched)

def test_delete_orders_keyword_cleanup_before_db(patched):
    s=(patched/'app/api/documents.py').read_text();assert s.index('_delete_by_query?refresh=true')<s.index('await delete(doc)')
    assert 'response.raise_for_status()' in s

@pytest.mark.asyncio
@pytest.mark.parametrize('http_status',[200,401,503])
async def test_evaluation_authenticated_internal_http_and_failure(patched,monkeypatch,http_status):
    from test_upstream_adapter import module
    module(monkeypatch,'app.services.auth',create_access_token=lambda uid,role:'synthetic-token-for-'+str(uid))
    monkeypatch.setenv('RAG_INTERNAL_API_URL','http://rag-api:8000')
    observed=[];original_client=httpx.AsyncClient
    def responder(req):
        observed.append(req)
        return httpx.Response(http_status,json={'answer':'근거 답변','results':[{'content':'근거'}]})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original_client(transport=httpx.MockTransport(responder),**kwargs))
    ns={};exec((patched/'app/services/evaluation/ragas.py').read_text(),ns);e=ns['RAGASEvaluator']();e._evaluation_user_id=2
    if http_status==200:assert await e._run_search('질문')=={'answer':'근거 답변','contexts':['근거']}
    else:
        with pytest.raises(httpx.HTTPStatusError):await e._run_search('질문')
    assert str(observed[0].url)=='http://rag-api:8000/api/search'
    assert observed[0].headers['authorization']=='Bearer synthetic-token-for-2'

@pytest.mark.asyncio
async def test_evaluation_rejects_missing_identity(patched,monkeypatch):
    from test_upstream_adapter import module
    module(monkeypatch,'app.services.auth',create_access_token=lambda uid,role:'synthetic')
    ns={};exec((patched/'app/services/evaluation/ragas.py').read_text(),ns)
    with pytest.raises(RuntimeError,match='identity'):await ns['RAGASEvaluator']()._run_search('질문')

def test_frontend_sidebar_extension_keeps_original_items(tmp_path):
    p=tmp_path/'src/components/layout/sidebar.tsx';p.parent.mkdir(parents=True)
    p.write_text((ROOT/'integration_tests/fixtures/sidebar.tsx').read_text())
    subprocess.run(['node',str(ROOT/'deploy/patch_frontend.mjs')],cwd=tmp_path,check=True,capture_output=True)
    assert p.read_text().count('href: "/codes"')==1 and 'href: "/documents"' in p.read_text()
