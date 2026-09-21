"""Build-copy patch and formatting behavior; no model inference."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
FILES = ['src/app/evaluation/runs/page.tsx','src/app/evaluation/compare/page.tsx']

@unittest.skipUnless(shutil.which('node') and (ROOT/'upstream/frontend/src').exists(), 'Requires upstream and Node')
class EvaluationFrontendPatch(unittest.TestCase):
    def test_unavailable_is_not_zero_and_contract_is_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for file in FILES:
                dest = root/file
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT/'upstream/frontend'/file, dest)
            command = ['node', str(ROOT/'deploy/patch_evaluation_frontend.mjs')]
            compare = root/FILES[-1]
            original = compare.read_text()
            compare.write_text(original.replace('const diff = comparison.diff[metric] ?? 0;', 'const diff = 0;'))
            before = (root/FILES[0]).read_text()
            failed = subprocess.run(command, cwd=root, capture_output=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual((root/FILES[0]).read_text(), before)
            compare.write_text(original)
            passed = subprocess.run(command, cwd=root, capture_output=True)
            self.assertEqual(passed.returncode, 0, passed.stderr)
            runs = (root/FILES[0]).read_text()
            helper = 'function measured' + runs.split('function measured',1)[1].split('function RunDetailDialog',1)[0]
            helper = helper.replace('value: unknown','value').replace(': value is number','').replace('): string',')')
            script = helper + 'console.log(JSON.stringify([undefined,null,NaN,Infinity,"0",0,0.42].map(v=>metricText(v,true))));'
            result = subprocess.run(['node','-e',script],text=True,capture_output=True,check=True)
            self.assertEqual(json.loads(result.stdout),['미측정']*5+['0.0%','42.0%'])
            self.assertNotIn('?? 0', runs.split('function RunDetailDialog')[1].split('export default')[0])
            self.assertIn('metricText(run.metrics?.answer_relevancy)', runs)
            self.assertIn('metricText(r.answer_relevancy)', runs)
            self.assertIn('measured(val1) && measured(val2) ? comparison.diff[metric] : undefined',compare.read_text())
            self.assertNotIn('?? 0',compare.read_text())
            self.assertEqual(len(json.loads((root/'catalog-evaluation-patches.json').read_text())),2)
if __name__ == '__main__': unittest.main()
