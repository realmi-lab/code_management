"""Pinned notice patch contracts; no browser or provider integration claimed."""
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [f'src/components/settings/{name}-form.tsx' for name in ('search', 'hyde', 'chunking')]
COMMAND = ['node', str(ROOT/'deploy/patch_settings_availability_frontend.mjs')]


@unittest.skipUnless(shutil.which('node') and (ROOT/'upstream/frontend/src').exists(), 'Requires pinned source and Node')
class SettingsAvailabilityFrontendPatch(unittest.TestCase):
    def prepare(self, root):
        for file in FILES:
            dest = root/file
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT/'upstream/frontend'/file, dest)

    def test_notices_preserve_controls_and_record_exact_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.prepare(root)
            originals = {file: (root/file).read_text() for file in FILES}
            result = subprocess.run(COMMAND, cwd=root, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((root/'catalog-settings-availability-patches.json').read_text())
            for entry in manifest:
                before = originals[entry['path']]
                after = (root/entry['path']).read_text()
                self.assertEqual(entry['before_sha256'], hashlib.sha256(before.encode()).hexdigest())
                self.assertEqual(entry['after_sha256'], hashlib.sha256(after.encode()).hexdigest())
                self.assertIn('settings?.embedding_provider === "none"', after)
                self.assertIn('role="status"', after)
                self.assertIn('재인덱싱', after)
                # Remove just the notice: all original controls and handlers must survive exactly.
                start = after.index('\n          {settings?.embedding_provider === "none"')
                end = after.index('\n          )}', start) + len('\n          )}')
                self.assertEqual(after[:start] + after[end:], before)
            repeated = subprocess.run(COMMAND, cwd=root, capture_output=True)
            self.assertNotEqual(repeated.returncode, 0)

    def test_late_contract_failure_leaves_all_files_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.prepare(root)
            late = root/FILES[-1]
            late.write_text(late.read_text().replace('className="space-y-6"', 'className="changed"'))
            originals = {file: (root/file).read_bytes() for file in FILES}
            result = subprocess.run(COMMAND, cwd=root, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'contract changed', result.stderr)
            for file in FILES:
                self.assertEqual((root/file).read_bytes(), originals[file])
            self.assertFalse((root/'catalog-settings-availability-patches.json').exists())


if __name__ == '__main__':
    unittest.main()
