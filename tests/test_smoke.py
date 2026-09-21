from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import smoke
import manage

class SmokeTests(unittest.TestCase):
    def test_no_settings_means_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(manage.SetupError): smoke.exercise(Path(temp))

    def test_default_smoke_never_calls_search_or_writes_documents(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / '.env').write_text("ADMIN_USERNAME=admin\nADMIN_PASSWORD=password\n")
            with patch.object(smoke, 'request_json', side_effect=[{'ready': True}, {'ready': True}, {'access_token':'temporary-token'}, {'items':[], 'total':0}, {'id':1}, {'user':{'id':1}}, {'items':[], 'total':0}]) as req:
                report = smoke.exercise(root)
            self.assertTrue(report['passed'])
            self.assertFalse(report['rag_request_sent'])
            self.assertFalse(report['quality_verified'])
            paths = [c.args[1] for c in req.call_args_list]
            self.assertNotIn('/api/search/debug', paths)
            self.assertFalse(any('/upload' in p for p in paths))
            output = (root / '.local/http-smoke.json').read_text()
            self.assertNotIn('temporary-token', output)
            self.assertNotIn('password', output)

    def test_explicit_query_sent_with_real_endpoint_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / '.env').write_text('ADMIN_USERNAME=admin\nADMIN_PASSWORD=password\n')
            responses = [{}, {}, {'access_token':'token'}, {'items':[], 'total':0}, {'id':1}, {'user':{'id':1}}, {'items':[], 'total':0}, {'answer':'answer', 'results':[], 'pipeline_trace':[{'name':'generation'}]}]
            with patch.object(smoke, 'request_json', side_effect=responses) as req, redirect_stdout(io.StringIO()):
                report = smoke.exercise(root, query='test question')
            self.assertTrue(report['rag_request_sent'])
            self.assertEqual(req.call_args_list[-1].args[1], '/api/search/debug')
            self.assertEqual(req.call_args_list[-1].kwargs['body'], {'query':'test question','generate_answer':True})
            self.assertFalse(report['quality_verified'])

    def test_bad_login_does_not_continue(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / '.env').write_text('ADMIN_USERNAME=admin\nADMIN_PASSWORD=password\n')
            with patch.object(smoke, 'request_json', side_effect=[{}, {}, {}]) as req:
                with self.assertRaises(manage.SetupError): smoke.exercise(root)
            self.assertEqual(req.call_count, 3)
            self.assertTrue((root / '.local/http-smoke.json').exists())
            self.assertFalse(json.loads((root/'.local/http-smoke.json').read_text())['passed'])

if __name__ == '__main__': unittest.main()
