"""Apple 온디바이스 Foundation Model을 OpenAI 호환 chat/completions로 노출하는 로컬 브리지.

macOS 26 이상, Apple Intelligence가 켜진 Apple Silicon Mac에서만 동작합니다. 브리지는 127.0.0.1에만
바인딩하며, Docker 안의 API는 host.docker.internal로 접근합니다. 모델 호출 자체는 같은 디렉터리의
applefm.swift를 컴파일한 워커가 맡고, 이 파일은 HTTP 변환·인증·워커 수명만 다룹니다.

프롬프트와 응답 본문은 로그에 남기지 않습니다. 토큰 사용량은 Apple 프레임워크가 제공하지 않으므로
응답에 usage를 넣지 않습니다(추정치를 실측처럼 보이게 하지 않습니다).
"""
from __future__ import annotations
import argparse
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / '.local' / 'apple-bridge'
SOURCE = Path(__file__).with_name('applefm.swift')
BINARY = STATE_DIR / 'applefm'
PID_FILE = STATE_DIR / 'bridge.pid'
LOG_FILE = STATE_DIR / 'bridge.log'
MODEL_ID = 'apple/on-device'
DEFAULT_PORT = 8787
DEFAULT_WORKERS = 2
REQUEST_TIMEOUT = 90


class BridgeError(Exception):
    def __init__(self, status: int, message: str, code: str = 'bridge_error'):
        super().__init__(message)
        self.status, self.message, self.code = status, message, code


def load_env(path: Path) -> dict[str, str]:
    """manage.load_env와 같은 규칙으로 .env를 읽습니다(따옴표 제거, 주석 무시)."""
    sys.path.insert(0, str(ROOT / 'scripts'))
    from manage import load_env as _load  # noqa: PLC0415
    return _load(path)


def bridge_token() -> str:
    token = os.environ.get('CODE_APPLE_BRIDGE_TOKEN', '').strip()
    if token:
        return token
    return load_env(ROOT / '.env').get('CODE_APPLE_BRIDGE_TOKEN', '').strip()


def build(force: bool = False) -> Path:
    """applefm.swift를 컴파일합니다. 원본보다 새로운 실행 파일이 있으면 건너뜁니다."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if BINARY.exists() and not force and BINARY.stat().st_mtime >= SOURCE.stat().st_mtime:
        return BINARY
    if sys.platform != 'darwin':
        raise BridgeError(500, 'Apple 브리지는 macOS에서만 빌드할 수 있습니다.', 'unsupported_platform')
    result = subprocess.run(['swiftc', '-O', '-parse-as-library', '-o', str(BINARY), str(SOURCE)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise BridgeError(500, 'applefm 컴파일 실패: ' + result.stderr.strip()[:800], 'build_failed')
    return BINARY


def check_availability() -> dict:
    """Apple Intelligence 온디바이스 모델의 가용성을 워커에 묻습니다."""
    binary = build()
    result = subprocess.run([str(binary), '--check'], capture_output=True, text=True, timeout=60)
    if result.returncode != 0 or not result.stdout.strip():
        raise BridgeError(500, 'applefm --check 실패: ' + result.stderr.strip()[:300], 'check_failed')
    return json.loads(result.stdout.strip().splitlines()[-1])


class WorkerPool:
    """고정 개수의 applefm 프로세스를 JSON 줄 프로토콜로 재사용합니다. 죽거나 시간 초과한 워커는 교체합니다."""

    def __init__(self, binary: Path, size: int = DEFAULT_WORKERS, timeout: float = REQUEST_TIMEOUT):
        self.binary, self.size, self.timeout = str(binary), size, timeout
        self.idle: queue.Queue = queue.Queue()
        for _ in range(size):
            self.idle.put(None)

    def _spawn(self) -> subprocess.Popen:
        return subprocess.Popen([self.binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True, bufsize=1)

    def call(self, request: dict) -> dict:
        proc = self.idle.get()
        try:
            if proc is None or proc.poll() is not None:
                proc = self._spawn()
            timed_out = threading.Event()

            def expire():
                timed_out.set()
                proc.kill()

            timer = threading.Timer(self.timeout, expire)
            timer.start()
            try:
                proc.stdin.write(json.dumps(request, ensure_ascii=False) + '\n')
                proc.stdin.flush()
                line = proc.stdout.readline()
            finally:
                timer.cancel()
            if not line:
                proc = None
                if timed_out.is_set():
                    raise BridgeError(504, f'온디바이스 모델 응답이 {int(self.timeout)}초를 넘어 중단했습니다.', 'timeout')
                raise BridgeError(502, '온디바이스 모델 워커가 응답 없이 종료됐습니다.', 'worker_exited')
            response = json.loads(line)
            if response.get('id') != request['id']:
                proc.kill()
                proc = None
                raise BridgeError(502, '워커 응답 식별자가 요청과 다릅니다.', 'worker_desync')
            return response
        finally:
            self.idle.put(proc)

    def close(self):
        while not self.idle.empty():
            proc = self.idle.get_nowait()
            if proc is not None and proc.poll() is None:
                proc.kill()


def text_of(content) -> str:
    """OpenAI 메시지 content(문자열 또는 파트 배열)에서 텍스트만 모읍니다."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return '\n'.join(part.get('text', '') for part in content if isinstance(part, dict) and part.get('type') == 'text')
    return ''


