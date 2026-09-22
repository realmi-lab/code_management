"""Run synthetic Apple judge checks in an isolated API container, without writing credentials."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
from manage import load_env

values = {k: v for k, v in load_env(ROOT / '.env').items() if k.startswith(('CODE_', 'COMMANDCODE_', 'LANGFUSE_'))}
values['CODE_LLM_JUDGE_PROVIDER'] = 'apple'
values.pop('CODE_AI_SETTINGS_FILE', None)
cmd = ['docker', 'run', '--rm', '--add-host', 'host.docker.internal:host-gateway']
for key in values:
    cmd += ['-e', key]
cmd += ['-v', str(ROOT / 'extensions') + ':/ext:ro',
        '-v', str(Path(__file__).with_name('judge_bench_real.py')) + ':/bench.py:ro',
        '-e', 'PYTHONPATH=/ext:/app', 'code-management-full-api:75661c6',
        'python', '/bench.py', sys.argv[1] if len(sys.argv) > 1 else 'apple-v2-final', '3']
sys.exit(subprocess.run(cmd, env={**os.environ, **values}).returncode)
