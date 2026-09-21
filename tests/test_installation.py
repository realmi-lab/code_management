from __future__ import annotations
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import manage as m
from render_compose import build_compose


class Fixtures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make_source(self, name='source'):
        source = self.root / name
        (source / 'backend/app').mkdir(parents=True)
        (source / 'README.md').write_text('테스트 원본입니다. 실제 urstory-rag 소스가 아닙니다.\n')
        (source / 'backend/app/main.py').write_text('VALUE = 1\n')
        return source

    def lock(self, source):
        return {'repository': 'https://github.com/urstory/urstory-rag.git', 'commit': 'a' * 40,
                'tree': m.tree_manifest(source)['tree'], 'required_files': ['README.md', 'backend/app/main.py']}

    def package(self, source):
        package = self.root / 'package'
        package.mkdir()
        (package / 'upstream.lock.json').write_text(json.dumps(self.lock(source)))
        return package

    def archive(self, entries):
        out = io.BytesIO()
        with tarfile.open(fileobj=out, mode='w:gz') as tf:
            top = tarfile.TarInfo('repo'); top.type = tarfile.DIRTYPE
            tf.addfile(top)
            for name, data, type_, linkname in entries:
                entry = tarfile.TarInfo(name); entry.type = type_; entry.linkname = linkname
                entry.mode = 0o644
                if type_ == tarfile.REGTYPE:
                    entry.size = len(data)
                    tf.addfile(entry, io.BytesIO(data))
                else:
                    tf.addfile(entry)
        return out.getvalue()


class GitTreeTests(Fixtures):
    @unittest.skipUnless(shutil.which('git'), 'git not installed')
    def test_hash_matches_real_git_tree_including_modes_unicode_and_binary(self):
        source = self.make_source()
        (source / 'binary').write_bytes(bytes(range(256)))
        (source / '실행.sh').write_text('#!/bin/sh\nexit 0\n'); (source / '실행.sh').chmod(0o755)
        (source / 'd').mkdir(); (source / 'd/x').write_text('x'); (source / 'd.txt').write_text('sort')
        if hasattr(os, 'symlink'):
            (source / 'link').symlink_to('README.md')
        subprocess.run(['git', 'init', '-q', str(source)], check=True)
        subprocess.run(['git', '-C', str(source), 'config', 'core.autocrlf', 'false'], check=True)
        subprocess.run(['git', '-C', str(source), 'add', '-A'], check=True)
        expected = subprocess.check_output(['git', '-C', str(source), 'write-tree'], text=True).strip()
        self.assertEqual(m.tree_manifest(source)['tree'], expected)

    @unittest.skipUnless(shutil.which('git'), 'git not installed')
    def test_empty_directories_are_not_tracked_by_git(self):
        source = self.make_source()
        (source / 'empty/nested').mkdir(parents=True)
        subprocess.run(['git', 'init', '-q', str(source)], check=True)
        subprocess.run(['git', '-C', str(source), 'add', '-A'], check=True)
        expected = subprocess.check_output(['git', '-C', str(source), 'write-tree'], text=True).strip()
        self.assertEqual(m.tree_manifest(source)['tree'], expected)

    def test_changed_file_rejected(self):
        source = self.make_source(); lock = self.lock(source)
        (source / 'README.md').write_text('changed')
        with self.assertRaises(m.SetupError): m.verify_source(source, lock)

    def test_changed_executable_bit_rejected(self):
        source = self.make_source(); lock = self.lock(source)
        (source / 'README.md').chmod(0o755)
        with self.assertRaises(m.SetupError): m.verify_source(source, lock)

    def test_missing_file_rejected(self):
        source = self.make_source(); lock = self.lock(source)
        (source / 'README.md').unlink()
        with self.assertRaises(m.SetupError): m.verify_source(source, lock)

    def test_extra_file_rejected(self):
        source = self.make_source(); lock = self.lock(source)
        (source / 'hidden_runtime.py').write_text('bad')
        with self.assertRaises(m.SetupError): m.verify_source(source, lock)

    def test_no_source_not_success(self):
        source = self.make_source()
        with self.assertRaises(m.SetupError): m.verify_source(self.root / 'absent', self.lock(source))

    def test_local_import_is_full_and_idempotent(self):
        source = self.make_source(); package = self.package(source)
        with redirect_stdout(io.StringIO()):
            first = m.prepare(package, source=source)
            second = m.prepare(package)
        self.assertEqual(first['tree'], second['tree'])
        self.assertTrue((package / '.local/upstream-manifest.json').exists())
        self.assertTrue((source / 'README.md').exists())

    def test_existing_modified_tree_not_overwritten(self):
        source = self.make_source(); package = self.package(source)
        with redirect_stdout(io.StringIO()): m.prepare(package, source=source)
        target = package / 'upstream/README.md'; target.write_text('user edits')
        with self.assertRaises(m.SetupError): m.prepare(package, source=source)
        self.assertEqual(target.read_text(), 'user edits')

    def test_failed_download_never_creates_upstream(self):
        source = self.make_source(); package = self.package(source)
        with patch.object(m, 'fetch_archive', side_effect=m.SetupError('offline')):
            with self.assertRaises(m.SetupError): m.prepare(package)
        self.assertFalse((package / 'upstream').exists())
        self.assertFalse((package / '.local/upstream-manifest.json').exists())
        self.assertFalse((package / '.local/prepare.lock').exists())

    def test_bad_repo_lock_rejected(self):
        source = self.make_source(); package = self.package(source)
        lock = self.lock(source); lock['repository'] = 'https://example.org/other.git'
        (package / 'upstream.lock.json').write_text(json.dumps(lock))
        with self.assertRaises(m.SetupError): m.lock_spec(package)

    def test_install_lock_prevents_concurrent_mutation(self):
        with m.install_lock(self.root):
            with self.assertRaises(m.SetupError):
                with m.install_lock(self.root): pass
        self.assertFalse((self.root / '.local/prepare.lock').exists())


