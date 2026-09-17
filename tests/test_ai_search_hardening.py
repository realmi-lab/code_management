import asyncio
import json
import os
import signal
import sys
import time

import httpx
import pytest

from catalog.ai import AI, AIError, fingerprint
from catalog.command_code import CommandCodeError, chat
from catalog.config import Settings
from .conftest import add

MODEL = 'deepseek/deepseek-v4.1-flash'


def ai_instance(tmp_path):
    return AI(Settings(data_dir=tmp_path, ai_enabled=True, ai_chat_model='test'))


def query_response():
    return {'choices': [{'message': {'content': json.dumps({'queries': ['휴대폰 번호 중복 가입']})}}]}


@pytest.mark.parametrize('content', [None, [], {}, 42, 'x' * 16001])
def test_malformed_draft_content_preserves_controlled_error(tmp_path, monkeypatch, content):
    ai = ai_instance(tmp_path)
    async def request(*args):
        return {'choices': [{'message': {'content': content}}]}
    monkeypatch.setattr(ai, 'request', request)
    with pytest.raises(AIError, match='형식'):
        asyncio.run(ai.draft('원문', '', '', []))


def test_simultaneous_identical_queries_share_one_model_call(tmp_path, monkeypatch):
    ai = ai_instance(tmp_path)
    calls = []
    async def scenario():
        ready, finish = asyncio.Event(), asyncio.Event()
        async def request(*args):
            calls.append(args)
            ready.set()
            await finish.wait()
            return query_response()
        monkeypatch.setattr(ai, 'request', request)
        tasks = [asyncio.create_task(ai.search_queries('예전에 쓰던 번호로 다시 가입')) for _ in range(8)]
        await ready.wait()
        await asyncio.sleep(0)
        finish.set()
        results = await asyncio.gather(*tasks)
        assert all(result[0] == ['휴대폰 번호 중복 가입'] for result in results)
        assert sum(result[1] for result in results) == 7
        assert len(calls) == 1
        assert not ai._query_tasks
    asyncio.run(scenario())


def test_cancelled_waiter_does_not_cancel_another_search(tmp_path, monkeypatch):
    ai = ai_instance(tmp_path)
    async def scenario():
        ready, finish = asyncio.Event(), asyncio.Event()
        async def request(*args):
            ready.set()
            await finish.wait()
            return query_response()
        monkeypatch.setattr(ai, 'request', request)
        first = asyncio.create_task(ai.search_queries('가입 안내'))
        await ready.wait()
        second = asyncio.create_task(ai.search_queries('가입 안내'))
        await asyncio.sleep(0)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        finish.set()
        assert (await second)[0] == ['휴대폰 번호 중복 가입']
        assert not ai._query_tasks
    asyncio.run(scenario())


def test_last_cancelled_waiter_stops_model_and_next_query_can_retry(tmp_path, monkeypatch):
    ai = ai_instance(tmp_path)
    async def scenario():
        ready, stopped = asyncio.Event(), asyncio.Event()
        async def request(*args):
            ready.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
        monkeypatch.setattr(ai, 'request', request)
        first = asyncio.create_task(ai.search_queries('가입 안내'))
        await ready.wait()
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert stopped.is_set() and not ai._query_tasks
        async def success(*args): return query_response()
        monkeypatch.setattr(ai, 'request', success)
        assert (await ai.search_queries('가입 안내'))[1] is False
    asyncio.run(scenario())


def test_failed_shared_query_does_not_poison_cache(tmp_path, monkeypatch):
    ai = ai_instance(tmp_path)
    async def scenario():
        calls = []
        async def failed(*args):
            calls.append(args)
            await asyncio.sleep(0)
            raise AIError('연결 실패')
        monkeypatch.setattr(ai, 'request', failed)
        results = await asyncio.gather(*(ai.search_queries('가입 안내') for _ in range(3)), return_exceptions=True)
        assert len(calls) == 1 and all(isinstance(x, AIError) for x in results)
        async def success(*args): return query_response()
        monkeypatch.setattr(ai, 'request', success)
        assert (await ai.search_queries('가입 안내'))[1] is False
    asyncio.run(scenario())


def test_http_output_limit_stops_reading_upstream_stream(tmp_path, monkeypatch):
    ai = ai_instance(tmp_path)
    read_chunks = []
    class TooLarge(httpx.AsyncByteStream):
        async def __aiter__(self):
            for index in range(24):
                read_chunks.append(index)
                yield b'x' * (1024 * 1024)
    async def handler(request):
        return httpx.Response(200, stream=TooLarge())
    real_client = httpx.AsyncClient
    def client(*args, **kwargs):
        return real_client(*args, **kwargs, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, 'AsyncClient', client)
    with pytest.raises(AIError, match='허용 크기'):
        asyncio.run(ai.request('/chat/completions', {}))
    assert len(read_chunks) == 17


def fake_cli(tmp_path, body):
    path = tmp_path / 'fake-cli'
    path.write_text('#!' + sys.executable + '\n' + body)
    path.chmod(0o700)
    return str(path)


def cli_settings(tmp_path, binary):
    return Settings(data_dir=tmp_path / 'data', ai_enabled=True, ai_provider='command-code',
                    ai_allow_external=True, ai_chat_model=MODEL, command_code_bin=binary, ai_timeout=5)


