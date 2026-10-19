"""
Gunicorn configuration — production ASGI server for Coffee Bean Sorting System.

GPIO is NOT fork-safe, so workers=1 is mandatory.
UvicornWorker provides async support (WebSocket, lifespan, async routes).

Start:
    gunicorn backend.main:app -c gunicorn.conf.py
"""

import multiprocessing
import os
from pathlib import Path

# ── Binding ────────────────────────────────────────────────────────────────
host    = os.getenv("APP_HOST", "0.0.0.0")
port    = os.getenv("APP_PORT", "8000")
bind    = f"{host}:{port}"

#── Worker ─────────────────────────────────────────────────────────────────
# MUST be 1 — GPIO (RPi.GPIO) is not fork-safe.
workers         = 1
worker_class    = "uvicorn.workers.UvicornWorker"
worker_tmp_dir  = "/dev/shm"   # RAM-backed temp dir on Linux

# ── Timeouts ───────────────────────────────────────────────────────────────
timeout          = 120    # seconds — allow long MJPEG streams
keepalive        = 5      # keep-alive connection seconds
graceful_timeout = 30     # seconds to finish in-flight requests on SIGTERM

# ── Logging ────────────────────────────────────────────────────────────────
_log_dir = Path(os.getenv("LOG_DIR", "logs"))
_log_dir.mkdir(parents=True, exist_ok=True)

loglevel        = os.getenv("APP_LOG_LEVEL", "info")
accesslog       = str(_log_dir / "access.log")
errorlog        = str(_log_dir / "error.log")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" %(D)sµs'

# ── Process management ─────────────────────────────────────────────────────
pidfile     = str(_log_dir / "gunicorn.pid")
daemon      = False    # systemd manages the process — no double-fork
preload_app = False    # cannot preload — GPIO must init in worker, not master

# ── Hooks ──────────────────────────────────────────────────────────────────

def on_starting(server):
    server.log.info("=" * 55)
    server.log.info("  Coffee Bean Sorting System  —  Gunicorn starting")
    server.log.info(f"  Bind : {bind}")
    server.log.info(f"  PID  : {os.getpid()}")
    server.log.info("=" * 55)

def worker_init(worker):
    worker.log.info(f"Worker {worker.pid} initialised")

def on_exit(server):
    server.log.info("Gunicorn shutdown complete")