def worker_request(body: dict) -> dict:
    """chat/completions 본문을 워커 요청으로 바꿉니다. 지원하지 않는 옵션은 조용히 무시하지 않고 거부합니다."""
    if body.get('stream'):
        raise BridgeError(400, '스트리밍 응답은 지원하지 않습니다.', 'unsupported_parameter')
    model = body.get('model')
    if model != MODEL_ID:
        raise BridgeError(404, f'이 브리지는 {MODEL_ID} 모델만 제공합니다.', 'model_not_found')
    messages = body.get('messages')
    if not isinstance(messages, list) or not messages:
        raise BridgeError(400, 'messages가 필요합니다.', 'invalid_request')
    system = [text_of(m.get('content')) for m in messages if m.get('role') == 'system']
    rest = [m for m in messages if m.get('role') != 'system']
    if not rest:
        raise BridgeError(400, 'system 외 메시지가 하나 이상 필요합니다.', 'invalid_request')
    if len(rest) == 1 and rest[0].get('role') == 'user':
        prompt = text_of(rest[0].get('content'))
    else:
        prompt = '\n\n'.join(f"{m.get('role')}: {text_of(m.get('content'))}" for m in rest)
    request = {'id': uuid.uuid4().hex, 'prompt': prompt}
    if any(system):
        request['system'] = '\n\n'.join(s for s in system if s)
    if body.get('temperature') is not None:
        request['temperature'] = float(body['temperature'])
    limit = body.get('max_completion_tokens', body.get('max_tokens'))
    if limit is not None:
        request['max_tokens'] = int(limit)
    response_format = body.get('response_format')
    if response_format:
        kind = response_format.get('type')
        if kind == 'json_schema':
            spec = response_format.get('json_schema') or {}
            if not isinstance(spec.get('schema'), dict):
                raise BridgeError(400, 'response_format.json_schema.schema가 필요합니다.', 'invalid_request')
            request['schema'] = spec['schema']
            request['schema_name'] = spec.get('name') or 'Response'
        elif kind != 'text':
            raise BridgeError(400, f'response_format {kind}는 지원하지 않습니다.', 'unsupported_parameter')
    return request


def completion(worker_response: dict) -> dict:
    if worker_response.get('error'):
        raise BridgeError(502, f"온디바이스 모델 오류({worker_response.get('error_type')}): {worker_response['error']}"[:500], 'model_error')
    return {'id': 'chatcmpl-' + uuid.uuid4().hex[:24], 'object': 'chat.completion', 'created': int(time.time()),
            'model': MODEL_ID, 'system_fingerprint': 'apple-foundation-models',
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': worker_response.get('content', '')},
                         'finish_reason': 'stop', 'logprobs': None}]}


class Handler(BaseHTTPRequestHandler):
    server_version = 'apple-bridge/1'
    pool: WorkerPool
    token: str
    log_handle = None

    def log_message(self, fmt, *args):  # noqa: D401 - BaseHTTPRequestHandler 시그니처
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {self.address_string()} {fmt % args}\n"
        (self.log_handle or sys.stderr).write(line)
        (self.log_handle or sys.stderr).flush()

    def send_json(self, status: int, payload: dict, extra: dict | None = None):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, error: BridgeError):
        self.send_json(error.status, {'error': {'message': error.message, 'type': 'invalid_request_error' if error.status < 500 else 'server_error', 'code': error.code}})

    def authorized(self) -> bool:
        if not self.token:
            return True
        header = self.headers.get('Authorization', '')
        return header == f'Bearer {self.token}'

    def do_GET(self):  # noqa: N802
        if self.path == '/health':
            try:
                availability = check_availability()
                self.send_json(200 if availability.get('available') else 503, {'ok': bool(availability.get('available')), 'model': MODEL_ID, **availability})
            except BridgeError as error:
                self.send_error_json(error)
            return
        if not self.authorized():
            return self.send_error_json(BridgeError(401, '브리지 토큰이 필요합니다.', 'unauthorized'))
        if self.path == '/v1/models':
            return self.send_json(200, {'object': 'list', 'data': [{'id': MODEL_ID, 'object': 'model', 'owned_by': 'apple'}]})
        self.send_error_json(BridgeError(404, '알 수 없는 경로입니다.', 'not_found'))

    def do_POST(self):  # noqa: N802
        if not self.authorized():
            return self.send_error_json(BridgeError(401, '브리지 토큰이 필요합니다.', 'unauthorized'))
        if self.path != '/v1/chat/completions':
            return self.send_error_json(BridgeError(404, '알 수 없는 경로입니다.', 'not_found'))
        started = time.monotonic()
        try:
            length = int(self.headers.get('Content-Length') or 0)
            if length <= 0 or length > 4_000_000:
                raise BridgeError(400, '요청 본문 길이가 올바르지 않습니다.', 'invalid_request')
            try:
                body = json.loads(self.rfile.read(length))
            except ValueError as exc:
                raise BridgeError(400, 'JSON 본문을 해석할 수 없습니다.', 'invalid_request') from exc
            request = worker_request(body)
            result = completion(self.pool.call(request))
            self.send_json(200, result, {'X-Applefm-Duration-Ms': str(int((time.monotonic() - started) * 1000))})
        except BridgeError as error:
            self.send_error_json(error)


