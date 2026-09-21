#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
python3 scripts/manage.py start
