"""
Coffee Bean Sorting System — FastAPI Production Entry Point

Production (single worker — required for GPIO):
    gunicorn backend.main:app -c gunicorn.conf.py

Development (hot reload):
    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations
import asyncio
import logging
import logging.handlers
import os
import platform
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from backend.core.config import settings, PROJECT_ROOT
from backend.api.routes import router
from backend.api.websocket import websocket_endpoint, detection_broadcast_loop
from backend.core import camera_manager, sorting_controller, app_state
from backend.core.database import init_db, SessionLocal
from backend.core import db_service


# ══════════════════════════════════════════════════════════════════════════
# LOGGING  — stdout + rotating file
# ══════════════════════════════════════════════════════════════════════════

def _setup_logging() -> None:
    log_fmt  = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"
    level    = logging.DEBUG if not settings.is_production else logging.INFO

    # Root logger
    root = logging.getLogger()
    root.setLevel(level)

    # Console handler (always)
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(logging.Formatter(log_fmt, date_fmt))
    root.addHandler(console)

    # Rotating file handler — logs/coffee_sorter.log
    log_file = settings.log_dir_path / "coffee_sorter.log"
    file_h   = logging.handlers.RotatingFileHandler(
        filename    = log_file,
        maxBytes    = settings.LOG_MAX_BYTES,
        backupCount = settings.LOG_BACKUP_COUNT,
        encoding    = "utf-8",
    )
    file_h.setLevel(level)
    file_h.setFormatter(logging.Formatter(log_fmt, date_fmt))
    root.addHandler(file_h)

    # Suppress noisy third-party loggers in production
    if settings.is_production:
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


_setup_logging()
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# LIFESPAN — startup / shutdown
# ══════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(application: FastAPI):
    # ── STARTUP ────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("  Coffee Bean Sorting System  —  starting up")
    logger.info(f"  Environment : {settings.APP_ENV}")
    logger.info(f"  DB path     : {settings.db_url}")
    logger.info(f"  Log dir     : {settings.log_dir_path}")
    logger.info("=" * 60)

    # 1. Initialise database — creates tables if they don't exist
    logger.info("Initialising database …")
    init_db()
    logger.info("Database ready ✓")

    # 2. Load persisted settings into AppState
    db = SessionLocal()
    try:
        saved = db_service.load_settings(db)          # ← BUG #1 FIXED
        if saved:
            from backend.core import bean_detector
            app_state.settings.conveyor_rpm         = saved.conveyor_rpm
            app_state.settings.sensitivity          = saved.sensitivity
            app_state.settings.min_bean_area_px     = saved.min_bean_area_px
            app_state.settings.max_bean_area_px     = saved.max_bean_area_px
            app_state.settings.ejection_duration_ms = saved.ejection_duration_ms
            app_state.settings.air_pressure_mpa     = saved.air_pressure_mpa
            app_state.settings.auto_sort            = saved.auto_sort
            bean_detector.set_pixels_per_mm(saved.pixels_per_mm)
            logger.info(
                f"Settings loaded: rpm={saved.conveyor_rpm} "
                f"sensitivity={saved.sensitivity} ppm={saved.pixels_per_mm}"
            )
        else:
            logger.info("No saved settings — using defaults from .env")
    except Exception as exc:
        logger.error(f"Failed to load settings from DB: {exc}")
    finally:
        db.close()

    # 3. Start detection + broadcast background task
    detection_task = asyncio.create_task(detection_broadcast_loop())
    logger.info("Detection broadcast loop started ✓")
    logger.info("System ready — waiting for START command")

    # ── Hand control to FastAPI ────────────────────────────────────────
    yield

    # ── SHUTDOWN ───────────────────────────────────────────────────────
    logger.info("Shutting down …")

    detection_task.cancel()
    try:
        await asyncio.wait_for(detection_task, timeout=5.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass

    camera_manager.stop()
    sorting_controller.cleanup()

    # Close active DB session
    sid = getattr(app_state, "_db_session_id", None)
    if sid is not None:
        db = SessionLocal()
        try:
            db_service.close_sorting_session(db, sid)    # ← BUG #2 FIXED
            logger.info(f"DB sorting session #{sid} closed on shutdown")
        except Exception as exc:
            logger.error(f"Failed to close DB session on shutdown: {exc}")
        finally:
            db.close()

    logger.info("Shutdown complete")


# ══════════════════════════════════════════════════════════════════════════
# APP
# ══════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title       = "Coffee Bean Sorting System",
    version     = "2.0.0",
    description = (
        "Real-time coffee bean grading — Raspberry Pi Camera + OpenCV + SQLite. "
        "Premium / Grade 1 / Grade 2 / Grade 3 / Defective with pneumatic ejection."
    ),
    docs_url    = None if settings.is_production else "/docs",
    redoc_url   = None if settings.is_production else "/redoc",
    openapi_url = None if settings.is_production else "/openapi.json",
    lifespan    = lifespan,
)


# ══════════════════════════════════════════════════════════════════════════
# MIDDLEWARE
# ══════════════════════════════════════════════════════════════════════════

# ── CORS (secure — no wildcard with credentials) ──────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = False,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ── Optional API-key gate ─────────────────────────────────────────────────
class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    When API_KEY is set in .env, every request must include:
      Header:  X-API-Key: <key>
    WebSocket and static file routes are excluded.
    """
    EXEMPT_PREFIXES = ("/ws", "/stream", "/assets", "/health", "/camera-test")

    async def dispatch(self, request: Request, call_next):
        if not settings.API_KEY:
            return await call_next(request)
        path = request.url.path
        if any(path.startswith(p) for p in self.EXEMPT_PREFIXES):
            return await call_next(request)
        key = request.headers.get("X-API-Key", "")
        if key != settings.API_KEY:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )
        return await call_next(request)

