"""Container startup must fail closed when access protection is missing."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import uvicorn
uvicorn.run('catalog.main:app',host='0.0.0.0',port=8000,access_log=False)
