#!/bin/bash
# ============================================================
#  Coffee Bean Sorting System — Linux / Raspberry Pi Launcher
#  User: coffeebean@coffeebean
#  Usage:
#    chmod +x start_system.sh
#    ./start_system.sh
# ============================================================

# ── Resolve project root (wherever this script lives) ───────
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1

echo ""
echo " ============================================"
echo "   Coffee Bean Sorting System - Starting"
echo " ============================================"
echo ""

# ── Check for .env file ──────────────────────────────────────
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo " [!] No .env file found. Creating from .env.example..."
    if [ -f "$PROJECT_DIR/.env.example" ]; then
        cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
        echo " .env created from .env.example. Edit it if needed."
        echo ""
    else
        echo " [!] ERROR: .env.example not found either. Cannot continue."
        exit 1
    fi
fi

# ── Check for Python 3 ──────────────────────────────────────
if ! command -v python3 > /dev/null 2>&1; then
    echo " [!] ERROR: python3 not found. Install it with:"
    echo "     sudo apt install -y python3 python3-pip python3-venv"
    exit 1
fi

# ── Activate virtual environment if it exists ───────────────
if [ -f "$PROJECT_DIR/venv/bin/activate" ]; then
    echo " [~] Activating virtual environment..."
    source "$PROJECT_DIR/venv/bin/activate"
    PYTHON_CMD="python"
else
    echo " [~] No venv found — using system python3."
    echo "     Tip: create one with: python3 -m venv venv"
    echo "          then: source venv/bin/activate"
    echo "          then: pip install -r backend/requirements.txt"
    echo ""
    PYTHON_CMD="python3"
fi

# ── Check uvicorn is available ───────────────────────────────
if ! $PYTHON_CMD -m uvicorn --version > /dev/null 2>&1; then
    echo " [!] ERROR: uvicorn not found. Install dependencies with:"
    echo "     pip install -r backend/requirements.txt"
    exit 1
fi

# ── Build frontend if dist folder is missing ────────────────
if [ ! -f "$PROJECT_DIR/frontend/dist/index.html" ]; then
    echo " [!] Frontend not built yet. Checking for npm..."

    if ! command -v npm > /dev/null 2>&1; then
        echo " [!] ERROR: npm not found. Install it with:"
        echo "     sudo apt install -y nodejs npm"
        exit 1
    fi

    echo " [~] Building frontend, please wait..."
    cd "$PROJECT_DIR/frontend"
    npm install
    npm run build
    cd "$PROJECT_DIR"

    if [ ! -f "$PROJECT_DIR/frontend/dist/index.html" ]; then
        echo " [!] ERROR: Frontend build failed. Check npm output above."
        exit 1
    fi

    echo " Frontend built successfully."
    echo ""
fi

# ── Ensure logs directory exists ────────────────────────────
mkdir -p "$PROJECT_DIR/logs"

# ── Kill anything already on port 8000 ──────────────────────
if command -v lsof > /dev/null 2>&1; then
    PID=$(lsof -ti tcp:8000 2>/dev/null)
elif command -v fuser > /dev/null 2>&1; then
    PID=$(fuser 8000/tcp 2>/dev/null)
else
    PID=""
fi

if [ -n "$PID" ]; then
    echo " [~] Killing existing process on port 8000 (PID: $PID)..."
    kill -9 $PID 2>/dev/null
    sleep 1
fi

# ── Open launcher page immediately (before server starts) ────
# The launcher polls /health every 2s and shows a START button
# on the Pi screen. It will update automatically when server is up.
LAUNCHER_URL="http://localhost:8000/launcher"

_open_browser() {
    local url="$1"
    if command -v chromium-browser > /dev/null 2>&1; then
        DISPLAY=:0 chromium-browser \
            --noerrdialogs \
            --disable-infobars \
            --disable-session-crashed-bubble \
            --no-first-run \
            --start-fullscreen \
            --window-size=1024,600 \
            "$url" &
    elif command -v chromium > /dev/null 2>&1; then
        DISPLAY=:0 chromium \
            --noerrdialogs \
            --disable-infobars \
            --no-first-run \
            --start-fullscreen \
            --window-size=1024,600 \
            "$url" &
    elif command -v xdg-open > /dev/null 2>&1; then
        DISPLAY=:0 xdg-open "$url" &
    else
        echo " [i] Open your browser and go to: $url"
    fi
}

echo " [1/4] Starting backend server on port 8000..."
nohup $PYTHON_CMD -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 \
    > "$PROJECT_DIR/logs/server.log" 2>&1 &
SERVER_PID=$!
echo " Server PID: $SERVER_PID"

# ── Wait up to 25 seconds for server to be ready ────────────
echo " [2/4] Waiting for server to be ready..."
tries=0
ready=false
browser_opened=false

while [ $tries -lt 25 ]; do
    sleep 1
    tries=$((tries + 1))

    # Check if server is up
    if command -v curl > /dev/null 2>&1; then
        if curl -s --max-time 1 http://localhost:8000/health > /dev/null 2>&1; then
            ready=true
        fi
    else
        if $PYTHON_CMD -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=1)" > /dev/null 2>&1; then
            ready=true
        fi
    fi

    # Open browser as soon as server responds (launcher page serves immediately)
    if [ "$ready" = true ] && [ "$browser_opened" = false ]; then
        echo " [3/4] Server ready — opening launcher on screen..."
        _open_browser "$LAUNCHER_URL"
        browser_opened=true
        break
    fi
done

if [ "$ready" = false ]; then
    echo ""
    echo " [!] Server did not start in time."
    echo "     Check logs/server.log for errors:"
    echo "     cat $PROJECT_DIR/logs/server.log"
    echo ""
    # Still try to open browser in case server starts slowly
    _open_browser "$LAUNCHER_URL"
    # Don't exit — keep server running, browser will poll
fi

echo " [4/4] System started!"
echo ""
echo " ============================================"
echo "   Launcher  : http://localhost:8000/launcher"
echo "   Dashboard : http://localhost:8000"
echo "   Health    : http://localhost:8000/health"
echo " ============================================"
echo ""
echo " Press Ctrl+C to stop the server."
echo " Logs: $PROJECT_DIR/logs/server.log"
echo ""

# ── Keep script alive so Ctrl+C stops the server ────────────
trap "echo ''; echo ' Stopping server...'; kill $SERVER_PID 2>/dev/null; exit 0" INT TERM
wait $SERVER_PID
