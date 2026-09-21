"""Container startup must fail closed when access protection is missing."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if not os.getenv('ACCESS_TOKEN'):
    raise SystemExit('ACCESS_TOKEN required. Run python3 scripts/bootstrap.py before docker compose up.')
import uvicorn
uvicorn.run('catalog.main:app',host='0.0.0.0',port=8000,access_log=False)
