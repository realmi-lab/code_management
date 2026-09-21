"""Pinned selection patches and executable event handler regressions; no browser."""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [f'src/components/settings/{name}-form.tsx' for name in ('search', 'chunking')]
COMMAND = ['node', str(ROOT/'deploy/patch_settings_selection_frontend.mjs')]


@unittest.skipUnless(shutil.which('node') and (ROOT/'upstream/frontend/src').exists(), 'Requires pinned source and Node')
class SettingsSelectionFrontendPatch(unittest.TestCase):
    def prepare(self, root):
        for file in FILES:
            dest = root/file
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT/'upstream/frontend'/file, dest)

    def test_selection_handlers_ignore_empty_events_and_accept_valid_choices(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.prepare(root)
            result = subprocess.run(COMMAND, cwd=root, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            bodies = []
            for file in FILES:
                source = (root/file).read_text()
                bodies.extend(re.findall(r'onValueChange=\{\(v\) => \{ (.*?) \}\}', source))
            self.assertEqual(len(bodies), 3)
            code = 'const assert = require("node:assert/strict");\n'
            for body, field, saved, changed in zip(bodies, ['mode', 'keyword_engine', 'strategy'], ['vector', 'elasticsearch', 'auto'], ['cascading', 'bm25', 'semantic']):
                body = body.replace(' as SearchFormData["mode"]', '')
                code += '{ let value=' + json.dumps(saved) + '; const form={setValue:(key,v)=>{assert.equal(key,' + json.dumps(field) + ');value=v;}}; const onChange=(v)=>{' + body + '}; onChange(""); assert.equal(value,' + json.dumps(saved) + '); onChange(' + json.dumps(changed) + '); assert.equal(value,' + json.dumps(changed) + '); }\n'
            executed = subprocess.run(['node', '-e', code], capture_output=True)
            self.assertEqual(executed.returncode, 0, executed.stderr)
            chunking = (root/FILES[1]).read_text()
            backend = (ROOT/'upstream/backend/app/services/document/processor.py').read_text()
            implemented = re.findall(r'"(\w+)": lambda:', backend)
            for strategy in implemented + ['sentence', 'token']:
                self.assertEqual(chunking.count(f'<SelectItem value="{strategy}">'), 1)

    def test_contract_failure_does_not_partially_write_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.prepare(root)
            chunking = root/FILES[1]
            chunking.write_text(chunking.read_text().replace('value="recursive"', 'value="changed"'))
            before = {file: (root/file).read_bytes() for file in FILES}
            result = subprocess.run(COMMAND, cwd=root, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'contract changed', result.stderr)
            for file in FILES:
                self.assertEqual((root/file).read_bytes(), before[file])
            self.assertFalse((root/'catalog-settings-selection-patches.json').exists())


if __name__ == '__main__':
    unittest.main()
