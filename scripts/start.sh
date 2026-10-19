#!/usr/bin/env bash
# Production start — uses gunicorn with UvicornWorker
set -euo pipefail
cd "$(dirname "$0")/.."
source venv/bin/activate
exec gunicorn backend.main:app -c gunicorn.conf.py