class ArchiveTests(Fixtures):
    def unpack(self, entries):
        dest = self.root / 'unpacked'; dest.mkdir()
        m.unpack_archive(self.archive(entries), dest)
        return dest

    def test_normal_archive(self):
        dest = self.unpack([('repo/README.md', b'hello', tarfile.REGTYPE, '')])
        self.assertEqual((dest / 'README.md').read_bytes(), b'hello')

    def test_parent_traversal_rejected(self):
        with self.assertRaises(m.SetupError): self.unpack([('repo/../escape', b'x', tarfile.REGTYPE, '')])
        self.assertFalse((self.root / 'escape').exists())

    def test_absolute_path_rejected(self):
        with self.assertRaises(m.SetupError): self.unpack([('/tmp/escape', b'x', tarfile.REGTYPE, '')])

    def test_two_archive_roots_rejected(self):
        with self.assertRaises(m.SetupError): self.unpack([('other/file', b'x', tarfile.REGTYPE, '')])

    def test_duplicate_path_rejected(self):
        with self.assertRaises(m.SetupError): self.unpack([('repo/a', b'x', tarfile.REGTYPE, ''), ('repo/a', b'y', tarfile.REGTYPE, '')])

    def test_link_escape_rejected(self):
        with self.assertRaises(m.SetupError): self.unpack([('repo/a', b'', tarfile.SYMTYPE, '../../outside')])

    def test_write_through_symlink_rejected(self):
        with self.assertRaises(m.SetupError): self.unpack([('repo/link', b'', tarfile.SYMTYPE, 'inside'), ('repo/link/file', b'x', tarfile.REGTYPE, '')])

    def test_hardlink_rejected(self):
        with self.assertRaises(m.SetupError): self.unpack([('repo/a', b'', tarfile.LNKTYPE, '/etc/passwd')])

    def test_size_limit(self):
        with patch.object(m, 'MAX_UNPACKED', 2):
            with self.assertRaises(m.SetupError): self.unpack([('repo/a', b'long', tarfile.REGTYPE, '')])

    def test_archive_import_matches_source(self):
        source = self.make_source(); package = self.package(source)
        archive = self.root / 'archive.tar.gz'
        with tarfile.open(archive, 'w:gz') as tf: tf.add(source, arcname='repo')
        with redirect_stdout(io.StringIO()): report = m.prepare(package, archive=archive)
        self.assertEqual(report['tree'], self.lock(source)['tree'])


