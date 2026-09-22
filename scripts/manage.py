#!/usr/bin/env python3
"""Install and run the COMPLETE upstream tree, not a reimplementation.

Python standard library only. Source download is atomic and verified against
GitHub's pinned Git tree. Existing sources, .env files and Docker volumes are
never removed by this program. Application secrets are never included in reports.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import getpass
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
MAX_ARCHIVE = 128 * 1024 * 1024
MAX_UNPACKED = 512 * 1024 * 1024
MAX_FILES = 20000


class SetupError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def lock_spec(root: Path = ROOT) -> dict:
    lock = json.loads((root / 'upstream.lock.json').read_text())
    for key in ('commit', 'tree'):
        if not re.fullmatch(r'[a-f0-9]{40}', lock[key]):
            raise SetupError(f'Invalid source lock: {key}')
    if lock['repository'] != 'https://github.com/urstory/urstory-rag.git':
        raise SetupError('The source repository must be reviewed before it is changed.')
    return lock


def git_hash(kind: str, data: bytes) -> str:
    return hashlib.sha1(f'{kind} {len(data)}\0'.encode() + data).hexdigest()


def tree_manifest(root: Path) -> dict:
    """Compute the Git tree from disk, including file modes and symlink values.

    This works for the official source archive as well as a clean local git
    checkout. No git executable, staging operation or mutation is required.
    .git metadata at the root is excluded; all other files are checked.
    """
    root = root.resolve()
    files: list[dict] = []

    def walk(directory: Path) -> bytes:
        entries: list[tuple[bytes, bytes]] = []
        for item in directory.iterdir():
            if directory == root and item.name == '.git':
                continue
            name = os.fsencode(item.name)
            rel = item.relative_to(root).as_posix()
            if item.is_symlink():
                mode = '120000'
                raw = os.fsencode(os.readlink(item))
                digest = git_hash('blob', raw)
                sort_key = name
            elif item.is_dir():
                child_tree = walk(item)
                # Git's working-tree index does not track empty directories.
                if not child_tree:
                    continue
                digest = git_hash('tree', child_tree)
                mode = '40000'
                sort_key = name + b'/'
                entries.append((sort_key, mode.encode() + b' ' + name + b'\0' + bytes.fromhex(digest)))
                continue
            elif item.is_file():
                mode = '100755' if item.stat().st_mode & 0o111 else '100644'
                raw = item.read_bytes()
                digest = git_hash('blob', raw)
                sort_key = name
            else:
                raise SetupError(f'Unsupported source entry: {rel}')
            files.append({'path': rel, 'mode': mode, 'git_blob': digest,
                          'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
            entries.append((sort_key, mode.encode() + b' ' + name + b'\0' + bytes.fromhex(digest)))
        return b''.join(value for _, value in sorted(entries, key=lambda pair: pair[0]))

    digest = git_hash('tree', walk(root))
    return {'tree': digest, 'file_count': len(files), 'files': sorted(files, key=lambda item: item['path'])}


def verify_source(source: Path, lock: dict) -> dict:
    if not source.is_dir():
        raise SetupError('원본 전체 소스가 없습니다. prepare 또는 start를 실행하세요.')
    manifest = tree_manifest(source)
    if manifest['tree'] != lock['tree']:
        raise SetupError('원본 전체 파일의 Git tree가 고정 버전과 다릅니다. 기존 폴더는 변경하지 않았습니다.')
    missing = [p for p in lock['required_files'] if not (source / p).is_file()]
    if missing:
        raise SetupError('필수 파일이 없습니다: ' + ', '.join(missing))
    return {'repository': lock['repository'], 'commit': lock['commit'], 'verified_at': utc_now(), **manifest}


def _member_path(name: str, prefix: str) -> PurePosixPath:
    if '\\' in name or name.startswith('/'):
        raise SetupError('Unsafe archive path.')
    value = PurePosixPath(name)
    if '..' in value.parts or not value.parts or value.parts[0] != prefix:
        raise SetupError('Unsafe archive path or multiple archive roots.')
    return PurePosixPath(*value.parts[1:])


def unpack_archive(blob: bytes, destination: Path) -> None:
    if len(blob) > MAX_ARCHIVE:
        raise SetupError('Source archive is larger than the download limit.')
    try:
        with tarfile.open(fileobj=io.BytesIO(blob), mode='r:gz') as archive:
            members = archive.getmembers()
            if not members or len(members) > MAX_FILES:
                raise SetupError('Invalid number of source archive entries.')
            root_parts = PurePosixPath(members[0].name).parts
            if not root_parts:
                raise SetupError('Invalid archive root.')
            prefix = root_parts[0]
            total = 0
            plans = []
            seen = set()
            for member in members:
                relative = _member_path(member.name, prefix)
                if str(relative) == '.':
                    if not member.isdir():
                        raise SetupError('Invalid archive root.')
                    continue
                if relative.parts[0] == '.git' or relative in seen:
                    raise SetupError('Duplicate or forbidden source entry.')
                seen.add(relative)
                if not (member.isdir() or member.isfile() or member.issym()):
                    raise SetupError('Source archive contains a special file or hard link.')
                total += member.size
                if total > MAX_UNPACKED:
                    raise SetupError('Unpacked source exceeds the size limit.')
                plans.append((member, relative))
            # A symlink must never be traversed while writing later entries.
            links = {p for member, p in plans if member.issym()}
            for _, rel in plans:
                if any(parent in links for parent in rel.parents):
                    raise SetupError('Archive tries to write through a symlink.')
            for member, relative in plans:
                path = destination.joinpath(*relative.parts)
                path.parent.mkdir(parents=True, exist_ok=True)
                if member.isdir():
                    path.mkdir(exist_ok=True)
                elif member.isfile():
                    handle = archive.extractfile(member)
                    if handle is None:
                        raise SetupError('Missing source file data.')
                    with handle, path.open('xb') as output:
                        shutil.copyfileobj(handle, output)
                    path.chmod(0o755 if member.mode & 0o111 else 0o644)
                else:
                    target = member.linkname
                    if '\\' in target or PurePosixPath(target).is_absolute():
                        raise SetupError('Unsafe source symlink.')
                    if not (path.parent / target).resolve().is_relative_to(destination.resolve()):
                        raise SetupError('Source symlink escapes its directory.')
                    path.symlink_to(target)
    except (tarfile.TarError, OSError, ValueError) as exc:
        raise SetupError(f'원본 압축파일을 안전하게 풀지 못했습니다: {type(exc).__name__}') from exc


def fetch_archive(commit: str) -> bytes:
    url = f'https://codeload.github.com/urstory/urstory-rag/tar.gz/{commit}'
    req = urllib.request.Request(url, headers={'User-Agent': 'code-management-full-installer/1.0'})
    context = ssl.create_default_context()
    # python.org macOS installs may lack a configured CA bundle. Add the OS
    # trust store while retaining hostname/certificate verification and overrides.
    if sys.platform == 'darwin' and not os.getenv('SSL_CERT_FILE') and Path('/etc/ssl/cert.pem').is_file():
        context.load_verify_locations('/etc/ssl/cert.pem')
    try:
        with urllib.request.urlopen(req, timeout=120, context=context) as response:
            data = response.read(MAX_ARCHIVE + 1)
        if len(data) > MAX_ARCHIVE:
            raise SetupError('Source archive exceeds the download limit.')
        return data
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SetupError('GitHub 원본 전체 다운로드에 실패했습니다. 네트워크를 확인하거나 --archive/--source로 원본을 지정하세요. 원본 대신 경량판을 실행하지 않습니다.') from exc


def private_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix='.write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(text)
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


@contextmanager
def install_lock(root: Path):
    state = root / '.local'
    state.mkdir(exist_ok=True)
    path = state / 'prepare.lock'
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise SetupError('다른 설치 작업의 잠금이 있습니다. 중단된 작업인지 확인한 후 .local/prepare.lock을 정리하세요.') from exc
    try:
        os.write(fd, f'{os.getpid()} {utc_now()}\n'.encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


def prepare(root: Path = ROOT, source: Path | None = None, archive: Path | None = None) -> dict:
    lock = lock_spec(root)
    target = root / 'upstream'
    with install_lock(root):
        if target.exists():
            report = verify_source(target, lock)
        else:
            with tempfile.TemporaryDirectory(prefix='.source-download-', dir=root) as temp:
                staging = Path(temp) / 'tree'
                staging.mkdir()
                if source:
                    verify_source(source, lock)
                    # Root .git metadata is not part of a Git tree or the delivered source.
                    for child in source.iterdir():
                        if child.name == '.git':
                            continue
                        dst = staging / child.name
                        if child.is_symlink():
                            dst.symlink_to(os.readlink(child))
                        elif child.is_dir():
                            shutil.copytree(child, dst, symlinks=True)
                        else:
                            shutil.copy2(child, dst)
                else:
                    data = archive.read_bytes() if archive else fetch_archive(lock['commit'])
                    unpack_archive(data, staging)
                report = verify_source(staging, lock)
                if target.exists():
                    raise SetupError('설치 중 원본 폴더가 생성되었습니다. 기존 폴더를 덮어쓰지 않습니다.')
                staging.rename(target)
        private_write(root / '.local/upstream-manifest.json', json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f'원본 전체 검증 통과: {report["file_count"]}개 파일 · {report["commit"][:7]}')
    return report


def load_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            raise SetupError('.env에는 KEY=value 형식만 사용할 수 있습니다.')
        key, value = line.split('=', 1)
        key = key.strip()
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*', key) or key in values:
            raise SetupError('.env에 잘못된 키 또는 중복 키가 있습니다.')
        if value[:1] in ("'", '"'):
            if len(value) < 2 or value[-1] != value[0]:
                raise SetupError('.env의 따옴표를 확인하세요.')
            value = value[1:-1]
        values[key] = value
    return values


def encode_env(values: dict[str, str]) -> str:
    lines = ['# PRIVATE: generated locally. Never commit, upload, or share this file.']
    for key, value in values.items():
        if any(c in value for c in ("'", '\n', '\r', '\x00')):
            raise SetupError(f'{key} contains unsupported quote/newline characters.')
        lines.append(f"{key}='{value}'")
    return '\n'.join(lines) + '\n'


def validate_admin_password(value: str) -> None:
    if (len(value)<12 or not re.search(r'[A-Z]',value) or not re.search(r'[a-z]',value)
        or not re.search(r'\d',value) or not re.search(r'[!@#$%^&*(),.?":{}|<>]',value)):
        raise SetupError('ADMIN_PASSWORD는 최소 12자, 대소문자·숫자·특수문자를 포함해야 합니다.')


def configure(root: Path = ROOT, interactive: bool = True) -> dict[str, str]:
    env_path = root / '.env'
    values = load_env(env_path)
    defaults = {
        'COMPOSE_PROJECT_NAME': 'code-management-full',
        'POSTGRES_USER': 'rag', 'POSTGRES_DB': 'rag',
        'ADMIN_USERNAME': 'admin', 'LANGFUSE_ADMIN_EMAIL': 'admin@example.local',
        'WEB_PORT': '3500', 'API_PORT': '8000', 'LANGFUSE_PORT': '3100', 'CATALOG_PORT': '8766',
        'OPENAI_API_KEY': '', 'CODE_CATALOG_AUTHORITY':'system',
        'CODE_LLM_PROVIDER':'openai','CODE_EMBEDDING_PROVIDER':'none',
        'CODE_AUTH_MODE':'local','ADMIN_PASSWORD':'',
        'POSTGRES_IMAGE': 'pgvector/pgvector:pg17',
        'ES_IMAGE': 'docker.elastic.co/elasticsearch/elasticsearch:8.17.0',
        'REDIS_IMAGE': 'redis:7-alpine', 'CLICKHOUSE_IMAGE': 'clickhouse/clickhouse-server:24.12',
        'LANGFUSE_WEB_IMAGE': 'langfuse/langfuse:3', 'LANGFUSE_WORKER_IMAGE': 'langfuse/langfuse-worker:3',
        'MINIO_IMAGE': 'quay.io/minio/minio:RELEASE.2025-04-22T22-12-26Z',
        'MINIO_MC_IMAGE': 'quay.io/minio/mc:RELEASE.2025-04-16T18-13-26Z',
    }
    for key, value in defaults.items():
        values.setdefault(key, value)
    for key in ('POSTGRES_PASSWORD', 'REDIS_PASSWORD', 'JWT_SECRET_KEY', 'NEXTAUTH_SECRET',
                'LANGFUSE_SALT', 'LANGFUSE_ENCRYPTION_KEY', 'CLICKHOUSE_PASSWORD',
                'LANGFUSE_REDIS_PASSWORD', 'MINIO_ROOT_PASSWORD', 'CATALOG_ACCESS_TOKEN',
                'CODE_APPLE_BRIDGE_TOKEN'):
        if not values.get(key):
            values[key] = secrets.token_hex(32)
    if not values.get('LOCAL_EMBEDDING_TOKEN'):values['LOCAL_EMBEDDING_TOKEN']=secrets.token_hex(32)
    for key in ('ADMIN_PASSWORD', 'LANGFUSE_ADMIN_PASSWORD'):
        if key=='ADMIN_PASSWORD' and values.get('CODE_AUTH_MODE')=='local':continue
        if not values.get(key):
            values[key] = 'Aa1!' + secrets.token_hex(18)
    for key, prefix in (('LANGFUSE_PUBLIC_KEY', 'pk-lf-'), ('LANGFUSE_SECRET_KEY', 'sk-lf-')):
        if not values.get(key):
            values[key] = prefix + secrets.token_hex(24)
    needs_openai = values.get('CODE_LLM_PROVIDER','openai')=='openai' or values.get('CODE_EMBEDDING_PROVIDER','openai')=='openai'
    if interactive and needs_openai and not values.get('OPENAI_API_KEY'):
        print('현재 OpenAI가 선택되어 있습니다. 키를 입력하거나 Enter를 눌러 건너뛴 뒤 화면에서 공급자를 선택하세요.')
        values['OPENAI_API_KEY'] = getpass.getpass('OpenAI API 키 (화면에 표시되지 않음): ').strip()
    for port_name in ('WEB_PORT', 'API_PORT', 'LANGFUSE_PORT', 'CATALOG_PORT'):
        try:
            valid = 1 <= int(values[port_name]) <= 65535
        except ValueError:
            valid = False
        if not valid:
            raise SetupError(f'{port_name}가 올바른 포트가 아닙니다.')
        values[port_name]=str(int(values[port_name]))
    if len({values[name] for name in ('WEB_PORT', 'API_PORT', 'LANGFUSE_PORT', 'CATALOG_PORT')}) != 4:
        raise SetupError('각 서비스의 호스트 포트는 달라야 합니다.')
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', values['COMPOSE_PROJECT_NAME']):
        raise SetupError('COMPOSE_PROJECT_NAME은 소문자·숫자·하이픈·밑줄만 사용하세요.')
    # These values are placed in URLs / init identifiers. Do not silently misparse them.
    for key in ('POSTGRES_USER', 'POSTGRES_DB'):
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,40}', values[key]):
            raise SetupError(f'{key}: use a simple lowercase SQL identifier.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,}', values['POSTGRES_PASSWORD']):
        raise SetupError('POSTGRES_PASSWORD must use URL-safe characters (16+).')
    if values['CODE_AUTH_MODE'] not in ('local','jwt'):raise SetupError('CODE_AUTH_MODE는 local 또는 jwt여야 합니다.')
    if values['CODE_AUTH_MODE']=='jwt':validate_admin_password(values['ADMIN_PASSWORD'])
    from urllib.parse import quote
    values['REDIS_PASSWORD_URLENCODED']=quote(values['REDIS_PASSWORD'],safe='')
    if values['CODE_CATALOG_AUTHORITY'] not in ('excel','system'): raise SetupError('CODE_CATALOG_AUTHORITY는 excel 또는 system이어야 합니다.')
    private_write(env_path, encode_env(values))
    print('로컬 설정 준비 완료: .env (기존 비밀번호와 키는 유지)')
    return values


def run(command: list[str], *, cwd: Path = ROOT, capture: bool = False) -> subprocess.CompletedProcess:
    try:
        env=os.environ.copy()
        # Ensure checked values are the same values passed to Compose. Preserve Docker context/proxy.
        values=load_env(cwd / '.env')
        for rogue in ('COMPOSE_FILE','COMPOSE_PROFILES','COMPOSE_ENV_FILES'):
            env.pop(rogue,None)
        env.update(values)
        return subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=capture, env=env)
    except FileNotFoundError as exc:
        raise SetupError(f'{command[0]} 실행 파일이 없습니다.') from exc
    except subprocess.CalledProcessError as exc:
        # Do not echo stdout/stderr from commands that may contain rendered secrets.
        raise SetupError(f'{command[0]} 명령이 실패했습니다 (종료코드 {exc.returncode}). 이전 명령의 오류를 확인하세요.') from exc


def docker_preflight(root: Path = ROOT) -> None:
    run(['docker', 'info', '--format', '{{.ServerVersion}}'], cwd=root, capture=True)
    version = run(['docker', 'compose', 'version', '--short'], cwd=root, capture=True).stdout.strip()
    match = re.match(r'v?(\d+)\.(\d+)', version)
    if not match or tuple(map(int, match.groups())) < (2, 20):
        raise SetupError('Docker Compose v2.20 이상이 필요합니다.')


def compose_args(root: Path = ROOT, legacy: bool = False) -> list[str]:
    values=load_env(root / '.env')
    args = ['docker', 'compose', '--project-name', values.get('COMPOSE_PROJECT_NAME','code-management-full'), '--env-file', str(root / '.env'), '-f', str(root / 'compose.yaml')]
    if legacy:
        args += ['--profile', 'legacy']
    if values.get('CODE_EMBEDDING_PROVIDER')=='local':args+=['--profile','local-embedding']
    return args


def check_ports(values: dict[str, str], legacy: bool = False) -> None:
    keys = ['WEB_PORT', 'API_PORT', 'LANGFUSE_PORT'] + (['CATALOG_PORT'] if legacy else [])
    if len({int(values[k]) for k in keys})!=len(keys): raise SetupError('호스트 포트가 중복됩니다.')
    for key in keys:
        sock = socket.socket()
        try:
            sock.bind(('127.0.0.1', int(values[key])))
        except OSError as exc:
            raise SetupError(f'{key}={values[key]} 포트가 사용 중입니다. 기존 앱은 종료하지 않았습니다. .env에서 포트를 바꾸세요.') from exc
        finally:
            sock.close()


def start(root: Path = ROOT, *, legacy: bool = False, source: Path | None = None,
          archive: Path | None = None, interactive: bool = True, open_browser: bool = True) -> None:
    docker_preflight(root)
    values = configure(root, interactive=interactive)
    if values.get('CODE_LLM_PROVIDER') not in (None,'openai','commandcode','anthropic','deepseek','apple'):raise SetupError('지원하지 않는 LLM 공급자입니다.')
    if values.get('CODE_EMBEDDING_PROVIDER','none') not in ('openai','local','none'):
        raise SetupError('지원하지 않는 임베딩 공급자입니다.')
    if not environment_ready(values):
        print('AI 키가 없는 공급자의 호출은 차단됩니다. 로그인 후 알림 코드 → AI 설정에서 키를 입력하세요.')
    if judge_bridge_required(values) or sys.platform == 'darwin':
        # The admin screen offers the Apple judge only while the bridge answers, so start it whenever this Mac can serve it.
        # When the env forces the Apple judge, fail before the long build instead of judging every turn into an error.
        try:
            apple_bridge('stop', root)
            bridge = apple_bridge('start', root)
            print(f"Apple 온디바이스 판정 브리지 실행 중: http://127.0.0.1:{bridge.get('port', 8787)} (pid {bridge.get('pid')})")
        except SetupError as exc:
            if judge_bridge_required(values):
                raise
            print(f'Apple 온디바이스 판정 브리지는 준비하지 않았습니다(선택 불가): {exc}')
    args = compose_args(root, legacy)
    # Configuration check does not print interpolated secrets.
    run(args + ['config', '--quiet'], cwd=root)
    running = run(args + ['ps', '--status', 'running', '--services'], cwd=root, capture=True).stdout.strip()
    if not running:
        check_ports(values, legacy)
    prepare(root, source=source, archive=archive)
    print('원본 전체 소스 검증 완료. 원본 프론트·API·검색·워커·모니터링을 빌드합니다.')
    if values.get('CODE_EMBEDDING_PROVIDER')=='local':
        run(args + ['up','-d','--build','--wait','--wait-timeout','1800','local-embeddings'],cwd=root)
    run(args + ['up', '-d', '--build', '--wait', '--wait-timeout', '900'], cwd=root)
    images = run(args + ['images', '--format', 'json'], cwd=root, capture=True).stdout
    private_write(root / '.local/runtime-images.json', images)
    print('컨테이너 기동 확인 완료. 실제 문서 검색 품질 검증과는 별개입니다.')
    print(f'원본 화면: http://localhost:{values["WEB_PORT"]}')
    print(f'모니터링: http://localhost:{values["LANGFUSE_PORT"]}')
    print('로그인 정보: python3 scripts/manage.py credentials')
    if legacy:
        print(f'별도 보존된 구버전 코드 관리 화면: http://localhost:{values["CATALOG_PORT"]} (원본과 자동 통합 아님)')
    if open_browser:
        webbrowser.open(f'http://localhost:{values["WEB_PORT"]}/codes')


def environment_ready(values):
    keys={'commandcode':'COMMANDCODE_API_KEY','anthropic':'ANTHROPIC_API_KEY','deepseek':'DEEPSEEK_API_KEY','openai':'OPENAI_API_KEY','apple':'CODE_APPLE_BRIDGE_TOKEN'}
    llm=bool(values.get(keys.get(values.get('CODE_LLM_PROVIDER','openai'),'')))
    mode=values.get('CODE_EMBEDDING_PROVIDER','none')
    embedding=True if mode=='none' else bool(values.get('LOCAL_EMBEDDING_TOKEN')) if mode=='local' else bool(values.get('OPENAI_API_KEY')) if mode=='openai' else False
    return llm and embedding


def judge_bridge_required(values: dict[str, str]) -> bool:
    """CODE_LLM_JUDGE_PROVIDER=apple sends the two judge stages to the Mac-side Apple bridge."""
    return values.get('CODE_LLM_JUDGE_PROVIDER', '').strip() == 'apple' or values.get('CODE_LLM_PROVIDER') == 'apple'


def apple_bridge(command: str, root: Path = ROOT) -> dict:
    """Run extensions/apple_bridge/bridge.py <command>; surface its JSON error instead of a generic failure."""
    script = root / 'extensions' / 'apple_bridge' / 'bridge.py'
    env = {**os.environ, **{k: v for k, v in load_env(root / '.env').items() if k == 'CODE_APPLE_BRIDGE_TOKEN'}}
    result = subprocess.run([sys.executable, str(script), command], cwd=root, text=True, capture_output=True, env=env)
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else result.stdout.strip()[-300:]
        raise SetupError(f'Apple 판정 브리지 {command} 실패: {detail}')
    try:
        return json.loads(result.stdout.strip().splitlines()[-1]) if result.stdout.strip() else {}
    except ValueError:
        return {'output': result.stdout.strip()[-300:]}


def doctor(root: Path = ROOT) -> dict:
    checks = []
    values = load_env(root / '.env')
    for name, callback in (
        ('source_tree', lambda: verify_source(root / 'upstream', lock_spec(root))),
        ('docker', lambda: docker_preflight(root)),
        ('environment', lambda: environment_ready(values)),
        *([('apple_bridge', lambda: apple_bridge('check', root).get('available', False))] if judge_bridge_required(values) else []),
    ):
        try:
            result = callback()
            if result is False:
                raise SetupError('LLM or embedding credentials/provider not configured')
            checks.append({'check': name, 'ok': True})
        except SetupError as exc:
            checks.append({'check': name, 'ok': False, 'detail': str(exc)})
    report = {'at': utc_now(), 'checks': checks, 'passed': all(c['ok'] for c in checks),
              'note': 'Preflight only. This is not an LLM quality, security or deployment certification.'}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='UrstoryRAG 원본 전체 실행 관리')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'start'):
        item = sub.add_parser(name)
        group = item.add_mutually_exclusive_group()
        group.add_argument('--source', type=Path, help='이미 받은 원본 git checkout 경로')
        group.add_argument('--archive', type=Path, help='고정 커밋의 공식 tar.gz 파일')
        if name == 'start':
            item.add_argument('--legacy', action='store_true', help='구버전 앱을 별도 서비스로 함께 실행')
            item.add_argument('--non-interactive', action='store_true')
            item.add_argument('--no-browser', action='store_true')
    configure_parser = sub.add_parser('configure')
    configure_parser.add_argument('--non-interactive', action='store_true')
    for name in ('verify', 'doctor', 'credentials', 'status', 'stop'):
        sub.add_parser(name)
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            prepare(source=args.source, archive=args.archive)
        elif args.command == 'start':
            start(source=args.source, archive=args.archive, legacy=args.legacy,
                  interactive=not args.non_interactive, open_browser=not args.no_browser)
        elif args.command == 'configure':
            configure(interactive=not args.non_interactive)
        elif args.command == 'verify':
            report = verify_source(ROOT / 'upstream', lock_spec())
            print(f'원본 전체 {report["file_count"]}개 파일·모드 일치 / tree={report["tree"]}')
        elif args.command == 'doctor':
            return 0 if doctor()['passed'] else 1
        elif args.command == 'credentials':
            values = load_env(ROOT / '.env')
            if not values:
                raise SetupError('configure를 먼저 실행하세요.')
            if values.get('CODE_AUTH_MODE','local')=='local':
                print('로컬 모드: 로그인이나 관리자 비밀번호 없이 접속합니다.')
                print('http://localhost:'+values.get('WEB_PORT','3500')+'/codes')
                return 0
            for label, key in [('원본 관리자 ID', 'ADMIN_USERNAME'), ('원본 관리자 비밀번호', 'ADMIN_PASSWORD'),
                               ('Langfuse ID', 'LANGFUSE_ADMIN_EMAIL'), ('Langfuse 비밀번호', 'LANGFUSE_ADMIN_PASSWORD'),
                               ('구버전 코드 관리 접속 키', 'CATALOG_ACCESS_TOKEN')]:
                print(f'{label}: {values.get(key, "미설정")}')
            print('기존 DB의 비밀번호를 .env 변경만으로 초기화하지 않습니다. API 키는 출력하지 않았습니다.')
        elif args.command in ('status', 'stop'):
            docker_preflight()
            # stop is intentionally not down -v. Data and unrelated projects remain.
            run(compose_args(legacy=True) + (['ps', '--all'] if args.command == 'status' else ['stop']))
            values = load_env(ROOT / '.env')
            if args.command == 'stop':
                if (ROOT / '.local' / 'apple-bridge' / 'bridge.pid').exists():
                    print('Apple 판정 브리지:', apple_bridge('stop'))
            elif judge_bridge_required(values):
                try:
                    print('Apple 판정 브리지:', apple_bridge('status'))
                except SetupError as exc:
                    print(f'Apple 판정 브리지: 실행 중 아님 ({exc})')
        return 0
    except (SetupError, OSError) as exc:
        print(f'중단: {exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('사용자가 중단했습니다. 기존 파일과 Docker 볼륨은 삭제하지 않았습니다.', file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
