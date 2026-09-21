#!/usr/bin/env python3
"""Native Python launcher. Reads .env without executing it as a shell script."""
from __future__ import annotations
import os
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def load_env(path):
    if not path.exists():return
    for line in path.read_text(encoding='utf-8').splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        if '=' not in line:raise ValueError('Invalid .env line (expected KEY=value)')
        key,value=line.split('=',1);key=key.strip();value=value.strip()
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*',key):raise ValueError('Invalid .env key')
        if len(value)>=2 and value[0]==value[-1] and value[0] in ('"',"'"):value=value[1:-1]
        os.environ.setdefault(key,value)

if __name__=='__main__':
    os.chdir(ROOT);load_env(ROOT/'.env')
    if not os.getenv('ACCESS_TOKEN'):
        raise SystemExit('접속 키가 없습니다. 먼저 python3 scripts/bootstrap.py --show-key 를 실행해주세요.')
    import uvicorn
    host=os.getenv('BIND_HOST','127.0.0.1');port=int(os.getenv('PORT','8766'))
    print(f'Code Library: http://localhost:{port} · 데이터 폴더: '+os.getenv('DATA_DIR',str(ROOT/'data')))
    uvicorn.run('catalog.main:app',host=host,port=port,access_log=False)
