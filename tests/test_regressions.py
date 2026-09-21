import sys,tempfile,os,json,subprocess
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from urllib.parse import urlparse,unquote
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import manage,smoke,render_compose

class Regressions(TestCase):
    def test_B02_validated_environment_passed_to_child(self):
        with tempfile.TemporaryDirectory() as t:
            r=Path(t);(r/'.env').write_text("COMPOSE_PROJECT_NAME='intended-project'\n")
            with patch.dict(os.environ,{'COMPOSE_PROJECT_NAME':'wrong-project','COMPOSE_PROFILES':'legacy','DOCKER_HOST':'test-context'}):
                out=manage.run([sys.executable,'-c','import os,json; print(json.dumps({k:os.environ.get(k) for k in ["COMPOSE_PROJECT_NAME","COMPOSE_PROFILES","DOCKER_HOST"]}))'],cwd=r,capture=True)
            result=json.loads(out.stdout);self.assertEqual(result['COMPOSE_PROJECT_NAME'],'intended-project');self.assertIsNone(result['COMPOSE_PROFILES']);self.assertEqual(result['DOCKER_HOST'],'test-context')
    def test_B03_weak_password_rejected_without_overwrite(self):
        with tempfile.TemporaryDirectory() as t:
            r=Path(t);p=r/'.env';p.write_text('CODE_AUTH_MODE=jwt\nADMIN_PASSWORD=123321\n');old=p.read_bytes()
            with self.assertRaises(manage.SetupError):manage.configure(r,False)
            self.assertEqual(p.read_bytes(),old)
    def test_B04_reserved_redis_password_is_encoded(self):
        with tempfile.TemporaryDirectory() as t:
            r=Path(t);(r/'.env').write_text("REDIS_PASSWORD='DummyOnly#123456789'\n")
            values=manage.configure(r,False);parsed=urlparse('redis://:'+values['REDIS_PASSWORD_URLENCODED']+'@redis:6379/0')
            self.assertEqual(parsed.hostname,'redis');self.assertEqual(unquote(parsed.password),values['REDIS_PASSWORD'])
            self.assertIn('REDIS_PASSWORD_URLENCODED',render_compose.build_compose()['services']['rag-api']['environment']['REDIS_URL'])
    def test_B05_failed_latest_attempt_replaces_success(self):
        with tempfile.TemporaryDirectory() as t:
            r=Path(t);(r/'.env').write_text('ADMIN_USERNAME=admin\nADMIN_PASSWORD=not-used\n')
            responses=[{},{},{'access_token':'synthetic'},{'items':[]},{'id':1},{'user':{'id':1}},{'items':[]}]
            with patch.object(smoke,'request_json',side_effect=responses):smoke.exercise(r)
            before=json.loads((r/'.local/http-smoke.json').read_text())
            with patch.object(smoke,'request_json',side_effect=manage.SetupError('network failed')):
                with self.assertRaises(manage.SetupError):smoke.exercise(r)
            after=json.loads((r/'.local/http-smoke.json').read_text());self.assertFalse(after['passed']);self.assertNotEqual(before['run_id'],after['run_id']);self.assertEqual(after['state'],'failed')
    def test_B06_equal_numeric_ports_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            r=Path(t);(r/'.env').write_text('WEB_PORT=08000\nAPI_PORT=8000\n')
            with self.assertRaises(manage.SetupError):manage.configure(r,False)
    def test_wrapper_preserves_original_login_and_worker(self):
        source=(ROOT/'extensions/code_agent/entrypoint.py').read_text();self.assertIn('from app.main import app',source);self.assertIn('from app.dependencies import get_current_user',source)
        self.assertIn('from app.worker import celery_app',(ROOT/'extensions/code_agent/worker.py').read_text())
    def test_integrated_migration_and_source_build(self):
        c=render_compose.build_compose();self.assertIn('code_agent.migrate',c['services']['db-migrate']['command'][-1])
        self.assertIn('extensions/frontend',(ROOT/'deploy/frontend.Dockerfile').read_text());self.assertIn('patch_backend.py',(ROOT/'deploy/backend.Dockerfile').read_text())
