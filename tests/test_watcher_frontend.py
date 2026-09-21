"""Pinned build-copy contracts and actual request serialization, no provider calls."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ['src/lib/api.ts', 'src/lib/queries.ts', 'src/components/settings/watcher-form.tsx']

@unittest.skipUnless(shutil.which('node') and (ROOT/'upstream/frontend/src').exists(), 'Requires upstream and Node')
class WatcherFrontendPatch(unittest.TestCase):
    def test_patch_and_serialized_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for file in FILES:
                dest = root/file
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT/'upstream/frontend'/file, dest)
            command = ['node', str(ROOT/'deploy/patch_watcher_frontend.mjs')]
            form = root/FILES[-1]
            original = form.read_text()
            form.write_text(original.replace('await startMutation.mutateAsync();', 'await changed();'))
            before = (root/FILES[0]).read_text()
            failed = subprocess.run(command, cwd=root, capture_output=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual((root/FILES[0]).read_text(), before)
            form.write_text(original)
            passed = subprocess.run(command, cwd=root, capture_output=True)
            self.assertEqual(passed.returncode, 0, passed.stderr)
            api = (root/FILES[0]).read_text()
            function = api.split('    start: (directories: string[], usePolling = false) => {')[1].split('\n    },')[0]
            function = function.replace('fetchJSON<WatcherActionResponse>', 'fetchJSON')
            script = 'const fetchJSON=(url, options)=>({url, options});const start=(directories,usePolling=false)=>{' + function + '};console.log(JSON.stringify(start(["/watch/a,b", "/watch/한 글"],true)));'
            result = subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True)
            from urllib.parse import urlparse, parse_qs
            payload = json.loads(result.stdout)
            query = parse_qs(urlparse(payload['url']).query)
            self.assertEqual(query, {'directories':['/watch/a,b','/watch/한 글'], 'use_polling':['true']})
            self.assertEqual(payload['options'], {'method':'POST'})
            self.assertIn('api.watcher.start(options.directories, options.usePolling)', (root/FILES[1]).read_text())
            self.assertIn('startMutation.mutateAsync({ directories, usePolling:', form.read_text())
            self.assertNotIn('toast.info("감시 설정은', form.read_text())
            self.assertNotIn('수동 스캔이 시작되었습니다', form.read_text())
            self.assertIn('result.scanned_files', form.read_text())
            self.assertIn('이 작업은 인덱싱을 실행하지 않습니다', form.read_text())
            self.assertEqual(len(json.loads((root/'catalog-watcher-patches.json').read_text())), 3)

if __name__ == '__main__': unittest.main()
