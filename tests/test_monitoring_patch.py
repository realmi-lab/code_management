import unittest,tempfile,subprocess,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class MonitoringPatch(unittest.TestCase):
 def test_backend_contract(self):
  with tempfile.TemporaryDirectory() as tmp:
   target=Path(tmp)/'app/api/monitoring.py';target.parent.mkdir(parents=True)
   shutil.copyfile(ROOT/'upstream/backend/app/api/monitoring.py',target)
   script=ROOT/'deploy/patch_monitoring.py'
   result=subprocess.run([sys.executable,str(script),tmp],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   self.assertIn('Depends(require_admin)',target.read_text())
   self.assertNotEqual(subprocess.run([sys.executable,str(script),tmp],capture_output=True).returncode,0)
 def test_frontend_contract(self):
  with tempfile.TemporaryDirectory() as tmp:
   for name in ['src/app/monitoring/page.tsx','src/app/monitoring/traces/page.tsx','src/types/index.ts','src/app/monitoring/metrics/page.tsx']:
    target=Path(tmp)/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/'upstream/frontend'/name,target)
   script=ROOT/'deploy/patch_monitoring_frontend.mjs'
   result=subprocess.run(['node',str(script)],cwd=tmp,capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   self.assertNotEqual(subprocess.run(['node',str(script)],cwd=tmp,capture_output=True).returncode,0)
