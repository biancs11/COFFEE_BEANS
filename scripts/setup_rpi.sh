#!/usr/bin/env bash
# ============================================================
# Coffee Bean Sorting System — Raspberry Pi Setup Script
# Tested on Raspberry Pi OS Bookworm (64-bit), RPi 4/5.
#
# Run ONCE after cloning / copying the project:
#   chmod +x scripts/setup_rpi.sh
#   ./scripts/setup_rpi.sh
# ============================================================
set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠ $*${NC}"; }
die()  { echo -e "${RED}✗ $*${NC}" >&2; exit 1; }

# ── Resolve project root ──────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
SERVICE_SRC="$SCRIPT_DIR/coffee-sorter.service"
SERVICE_DST="/etc/systemd/system/coffee-sorter.service"

echo ""
echo "============================================================"
echo "  Coffee Bean Sorting System — Raspberry Pi Setup"
echo "  Project : $PROJECT_DIR"
echo "  User    : $USER"
echo "============================================================"
echo ""

# ── Sanity checks ─────────────────────────────────────────────
[[ "$(uname -m)" == aarch64 ]] || warn "Not running on arm64 — GPIO will be in simulation mode"
[[ $EUID -ne 0 ]] || die "Do NOT run this script as root. Run as your normal user (sudo will be used where needed)."
command -v python3 >/dev/null || die "python3 not found"

# ── 1. System packages ────────────────────────────────────────
echo "── Step 1: Installing system packages …"
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    python3-pip python3-venv python3-dev \
    python3-picamera2 libcamera-apps \
    libopencv-dev python3-opencv \
    nodejs npm \
    git curl \
    i2c-tools      # smbus2 / pressure sensor
ok "System packages installed"

# ── 2. Enable camera + I2C ────────────────────────────────────
echo "── Step 2: Enabling camera and I2C …"
sudo raspi-config nonint do_camera 0 2>/dev/null && ok "Camera enabled" || warn "raspi-config camera enable skipped"
sudo raspi-config nonint do_i2c 0    2>/dev/null && ok "I2C enabled"    || warn "raspi-config I2C enable skipped"

# ── 3. Python virtual environment ─────────────────────────────
echo "── Step 3: Creating Python virtual environment …"
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --quiet --upgrade pip wheel
ok "Virtual environment ready at $VENV_DIR"

# ── 4. Python dependencies ────────────────────────────────────
echo "── Step 4: Installing Python dependencies …"
pip install --quiet -r "$PROJECT_DIR/backend/requirements.txt"

# Raspberry Pi-specific packages (may not be on PyPI for all archs)
pip install --quiet RPi.GPIO==0.7.1 || warn "RPi.GPIO install failed — GPIO will be in simulation mode"
pip install --quiet smbus2==0.4.3   || warn "smbus2 install failed — pressure sensor will use simulation"
ok "Python dependencies installed"

# ── 5. Environment file ───────────────────────────────────────
echo "── Step 5: Setting up .env …"
if [[ ! -f "$PROJECT_DIR/.env" ]]; then
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    # Patch CORS origins to use actual Pi IP
    PI_IP=$(hostname -I | awk '{print $1}')
    sed -i "s|CORS_ORIGINS=.*|CORS_ORIGINS=http://localhost:8000,http://${PI_IP}:8000|" "$PROJECT_DIR/.env"
    ok ".env created from .env.example (IP: $PI_IP)"
else
    ok ".env already exists — skipping"
fi

# ── 6. Create data and logs directories ──────────────────────
echo "── Step 6: Creating data and logs directories …"
mkdir -p "$PROJECT_DIR/data" "$PROJECT_DIR/logs"
ok "data/ and logs/ directories ready"

# ── 7. Run database migrations ────────────────────────────────
echo "── Step 7: Running Alembic migrations …"
cd "$PROJECT_DIR"
"$VENV_DIR/bin/alembic" upgrade head
ok "Database migrations applied"

# ── 8. Build React frontend ───────────────────────────────────
echo "── Step 8: Building React frontend …"
cd "$PROJECT_DIR/frontend"

# Use Node ≥18; install via nvm if system node is too old
NODE_VER=$(node --version 2>/dev/null | sed 's/v//' | cut -d. -f1)
if [[ "${NODE_VER:-0}" -lt 18 ]]; then
    warn "Node $(node --version 2>/dev/null || echo 'not found') is too old — installing Node 20 via nvm …"
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
    export NVM_DIR="$HOME/.nvm"
    # shellcheck source=/dev/null
    source "$NVM_DIR/nvm.sh"
    nvm install 20
    nvm use 20
fi

npm ci --silent
npm run build
ok "React frontend built → frontend/dist/"
cd "$PROJECT_DIR"

# ── 9. Install systemd service ────────────────────────────────
echo "── Step 9: Installing systemd service …"

# Patch service file with correct user and project path
TMP_SERVICE=$(mktemp)
sed "s|/home/pi/projects/coffee_bean_sorting|$PROJECT_DIR|g; s|User=pi|User=$USER|g; s|Group=pi|Group=$USER|g" \
    "$SERVICE_SRC" > "$TMP_SERVICE"

sudo cp "$TMP_SERVICE" "$SERVICE_DST"
rm "$TMP_SERVICE"

sudo systemctl daemon-reload
sudo systemctl enable coffee-sorter
sudo systemctl restart coffee-sorter

# Give it a moment, then check
sleep 3
if sudo systemctl is-active --quiet coffee-sorter; then
    ok "coffee-sorter service is running"
else
    warn "Service may not have started yet. Check: sudo journalctl -u coffee-sorter -n 50"
fi

# ── 10. Optional: kiosk autostart ────────────────────────────
echo "── Step 10: Setting up Chromium kiosk autostart …"
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
cat > "$AUTOSTART_DIR/coffee-sorter-kiosk.desktop" << EOF
[Desktop Entry]
Type=Application
Name=Coffee Bean Sorter
Exec=bash -c 'sleep 5 && chromium-browser --kiosk --noerrdialogs --disable-infobars --disable-session-crashed-bubble --no-first-run --window-size=1024,600 http://localhost:8000/launcher'
EOF
ok "Chromium kiosk autostart configured → opens /launcher on Waveshare 7\" 1024x600"

# ── Summary ───────────────────────────────────────────────────
PI_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "============================================================"
echo -e "${GREEN}  Setup complete!${NC}"
echo "============================================================"
echo ""
echo "  Dashboard : http://localhost:8000"
echo "  Network   : http://${PI_IP}:8000"
echo "  API docs  : Disabled in production (set APP_ENV=development to enable)"
echo "  Health    : http://localhost:8000/health"
echo "  Logs      : $PROJECT_DIR/logs/"
echo "  DB        : $PROJECT_DIR/data/coffee_sorter.db"
echo ""
echo "  Service commands:"
echo "    sudo systemctl status  coffee-sorter"
echo "    sudo systemctl restart coffee-sorter"
echo "    sudo journalctl -u coffee-sorter -f"
echo ""
echo "  Run migrations manually:"
echo "    source venv/bin/activate"
echo "    alembic upgrade head"
echo ""
echo -e "${YELLOW}  Reboot recommended to apply camera/I2C changes:${NC}"
echo "    sudo reboot"
echo ""