class ConfigTests(Fixtures):
    def test_secrets_random_no_known_defaults(self):
        with redirect_stdout(io.StringIO()): values = m.configure(self.root, interactive=False)
        self.assertGreaterEqual(len(values['JWT_SECRET_KEY']), 64)
        self.assertEqual(values['OPENAI_API_KEY'], '')
        self.assertNotIn('changeme', values['ADMIN_PASSWORD'].lower())

    def test_existing_secrets_preserved(self):
        with redirect_stdout(io.StringIO()):
            first = m.configure(self.root, interactive=False)
            second = m.configure(self.root, interactive=False)
        self.assertEqual(first, second)
        self.assertEqual((self.root / '.env').stat().st_mode & 0o777, 0o600)

    def test_key_with_dollar_is_quoted_not_interpolated(self):
        raw = {'KEY': 'abc$literal#value'}
        path = self.root / '.env'; path.write_text(m.encode_env(raw))
        self.assertEqual(m.load_env(path), raw)
        self.assertIn("'abc$literal#value'", path.read_text())

    def test_newline_value_rejected(self):
        with self.assertRaises(m.SetupError): m.encode_env({'KEY': 'x\ny'})

    def test_duplicate_key_rejected(self):
        p = self.root / '.env'; p.write_text('KEY=a\nKEY=b\n')
        with self.assertRaises(m.SetupError): m.load_env(p)

    def test_invalid_port_rejected(self):
        (self.root / '.env').write_text('WEB_PORT=99999\n')
        with self.assertRaises(m.SetupError): m.configure(self.root, interactive=False)

    def test_same_ports_rejected(self):
        (self.root / '.env').write_text('WEB_PORT=8000\nAPI_PORT=8000\n')
        with self.assertRaises(m.SetupError): m.configure(self.root, interactive=False)

    def test_postgres_password_url_safety(self):
        (self.root / '.env').write_text("POSTGRES_PASSWORD='invalid@password123'\n")
        with self.assertRaises(m.SetupError): m.configure(self.root, interactive=False)

    def test_setup_logs_do_not_print_passwords(self):
        out = io.StringIO()
        with redirect_stdout(out): values = m.configure(self.root, interactive=False)
        for key in ('ADMIN_PASSWORD', 'JWT_SECRET_KEY', 'LANGFUSE_SECRET_KEY'):
            if values[key]:self.assertNotIn(values[key], out.getvalue())

    def test_keyless_setup_allows_configuration_screen_but_reports_not_ready(self):
        with redirect_stdout(io.StringIO()):values=m.configure(self.root,interactive=False)
        self.assertEqual(values['CODE_EMBEDDING_PROVIDER'],'none')
        self.assertFalse(m.environment_ready(values))
        self.assertTrue(m.environment_ready(dict(values,CODE_LLM_PROVIDER='anthropic',ANTHROPIC_API_KEY='synthetic')))


