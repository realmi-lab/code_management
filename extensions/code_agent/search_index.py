"""Initialize the upstream document index for a genuinely empty document store."""
import httpx
from sqlalchemy import text

async def ensure_empty_document_index(store, es_url):
    from app.services.document.stores.elasticsearch_store import _INDEX_SETTINGS
    async with httpx.AsyncClient(base_url=es_url, timeout=30) as client:
        response = await client.head('/rag_chunks')
        if response.status_code != 404:
            response.raise_for_status()
            return
        # Missing an index with existing chunks is data loss, not an empty search.
        with store.engine.connect() as connection:
            if connection.execute(text('SELECT count(*) FROM chunks')).scalar():
                raise RuntimeError('rag_chunks 검색 인덱스가 없습니다. 기존 문서를 재인덱싱해야 합니다.')
        response = await client.put('/rag_chunks', json=_INDEX_SETTINGS)
        if response.status_code == 400:
            error = response.json().get('error', {})
            if isinstance(error, dict) and error.get('type') == 'resource_already_exists_exception':
                return  # Another startup or first upload created it concurrently.
        response.raise_for_status()