def make_server(pool: WorkerPool, token: str, host: str = '127.0.0.1', port: int = DEFAULT_PORT, log_handle=None) -> ThreadingHTTPServer:
    handler = type('BoundHandler', (Handler,), {'pool': pool, 'token': token, 'log_handle': log_handle})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def serve(port: int, workers: int) -> None:
    binary = build()
    availability = check_availability()
    if not availability.get('available'):
        raise BridgeError(503, f"Apple Intelligence 온디바이스 모델을 쓸 수 없습니다: {availability.get('reason')}", 'model_unavailable')
    pool = WorkerPool(binary, size=workers)
    server = make_server(pool, bridge_token(), port=port)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(json.dumps({'listening': f'http://127.0.0.1:{port}', 'model': MODEL_ID, 'workers': workers, 'token_required': bool(bridge_token())}), flush=True)
    try:
        while not stop.is_set():
            stop.wait(0.5)
    finally:
        server.shutdown()
        pool.close()


def health(port: int) -> dict | None:
    import urllib.request  # noqa: PLC0415
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=15) as response:
            return json.load(response)
    except Exception:  # noqa: BLE001 - 상태 조회 실패는 "실행 중 아님"으로 보고
        return None


def running_pid() -> int | None:
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def start(port: int, workers: int) -> dict:
    """브리지를 백그라운드로 띄우고 /health가 응답할 때까지 기다립니다. 모델을 쓸 수 없으면 실패합니다."""
    build()
    availability = check_availability()
    if not availability.get('available'):
        raise BridgeError(503, f"Apple Intelligence 온디바이스 모델을 쓸 수 없습니다: {availability.get('reason')}. 시스템 설정 → Apple Intelligence 및 Siri에서 켜 주세요.", 'model_unavailable')
    if running_pid() and health(port):
        return {'status': 'already_running', 'pid': running_pid(), 'port': port}
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log = open(LOG_FILE, 'a', encoding='utf-8')  # noqa: SIM115 - 자식 프로세스에 넘기는 핸들
    env = {**os.environ, 'CODE_APPLE_BRIDGE_TOKEN': bridge_token()}
    proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'serve', '--port', str(port), '--workers', str(workers)],
                            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True, env=env, cwd=str(ROOT))
    PID_FILE.write_text(str(proc.pid))
    os.chmod(PID_FILE, 0o600)
    for _ in range(60):
        if proc.poll() is not None:
            raise BridgeError(500, f'브리지가 바로 종료됐습니다. 로그: {LOG_FILE}', 'start_failed')
        status = health(port)
        if status and status.get('ok'):
            return {'status': 'started', 'pid': proc.pid, 'port': port, 'log': str(LOG_FILE)}
        time.sleep(0.5)
    raise BridgeError(500, f'브리지가 30초 안에 응답하지 않았습니다. 로그: {LOG_FILE}', 'start_timeout')


def stop() -> dict:
    pid = running_pid()
    if pid is None:
        PID_FILE.unlink(missing_ok=True)
        return {'status': 'not_running'}
    os.kill(pid, signal.SIGTERM)
    for _ in range(40):
        if running_pid() is None:
            break
        time.sleep(0.25)
    else:
        os.kill(pid, signal.SIGKILL)
    PID_FILE.unlink(missing_ok=True)
    return {'status': 'stopped', 'pid': pid}


def status(port: int) -> dict:
    return {'pid': running_pid(), 'port': port, 'health': health(port), 'binary': BINARY.exists(), 'log': str(LOG_FILE)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Apple 온디바이스 판정 브리지')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('serve', 'start', 'stop', 'status', 'build', 'check'):
        item = sub.add_parser(name)
        if name in ('serve', 'start', 'status'):
            item.add_argument('--port', type=int, default=int(os.environ.get('CODE_APPLE_BRIDGE_PORT', DEFAULT_PORT)))
        if name in ('serve', 'start'):
            item.add_argument('--workers', type=int, default=DEFAULT_WORKERS)
        if name == 'build':
            item.add_argument('--force', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'serve':
            serve(args.port, args.workers)
        elif args.command == 'start':
            print(json.dumps(start(args.port, args.workers), ensure_ascii=False))
        elif args.command == 'stop':
            print(json.dumps(stop(), ensure_ascii=False))
        elif args.command == 'status':
            report = status(args.port)
            print(json.dumps(report, ensure_ascii=False))
            return 0 if report['health'] and report['health'].get('ok') else 1
        elif args.command == 'build':
            print(build(force=args.force))
        elif args.command == 'check':
            report = check_availability()
            print(json.dumps(report, ensure_ascii=False))
            return 0 if report.get('available') else 1
        return 0
    except BridgeError as error:
        print(json.dumps({'error': error.message, 'code': error.code}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
