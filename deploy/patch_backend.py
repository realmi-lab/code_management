"""Small, fail-closed fixes applied to the container copy; upstream/ stays immutable."""
from pathlib import Path
import ast,json,sys,hashlib

def apply(root:Path):
    edits=[]
    def replace(path,old,new,count=1):
        p=root/path;s=p.read_text();found=s.count(old)
        if found!=count: raise RuntimeError(f'Upstream contract changed: {path} ({found} != {count})')
        output=s.replace(old,new);ast.parse(output)
        p.write_text(output);edits.append({'path':str(path),'before_sha256':hashlib.sha256(s.encode()).hexdigest(),'after_sha256':hashlib.sha256(output.encode()).hexdigest()})
    replace('app/api/search.py','CacheService.compute_settings_hash(settings.model_dump())',
            'CacheService.compute_settings_hash({**settings.model_dump(), "generate_answer": search_request.generate_answer})',2)
    replace('app/main.py','model="gpt-4.1-mini")','model=_rag.llm_model, temperature=_rag.llm_temperature)')
    replace('app/api/evaluation.py','run_evaluation_task.delay(str(run.dataset_id), str(run.id))',
            'run_evaluation_task.delay(str(run.dataset_id), str(run.id), _admin.id)')
    replace('app/tasks/evaluation.py','def run_evaluation_task(dataset_id: str, run_id: str):','def run_evaluation_task(dataset_id: str, run_id: str, user_id: int | None = None):')
    replace('app/tasks/evaluation.py','evaluator = RAGASEvaluator()',
            'evaluator = RAGASEvaluator()\n    evaluator._evaluation_user_id = user_id')
    replace('app/services/evaluation/ragas.py','settings = RAGSettings()',
            'from app.services.settings import SettingsService\n                settings = await SettingsService(db=db).get_settings()')
    replace('app/services/evaluation/ragas.py','        import httpx\n\n        async with httpx.AsyncClient() as client:',
            '''        import httpx
        import os
        from app.services.auth import create_access_token
        user_id = getattr(self, "_evaluation_user_id", None)
        if not user_id:
            raise RuntimeError("Evaluation requires the requesting user's identity")
        token = create_access_token(user_id, "user")
        base = os.environ.get("RAG_INTERNAL_API_URL", "http://rag-api:8000").rstrip("/")
        async with httpx.AsyncClient() as client:''')
    replace('app/services/evaluation/ragas.py','"http://localhost:8000/api/search",','base + "/api/search",\n                headers={"Authorization": "Bearer " + token},')
    replace('app/services/evaluation/ragas.py','            data = resp.json()', '            resp.raise_for_status()\n            data = resp.json()')
    # Do not let deleted documents remain searchable in the keyword store.
    replace('app/api/documents.py','    # 파일 삭제\n', '''    # Clean keyword index before deleting the authoritative document row.
    import httpx
    from app.config import get_settings
    async with httpx.AsyncClient(base_url=get_settings().elasticsearch_url, timeout=30) as es:
        response = await es.post("/rag_chunks/_delete_by_query?refresh=true",
                                 json={"query": {"term": {"document_id": str(doc.id)}}})
        if response.status_code != 404:
            response.raise_for_status()

    # 파일 삭제
''')
    (root/'catalog-patches.json').write_text(json.dumps(edits,indent=2))
    return edits
if __name__=='__main__':apply(Path(sys.argv[1] if len(sys.argv)>1 else '/app'))
