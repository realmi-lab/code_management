"""Isolated native launcher, bootstrap, and backup smoke tests. Creates only temporary data."""
from pathlib import Path
import json, os, shutil, sqlite3, socket, subprocess, sys, tempfile, time, urllib.request, urllib.error
root=Path(__file__).resolve().parent.parent
checks=[]
with tempfile.TemporaryDirectory(prefix='cm-launch-smoke-') as tmp:
 t=Path(tmp); mini=t/'config-test';(mini/'scripts').mkdir(parents=True)
 shutil.copy(root/'scripts/bootstrap.py',mini/'scripts/bootstrap.py');shutil.copy(root/'.env.example',mini/'.env.example')
 subprocess.run([sys.executable,str(mini/'scripts/bootstrap.py')],check=True,capture_output=True)
 before=(mini/'.env').read_bytes();assert b'ACCESS_TOKEN=\n' not in before
 assert ((mini/'.env').stat().st_mode & 0o777)==0o600
 subprocess.run([sys.executable,str(mini/'scripts/bootstrap.py')],check=True,capture_output=True)
 assert (mini/'.env').read_bytes()==before
 checks.append('bootstrap: nonempty private key, mode600, repeat does not overwrite')
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 env={**os.environ,'ACCESS_TOKEN':'temporary-smoke-token','DATA_DIR':str(t/'data'),'PORT':str(port),'BIND_HOST':'127.0.0.1','AI_ENABLED':'false','CATALOG_AUTHORITY':'excel'}
 p=subprocess.Popen([sys.executable,str(root/'run.py')],cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 try:
  base=f'http://127.0.0.1:{port}'
  for _ in range(80):
   try:
    response=urllib.request.urlopen(base+'/api/health',timeout=0.3);assert json.load(response)['ok'];break
   except (OSError,urllib.error.URLError):time.sleep(.1)
  else:raise RuntimeError('native launcher did not become healthy')
  checks.append('native run.py: actual loopback HTTP health response')
  try:urllib.request.urlopen(base+'/api/meta?namespace=live',timeout=2);raise AssertionError('missing auth accepted')
  except urllib.error.HTTPError as e:assert e.code==401
  req=urllib.request.Request(base+'/api/meta?namespace=live',headers={'Authorization':'Bearer temporary-smoke-token'})
  meta=json.load(urllib.request.urlopen(req,timeout=2));assert isinstance(meta,dict)
  checks.append('native HTTP: missing access key rejected, valid key accepted')
  html=urllib.request.urlopen(base+'/',timeout=2).read();assert b'Code Library' in html
  checks.append('native HTTP: static index served')
  subprocess.run([sys.executable,str(root/'scripts/backup.py'),'--data-dir',str(t/'data'),'--output',str(t/'backup')],check=True,capture_output=True)
  with sqlite3.connect(t/'backup/catalog.sqlite3') as db:assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
  assert ((t/'backup/catalog.sqlite3').stat().st_mode & 0o777)==0o600
  checks.append('backup: live SQLite snapshot integrity and private file permissions')
 finally:
  p.terminate()
  try:p.wait(timeout=5)
  except subprocess.TimeoutExpired:p.kill();p.wait()
 # Missing credentials fail closed without starting a listener.
 env2={**os.environ,'ACCESS_TOKEN':''}
 r=subprocess.run([sys.executable,str(root/'scripts/container_start.py')],env=env2,capture_output=True)
 assert r.returncode!=0 and b'ACCESS_TOKEN required' in r.stderr
 checks.append('container entrypoint refuses missing credentials (Python-only check, not Docker run)')
report={'passed':len(checks),'checks':checks,'docker_engine':shutil.which('docker'),'external_model_calls':False}
(root/'docs/launcher-smoke-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
