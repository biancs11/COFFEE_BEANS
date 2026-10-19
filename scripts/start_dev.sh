#!/usr/bin/env bash
# Development — hot-reload backend + Vite dev server in parallel
set -euo pipefail
cd "$(dirname "$0")/.."
source venv/bin/activate

export APP_ENV=development

# Backend
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Frontend
cd frontend && npm run dev &
FRONTEND_PID=$!

echo ""
echo "  Backend  → http://localhost:8000  (PID $BACKEND_PID)"
echo "  Frontend → http://localhost:5173  (PID $FRONTEND_PID)"
echo "  API docs → http://localhost:8000/docs"
echo ""
echo "  Press Ctrl+C to stop both"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Stopped.'; exit" INT TERM
wait
