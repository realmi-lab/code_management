import unittest,tempfile,subprocess,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class SearchPersistencePatch(unittest.TestCase):
 def test_pinned_search_contract(self):
  with tempfile.TemporaryDirectory() as tmp:
   for rel in ['src/app/search/page.tsx','src/components/search/search-input.tsx']:
    p=Path(tmp)/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/'upstream/frontend'/rel,p)
   script=ROOT/'deploy/patch_search_persistence.mjs'
   r=subprocess.run(['node',str(script)],cwd=tmp,capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   self.assertIn('mutateAsync(params).then(setSavedResult)',(Path(tmp)/'src/app/search/page.tsx').read_text())
   self.assertNotEqual(subprocess.run(['node',str(script)],cwd=tmp,capture_output=True).returncode,0)