def test_cli_output_overflow_cleans_all_reader_tasks(tmp_path):
    binary = fake_cli(tmp_path, "import sys,time\nsys.stdin.read()\nsys.stderr.write('x'*2200000)\nsys.stderr.flush()\ntime.sleep(30)\n")
    async def scenario():
        with pytest.raises(CommandCodeError, match='허용 크기'):
            await chat(cli_settings(tmp_path, binary), {'messages': [{'content': '테스트'}]})
        pending = [task for task in asyncio.all_tasks() if task is not asyncio.current_task() and not task.done()]
        assert pending == []
    started = time.monotonic()
    asyncio.run(scenario())
    assert time.monotonic() - started < 5


@pytest.mark.skipif(os.name != 'posix', reason='POSIX process group contract')
def test_cli_cancellation_reaps_process(tmp_path):
    pidfile = tmp_path / 'pid'
    binary = fake_cli(tmp_path, 'import os,time\nfrom pathlib import Path\nPath(' + repr(str(pidfile)) + ').write_text(str(os.getpid()))\ntime.sleep(30)\n')
    async def scenario():
        task = asyncio.create_task(chat(cli_settings(tmp_path, binary), {'messages': [{'content': '테스트'}]}))
        for _ in range(100):
            if pidfile.exists(): break
            await asyncio.sleep(.01)
        assert pidfile.exists()
        pid = int(pidfile.read_text())
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        with pytest.raises(ProcessLookupError): os.kill(pid, 0)
        assert len(asyncio.all_tasks()) == 1
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['retire', 'edit'])
def test_embedding_search_refreshes_catalog_after_model_wait(client, monkeypatch, change):
    add(client)
    db, ai = client.app.state.db, client.app.state.ai
    ai.settings.ai_enabled = True
    ai.settings.ai_embedding_model = 'test'
    async def initial(texts): return [[1., 0.] for _ in texts]
    monkeypatch.setattr(ai, 'embeddings', initial)
    assert client.post('/api/ai/reindex').json()['indexed'] == 1
    async def changed(texts):
        with db.connect(write=True) as con:
            if change == 'retire':
                con.execute("UPDATE codes SET status='retired' WHERE namespace='live'")
            else:
                con.execute("UPDATE codes SET message='30초 이후 인증을 다시 확인해주세요.',revision=revision+1 WHERE namespace='live'")
            db.bump(con, 'live')
        return [[1., 0.]]
    monkeypatch.setattr(ai, 'embeddings', changed)
    result = client.post('/api/search', json={'query': '30초 인증 대기'}).json()
    assert result['catalog_version'] == db.version('live')
    assert result['embedding_coverage'] == 0
    assert result['mode'] == 'basic'
    if change == 'retire':
        assert result['results'] == []
    else:
        assert result['results'][0]['message'] == '30초 이후 인증을 다시 확인해주세요.'


def test_invalid_saved_embedding_falls_back_without_model_call(client, monkeypatch):
    add(client)
    db, ai = client.app.state.db, client.app.state.ai
    ai.settings.ai_enabled = True
    ai.settings.ai_embedding_model = 'test'
    row = db.get_code('live', 'AT-1923')
    with db.connect(write=True) as con:
        con.execute('INSERT INTO embeddings VALUES(?,?,?,?)', (row['id'], ai.embedding_identity, fingerprint(row), '{broken'))
    async def no_call(*args): raise AssertionError('Invalid vectors should not trigger inference')
    monkeypatch.setattr(ai, 'embeddings', no_call)
    result = client.post('/api/search', json={'query': '인증'}).json()
    assert result['mode'] == 'basic' and result['results']
    assert result['embedding_coverage'] == 0


def test_exact_code_lookup_does_not_scan_catalog(client, monkeypatch):
    add(client)
    def no_scan(*args, **kwargs): raise AssertionError('Exact lookup should use indexed rows and SQL count')
    monkeypatch.setattr(client.app.state.db, 'all_codes', no_scan)
    result = client.post('/api/search', json={'query': 'AT-1923'}).json()
    assert result['results'][0]['code'] == 'AT-1923'
    assert result['scope']['catalog_count'] == 1


def test_search_snapshot_keeps_catalog_version_consistent(client, monkeypatch):
    add(client)
    db = client.app.state.db
    old_version = db.version('live')
    original = db.all_codes
    def concurrent_edit(namespace, include_retired=True, con=None):
        rows = original(namespace, include_retired, con)
        with db.connect(write=True) as writer:
            writer.execute("UPDATE codes SET message='다른 문구',revision=revision+1 WHERE namespace='live'")
            db.bump(writer, 'live')
        return rows
    monkeypatch.setattr(db, 'all_codes', concurrent_edit)
    result = client.post('/api/search', json={'query': '인증'}).json()
    assert result['results'][0]['message'] == '메뉴확인 30초 이후에 인증해주세요.'
    assert result['catalog_version'] == old_version


def test_cached_features_refresh_changed_text(client):
    add(client)
    request = {'query': '30초 인증'}
    assert client.post('/api/search', json=request).json()['results']
    db = client.app.state.db
    with db.connect(write=True) as con:
        con.execute("UPDATE codes SET message='30초 인증을 다시 확인해주세요.',revision=revision+1 WHERE namespace='live'")
        db.bump(con, 'live')
    result = client.post('/api/search', json=request).json()
    assert result['results'][0]['message'] == '30초 인증을 다시 확인해주세요.'
