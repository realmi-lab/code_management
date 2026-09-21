"""Consistent SQLite backup plus immutable original uploads. No destructive restore."""
from __future__ import annotations
import argparse
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime,timezone

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    source=args.data_dir.resolve();dest=args.output.resolve()
    if source==dest or source in dest.parents:raise SystemExit('Backups must be outside the data directory.')
    if not (source/'catalog.sqlite3').exists():raise SystemExit('Database not found.')
    dest.mkdir(parents=True,exist_ok=False);dest.chmod(0o700)
    with sqlite3.connect(source/'catalog.sqlite3') as src,sqlite3.connect(dest/'catalog.sqlite3') as out:
        src.backup(out)
    (dest/'catalog.sqlite3').chmod(0o600)
    if (source/'uploads').exists():shutil.copytree(source/'uploads',dest/'uploads')
    (dest/'BACKUP.txt').write_text('UTC '+datetime.now(timezone.utc).isoformat()+'\nDatabase copied with SQLite backup API. Source app was not stopped.\nStop the app before restoring files manually.\n')
    print('Backup created:',dest)

if __name__=='__main__':main()
