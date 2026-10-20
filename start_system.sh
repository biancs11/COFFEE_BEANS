#!/bin/bash
# ============================================================
#  Coffee Bean Sorting System — Linux / Raspberry Pi Launcher
#  Usage: bash start_system.sh
#         or make it executable: chmod +x start_system.sh
#                                 ./start_system.sh
# ============================================================

# ── Resolve project root (wherever this script lives) ───────
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1

echo ""
echo " ============================================"
echo "   Coffee Bean Sorting System - Starting"
echo " ============================================"
echo ""

# ── Build frontend if dist folder is missing ────────────────
if [ ! -f "frontend/dist/index.html" ]; then
    echo " [!] Frontend not built yet. Building now, please wait..."
    cd frontend
    npm install
    npm run build
    cd ..
    echo " Frontend built successfully."
    echo ""
fi

# ── Ensure logs directory exists ────────────────────────────
mkdir -p "$PROJECT_DIR/logs"

# ── Kill anything already on port 8000 ──────────────────────
PID=$(lsof -ti tcp:8000 2>/dev/null)
if [ -n "$PID" ]; then
    echo " [~] Killing existing process on port 8000 (PID: $PID)..."
    kill -9 "$PID" 2>/dev/null
    sleep 1
fi

# ── Start backend server ─────────────────────────────────────
echo " [1/3] Launching backend server on port 8000..."
nohup python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 \
    > "$PROJECT_DIR/logs/server.log" 2>&1 &
SERVER_PID=$!
echo " Server PID: $SERVER_PID"

# ── Wait up to 15 seconds for server to be ready ────────────
echo " [2/3] Waiting for server to be ready..."
tries=0
ready=false

while [ $tries -lt 15 ]; do
    sleep 1
    tries=$((tries + 1))
    if curl -s --max-time 1 http://localhost:8000/health > /dev/null 2>&1; then
        ready=true
        break
    fi
done

if [ "$ready" = false ]; then
    echo ""
    echo " [!] Server did not start in time."
    echo "     Check logs/server.log for errors."
    echo ""
    exit 1
fi

echo " [3/3] Server is ready!"
echo ""
echo " ============================================"
echo "   System running at: http://localhost:8000"
echo " ============================================"
echo ""

# ── Open browser ─────────────────────────────────────────────
URL="http://localhost:8000"

if command -v xdg-open > /dev/null 2>&1; then
    xdg-open "$URL" &          # Linux desktop (GNOME, KDE, XFCE, etc.)
elif command -v chromium-browser > /dev/null 2>&1; then
    chromium-browser "$URL" &  # Raspberry Pi OS default
elif command -v chromium > /dev/null 2>&1; then
    chromium "$URL" &
else
    echo " [i] Open your browser and go to: $URL"
fi

echo " Server is running. Press Ctrl+C to stop."
echo " Logs: $PROJECT_DIR/logs/server.log"
echo ""

# ── Keep script alive so Ctrl+C stops the server ────────────
trap "echo ''; echo ' Stopping server...'; kill $SERVER_PID 2>/dev/null; exit 0" INT TERM
wait $SERVER_PID
