#!/usr/bin/env python3
"""Create private local config without overwriting an existing configuration."""
from __future__ import annotations
import argparse
import secrets
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--show-key',action='store_true',help='Display YOUR generated local access key in this terminal.')
    args=parser.parse_args()
    target=ROOT/'.env'
    if target.exists():
        print('기존 .env를 유지합니다. 설정을 덮어쓰지 않았습니다.')
    else:
        text=(ROOT/'.env.example').read_text(encoding='utf-8')
        text=text.replace('ACCESS_TOKEN=\n','ACCESS_TOKEN='+secrets.token_urlsafe(32)+'\n',1)
        # O_EXCL prevents an accidental concurrent overwrite.
        with target.open('x',encoding='utf-8') as f:f.write(text)
        target.chmod(0o600)
        print('.env를 만들었습니다. 개인 접속 키를 포함하므로 공유하지 마세요.')
    if args.show_key:
        for line in target.read_text(encoding='utf-8').splitlines():
            if line.startswith('ACCESS_TOKEN='):
                value=line.split('=',1)[1].strip()
                if not value:raise SystemExit('ACCESS_TOKEN이 비어 있습니다. 실행 전에 설정해주세요.')
                print('브라우저 접속 키:',value)
                break
    print('다음 실행: docker compose up -d --build')
    print('접속: http://localhost:8766 (PORT를 변경하지 않은 경우)')

if __name__=='__main__':main()
