import subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class ProxyTimeoutPatch(unittest.TestCase):
    def test_pinned_config_and_changed_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'next.config.ts'
            target.write_text((ROOT/'upstream/frontend/next.config.ts').read_text())
            script=str(ROOT/'deploy/patch_proxy_timeout_frontend.mjs')
            result=subprocess.run(['node',script],cwd=directory,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('proxyTimeout: 300_000',target.read_text())
            self.assertIn('source: "/api/:path*"',target.read_text())
            self.assertNotEqual(subprocess.run(['node',script],cwd=directory,capture_output=True).returncode,0)
