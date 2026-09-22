"""Pinned frontend patch checks; these do not claim browser or live backend coverage."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ['src/lib/auth-context.tsx', 'src/components/layout/auth-layout.tsx',
         'src/components/layout/header.tsx', 'src/app/settings/profile/page.tsx',
         'src/app/login/page.tsx']

@unittest.skipUnless(shutil.which('node') and (ROOT/'upstream/frontend/src').exists(), 'Requires verified upstream and Node')
class LocalAccessFrontendPatch(unittest.TestCase):
    def test_pinned_patch_and_atomic_contract_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for file in FILES:
                dest = root/file
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT/'upstream/frontend'/file, dest)
            command = ['node', str(ROOT/'deploy/patch_local_access_frontend.mjs')]
            # A late contract mismatch must leave every earlier file untouched.
            login = root/FILES[-1]
            login.write_text(login.read_text().replace('const { login }', 'const { login: signIn }'))
            original_auth = (root/FILES[0]).read_text()
            failed = subprocess.run(command, cwd=root, capture_output=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual((root/FILES[0]).read_text(), original_auth)
            shutil.copy(ROOT/'upstream/frontend'/FILES[-1], login)
            passed = subprocess.run(command, cwd=root, capture_output=True)
            self.assertEqual(passed.returncode, 0, passed.stderr)
            auth = (root/FILES[0]).read_text()
            self.assertIn('setUser(await fetchMe(null))', auth)
            self.assertIn('if (mode?.mode !== "jwt")', auth)
            self.assertIn('headers: token ? { Authorization:', auth)
            self.assertIn('router.replace(localMode ? "/codes" : "/")', (root/FILES[1]).read_text())
            self.assertIn('user && !localMode', (root/FILES[2]).read_text())
            self.assertIn('{!localMode && <div', (root/FILES[2]).read_text())

if __name__ == '__main__':
    unittest.main()