class ComposeTests(unittest.TestCase):
    def setUp(self): self.data = build_compose(); self.services = self.data['services']

    def test_generated_compose_in_sync(self):
        self.assertEqual(json.loads((ROOT / 'compose.yaml').read_text()), self.data)

    def test_full_stack_not_legacy_default(self):
        for name in ('rag-api', 'rag-frontend', 'rag-worker', 'rag-beat', 'postgres', 'elasticsearch', 'redis',
                     'langfuse-web', 'langfuse-worker', 'clickhouse', 'langfuse-redis', 'langfuse-minio', 'langfuse-minio-init', 'db-migrate'):
            self.assertIn(name, self.services)
            self.assertNotIn('profiles', self.services[name])
        self.assertEqual(self.services['catalog-legacy']['profiles'], ['legacy'])

    def test_infrastructure_not_exposed(self):
        for name in ('postgres', 'elasticsearch', 'redis', 'clickhouse', 'langfuse-redis', 'langfuse-minio'):
            self.assertNotIn('ports', self.services[name])

    def test_public_ports_loopback_only(self):
        for svc in self.services.values():
            for port in svc.get('ports', []): self.assertTrue(port.startswith('127.0.0.1:'))

    def test_no_external_network_or_fixed_container_names(self):
        self.assertNotIn('networks', self.data)
        for svc in self.services.values(): self.assertNotIn('container_name', svc)

    def test_upload_volume_shared(self):
        for name in ('rag-api', 'rag-worker'):
            self.assertIn('uploads:/app/uploads', self.services[name]['volumes'])

    def test_migration_gates_api_and_worker(self):
        for name in ('rag-api', 'rag-worker'):
            self.assertEqual(self.services[name]['depends_on']['db-migrate']['condition'], 'service_completed_successfully')

    def test_worker_uses_verified_upstream_module(self):
        cmd = self.services['rag-worker']['command']
        self.assertIn('code_agent.worker:celery_app', cmd)
        self.assertIn('from app.worker import celery_app', (ROOT/'extensions/code_agent/worker.py').read_text())
        self.assertIn('--pool=solo', cmd)

    def test_frontend_build_time_api_rewrite(self):
        self.assertEqual(self.services['rag-frontend']['build']['args']['NEXT_PUBLIC_API_URL'], 'http://rag-api:8000')
        self.assertIn('ENV NEXT_PUBLIC_API_URL', (ROOT / 'deploy/frontend.Dockerfile').read_text())

    def test_full_upstream_backend_copied(self):
        self.assertIn('COPY --chown=10001:10001 upstream/backend /app', (ROOT / 'deploy/backend.Dockerfile').read_text())
        self.assertIn('pip install --no-cache-dir --prefix=/install /build/backend', (ROOT / 'deploy/backend.Dockerfile').read_text())

    def test_required_secrets_have_no_weak_fallback(self):
        env = self.services['rag-api']['environment']
        for key in ('JWT_SECRET_KEY',):
            self.assertIn(':?', env[key])
        self.assertEqual(env['CODE_AUTH_MODE'],'${CODE_AUTH_MODE:-local}')
        self.assertEqual(env['ADMIN_PASSWORD'],'${ADMIN_PASSWORD:-}')
        # OpenAI key is optional only because local embedding + Command Code is supported.
        self.assertEqual(env['OPENAI_API_KEY'],'${OPENAI_API_KEY:-}')
        self.assertFalse(m.environment_ready({}))
        self.assertTrue(m.environment_ready({'CODE_LLM_PROVIDER':'commandcode','COMMANDCODE_API_KEY':'test',
            'CODE_EMBEDDING_PROVIDER':'local','LOCAL_EMBEDDING_TOKEN':'test'}))

    def test_nori_installed(self):
        self.assertIn('analysis-nori', (ROOT / 'deploy/elasticsearch.Dockerfile').read_text())

    def test_lf_project_keys_match_app(self):
        env = self.services['langfuse-web']['environment']
        self.assertEqual(env['LANGFUSE_INIT_PROJECT_PUBLIC_KEY'], self.services['rag-api']['environment']['LANGFUSE_PUBLIC_KEY'])
        self.assertEqual(env['LANGFUSE_INIT_PROJECT_SECRET_KEY'], self.services['rag-api']['environment']['LANGFUSE_SECRET_KEY'])
        self.assertEqual(env['CLICKHOUSE_CLUSTER_ENABLED'], 'false')

    def test_all_dependencies_exist(self):
        for svc in self.services.values():
            for dependency in svc.get('depends_on', {}): self.assertIn(dependency, self.services)

    def test_all_volume_references_declared(self):
        for svc in self.services.values():
            for volume in svc.get('volumes', []):
                source = volume.split(':')[0]
                if not source.startswith('./'):
                    self.assertIn(source, self.data['volumes'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
