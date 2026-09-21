from pathlib import Path

from conftest import ADMIN, USER, ScriptedGateway
from code_agent.store import Store
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from code_agent.api import create_router
from code_agent.store import DomainError

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / 'examples' / 'sample_code_catalog_200.xlsx'


def test_sample_200_xlsx_via_real_import_api(tmp_path):
    store = Store('sqlite:///' + str(tmp_path / 'sample200-api.db'))
    store.initialize()

    async def identity(authorization: str | None = Header(None)):
        if authorization == 'Bearer test-admin':
            return ADMIN
        if authorization == 'Bearer test-user':
            return USER
        raise HTTPException(401, '로그인 필요')

    app = FastAPI()
    class TestQuota:
        async def check(self,actor_id,operation): pass
    app.include_router(create_router(store, ScriptedGateway(store), identity, lambda: None, quota=TestQuota()))

    @app.exception_handler(DomainError)
    async def handler(request, exc):
        return JSONResponse({'detail': exc.message}, status_code=exc.status)

    with TestClient(app) as client:
        data = SAMPLE.read_bytes()
        preview = client.post(
            '/api/code-catalog/imports/preview',
            headers={'Authorization': 'Bearer test-admin'},
            files={'file': (SAMPLE.name, data, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},
        )
        assert preview.status_code == 200, preview.text
        p = preview.json()
        assert p['counts'] == {'new': 200, 'unchanged': 0, 'conflict': 0}
        assert p['errors'] == []
        assert p['warnings'] == []

        commit = client.post(
            f"/api/code-catalog/imports/{p['id']}/commit",
            headers={'Authorization': 'Bearer test-admin'},
            json={'expected_catalog_version': p['catalog_version']},
        )
        assert commit.status_code == 200, commit.text
        assert commit.json()['changed'] == 200

        listing = client.get(
            '/api/code-catalog/codes?include_retired=true&limit=200',
            headers={'Authorization': 'Bearer test-user'},
        )
        assert listing.status_code == 200
        body = listing.json()
        assert body['total'] == 200

        exact = client.get(
            '/api/code-catalog/codes/AT-2011',
            headers={'Authorization': 'Bearer test-user'},
        )
        assert exact.status_code == 200
        assert exact.json()['message'] == '이미 가입된 휴대폰 번호입니다.'

    store.engine.dispose()