app.add_middleware(APIKeyMiddleware)

# ── Request timing (dev + info logging) ──────────────────────────────────
class RequestTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        t0  = time.perf_counter()
        res = await call_next(request)
        ms  = (time.perf_counter() - t0) * 1000
        if ms > 500:   # only log slow requests
            logger.warning(f"Slow request: {request.method} {request.url.path} {ms:.0f}ms")
        return res

if not settings.is_production:
    app.add_middleware(RequestTimingMiddleware)


# ══════════════════════════════════════════════════════════════════════════
# GLOBAL ERROR HANDLER
# ══════════════════════════════════════════════════════════════════════════

@app.exception_handler(Exception)
async def _unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(f"Unhandled error on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "path":   request.url.path,
        },
    )

@app.exception_handler(HTTPException)
async def _http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


# ══════════════════════════════════════════════════════════════════════════
# HEALTH CHECK  (lightweight — no DB query, used by systemd / load balancer)
# ══════════════════════════════════════════════════════════════════════════

_start_time = time.time()

@app.get("/camera-test", tags=["camera"], include_in_schema=False)
async def camera_test_page():
    """Serve the standalone camera test page — open on any device on the LAN."""
    test_page = PROJECT_ROOT / "camera_test.html"
    if not test_page.exists():
        raise HTTPException(status_code=404, detail="camera_test.html not found in project root")
    return FileResponse(str(test_page), media_type="text/html")


@app.get("/launcher", tags=["launcher"], include_in_schema=False)
async def launcher_page():
    """
    Fullscreen launcher page — displayed on the Raspberry Pi screen.
    Shows a big START button and live system status (polls /health).
    Open in kiosk mode: chromium-browser --app=http://localhost:8000/launcher
    """
    launcher = PROJECT_ROOT / "launcher.html"
    if not launcher.exists():
        raise HTTPException(status_code=404, detail="launcher.html not found in project root")
    return FileResponse(str(launcher), media_type="text/html")


@app.get("/health", tags=["health"])
async def health_check():
    """
    Returns 200 when the application is alive.
    Returns 503 when in ERROR state (emergency stop triggered).
    """
    uptime = int(time.time() - _start_time)

    # Optional: read CPU temperature on RPi
    cpu_temp = 0.0
    try:
        if platform.system() == "Linux":
            cpu_temp = int(
                open("/sys/class/thermal/thermal_zone0/temp").read()
            ) / 1000.0
    except Exception:
        pass

    # Optional: psutil memory/CPU
    mem_mb = 0.0
    cpu_pct = 0.0
    try:
        import psutil
        mem_mb  = psutil.Process().memory_info().rss / 1_048_576
        cpu_pct = psutil.cpu_percent(interval=None)
    except ImportError:
        pass

    payload: dict[str, Any] = {
        "status":       "ok" if app_state.status.value != "error" else "degraded",
        "system_state": app_state.status.value,
        "uptime_s":     uptime,
        "camera_fps":   camera_manager.fps,
        "cpu_temp_c":   cpu_temp,
        "mem_mb":       round(mem_mb, 1),
        "cpu_pct":      cpu_pct,
        "db_session":   getattr(app_state, "_db_session_id", None),
        "version":      "2.0.0",
    }

    status_code = 503 if payload["status"] == "degraded" else 200
    return JSONResponse(content=payload, status_code=status_code)


@app.get("/health/db", tags=["health"])
async def health_db():
    """Performs a lightweight DB round-trip to confirm connectivity."""
    db = SessionLocal()
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception as exc:
        logger.error(f"DB health check failed: {exc}")
        return JSONResponse(
            status_code=503,
            content={"status": "error", "detail": str(exc)},
        )
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════
# REST ROUTES
# ══════════════════════════════════════════════════════════════════════════

app.include_router(router)


# ══════════════════════════════════════════════════════════════════════════
# WEBSOCKET
# ══════════════════════════════════════════════════════════════════════════

@app.websocket("/ws")
async def ws_route(websocket: WebSocket):
    await websocket_endpoint(websocket)


# ══════════════════════════════════════════════════════════════════════════
# MJPEG STREAM  — BUG #4 FIXED: async generator, no blocking sleep
# ══════════════════════════════════════════════════════════════════════════

async def _mjpeg_gen():
    """Async MJPEG generator — never blocks the event loop."""
    while True:
        jpeg = camera_manager.get_jpeg(quality=78)
        if jpeg:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + jpeg +
                b"\r\n"
            )
        await asyncio.sleep(0.033)   # ~30 fps ceiling


@app.get("/stream", tags=["camera"])
async def mjpeg_stream():
    """Raw MJPEG stream — usable in <img src="/stream"> or VLC."""
    return StreamingResponse(
        _mjpeg_gen(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ══════════════════════════════════════════════════════════════════════════
# SERVE REACT PRODUCTION BUILD
# ══════════════════════════════════════════════════════════════════════════

_frontend_dist = PROJECT_ROOT / "frontend" / "dist"

if _frontend_dist.is_dir():
    _assets_dir = _frontend_dist / "assets"
    if _assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        # Never intercept API / WS / health / standalone HTML routes
        if full_path.startswith(("api/", "ws", "health", "stream", "launcher", "camera-test")):
            raise HTTPException(status_code=404)
        index = _frontend_dist / "index.html"
        if not index.exists():
            raise HTTPException(status_code=404, detail="Frontend build not found")
        return FileResponse(str(index))
