import sys
from types import SimpleNamespace, ModuleType
from unittest.mock import MagicMock
import httpx
import pytest
from code_agent import search_index

@pytest.mark.asyncio
@pytest.mark.parametrize('exists,count,outcome',[(True,0,'existing'),(False,0,'created'),(False,3,'missing_data')])
async def test_empty_document_index_is_initialized_without_hiding_lost_chunks(monkeypatch,exists,count,outcome):
    module=ModuleType('app.services.document.stores.elasticsearch_store')
    module._INDEX_SETTINGS={'settings':{'analysis':{'analyzer':{'nori_analyzer':{'type':'custom','tokenizer':'nori_tokenizer'}}}}}
    monkeypatch.setitem(sys.modules,module.__name__,module)
    seen=[]
    def handle(request):
        seen.append(request)
        return httpx.Response((200 if exists else 404) if request.method=='HEAD' else 200,json={})
    native=httpx.AsyncClient
    monkeypatch.setattr(search_index.httpx,'AsyncClient',lambda **kw:native(**kw,transport=httpx.MockTransport(handle)))
    engine=MagicMock();engine.connect.return_value.__enter__.return_value.execute.return_value.scalar.return_value=count
    if outcome=='missing_data':
        with pytest.raises(RuntimeError,match='재인덱싱'):await search_index.ensure_empty_document_index(SimpleNamespace(engine=engine),'http://es')
    else:await search_index.ensure_empty_document_index(SimpleNamespace(engine=engine),'http://es')
    assert [r.method for r in seen]==(['HEAD','PUT'] if outcome=='created' else ['HEAD'])
