import unittest,tempfile,subprocess,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class CatalogSurfacesPatch(unittest.TestCase):
 def test_fixed_contract_and_duplicate_rejection(self):
  with tempfile.TemporaryDirectory() as tmp:
   dest=Path(tmp)
   for rel in ['src/lib/api.ts','src/app/documents/page.tsx','src/app/search/page.tsx']:
    target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/'upstream/frontend'/rel,target)
   script=ROOT/'deploy/patch_catalog_surfaces.mjs'
   result=subprocess.run(['node',str(script)],cwd=dest,capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   self.assertIn('DocumentList', (dest/'src/app/documents/page.tsx').read_text())
   self.assertIn('SearchResults', (dest/'src/app/search/page.tsx').read_text())
   self.assertIn('<CatalogPanel search />',(dest/'src/app/search/page.tsx').read_text())
   self.assertNotEqual(subprocess.run(['node',str(script)],cwd=dest,capture_output=True).returncode,0)
