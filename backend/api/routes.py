"""
REST API routes — full CRUD for all 5 ERD tables.

Endpoints
─────────
  /api/system/command          POST  — start / stop / pause / resume / reset / emergency_stop
  /api/stats                   GET   — live in-memory snapshot
  /api/settings                GET / POST

  /api/sessions                GET   — list sorting sessions
  /api/sessions/{id}           GET   — single session + summary
  /api/sessions/{id}/beans     GET   — beans for a session
  /api/sessions/{id}/logs      GET   — detection logs for a session
  /api/sessions/{id}/actions   GET   — sorting actions for a session
  /api/sessions/{id}/alerts    GET   — alerts for a session

  /api/beans                   GET   — all bean records (filterable)
  /api/beans/{id}              GET   — single bean record
  /api/beans/stats             GET   — aggregate stats

  /api/detection_logs          GET   — all detection logs
  /api/detection_logs/{id}     GET   — single log

  /api/actions                 GET   — all sorting actions
  /api/actions/{id}            GET   — single action

  /api/alerts                  GET   — all alerts (filterable)
  /api/alerts/{id}             GET   — single alert
  /api/alerts/{id}/acknowledge POST  — acknowledge one alert
  /api/alerts/acknowledge_all  POST  — acknowledge all

  /api/analytics/summary       GET   — all-time totals
  /api/analytics/session/{id}  GET   — per-session summary

  /api/calibrate               POST  — set pixels_per_mm
  /api/camera/snapshot         GET   — JPEG frame
"""

from __future__ import annotations
import asyncio as _asyncio
import io
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core import (
    app_state, camera_manager, bean_detector, sorting_controller,
    SystemCommand, SortingSettings, SystemStats,
    AlertLevel, BinType, SystemStatus,
)
from ..core import db_service
from ..core.config import settings as _cfg
from ..core.models import SortCounts

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["system"])


# ── helper ────────────────────────────────────────────────────────────────
def _sid() -> Optional[int]:
    return getattr(app_state, "_db_session_id", None)


# ══════════════════════════════════════════════════════════════════════════
# SYSTEM CONTROL
# ══════════════════════════════════════════════════════════════════════════

@router.post("/system/command")
async def system_command(cmd: SystemCommand, db: Session = Depends(get_db)):
    action = cmd.command.lower()

    # ── START ─────────────────────────────────────────────────────────────
    if action == "start":
        if app_state.status == SystemStatus.RUNNING:
            return {"ok": True, "status": "already running", "session_id": _sid()}

        # Create DB session row FIRST so it always exists even if hardware init fails
        try:
            db_sess = db_service.create_sorting_session(
                db,
                session_name=f"Session {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            )
            app_state._db_session_id = db_sess.session_id
            logger.info(f"DB sorting_session #{db_sess.session_id} opened")
        except Exception as exc:
            logger.error(f"Failed to create DB session: {exc}")
            # Continue without DB session — system still runs
            app_state._db_session_id = None

        # Set status IMMEDIATELY so UI responds instantly
        app_state.status     = SystemStatus.RUNNING
        app_state.start_time = datetime.now()

        # Start hardware asynchronously (non-blocking)
        # Camera initialization happens in background thread
        async def _start_hardware():
            """Background task to initialize hardware without blocking HTTP response"""
            try:
                # Run camera start in thread pool to avoid blocking event loop
                loop = _asyncio.get_event_loop()
                await loop.run_in_executor(None, camera_manager.start)
                logger.info("Camera started (async)")
            except Exception as exc:
                logger.warning(f"Camera start warning: {exc}")

            try:
                # Start conveyor and compressor (fast GPIO operations)
                sorting_controller.start_conveyor()
                sorting_controller.start_compressor()
                logger.info("Conveyor and compressor started (async)")
            except Exception as exc:
                logger.warning(f"Hardware start warning: {exc}")

            # Log startup alert after hardware init completes
            alert = app_state.add_alert(
                AlertLevel.INFO, "System Started",
                "Camera, conveyor, and compressor online.", "system",
            )
            if app_state._db_session_id:
                try:
                    db_local = next(get_db())
                    db_service.create_alert_from_model(db_local, alert, app_state._db_session_id)
                    db_local.close()
                except Exception as exc:
                    logger.error(f"Failed to log start alert: {exc}")

        # Fire and forget - don't wait for hardware init
        _asyncio.create_task(_start_hardware())

        # Return immediately - camera will be ready in ~1-2 seconds
        return {
            "ok": True,
            "status": "running",
            "session_id": app_state._db_session_id,
            "message": "System starting - camera initializing in background",
        }

    # ── STOP ──────────────────────────────────────────────────────────────
    elif action == "stop":
        # Allow stop even if already stopped — idempotent
        if app_state.status == SystemStatus.STOPPED:
            return {"ok": True, "status": "already stopped"}

        sid = _sid()

        # Stop hardware first (always, regardless of DB state)
        try:
            camera_manager.stop()
        except Exception as exc:
            logger.error(f"Camera stop error: {exc}")

        try:
            sorting_controller.stop_conveyor()
            sorting_controller.stop_compressor()
        except Exception as exc:
            logger.error(f"Hardware stop error: {exc}")

        app_state.status = SystemStatus.STOPPED

        # Log stop alert and close DB session — gracefully handle missing session
        alert = app_state.add_alert(
            AlertLevel.INFO, "System Stopped",
            "All subsystems deactivated by operator.", "system",
        )
        if sid:
            try:
                db_service.create_alert_from_model(db, alert, sid)
            except Exception as exc:
                logger.error(f"Failed to log stop alert: {exc}")
            try:
                db_service.close_sorting_session(db, sid)
                logger.info(f"DB sorting_session #{sid} closed")
            except Exception as exc:
                logger.error(f"Failed to close DB session #{sid}: {exc}")
        else:
            logger.info("Stop called with no active DB session — skipping close")

        app_state._db_session_id = None
        return {"ok": True, "status": "stopped"}

    # ── PAUSE ─────────────────────────────────────────────────────────────
    elif action == "pause":
        if app_state.status == SystemStatus.PAUSED:
            return {"ok": True, "status": "paused"}
        if app_state.status != SystemStatus.RUNNING:
            return {"ok": True, "status": app_state.status.value}
        app_state.status = SystemStatus.PAUSED
        # Stop conveyor (no more sorting) but keep camera running for live feed
        try:
            sorting_controller.stop_conveyor()
        except Exception as exc:
            logger.warning(f"Conveyor pause error: {exc}")
        return {"ok": True, "status": "paused"}

    # ── RESUME ────────────────────────────────────────────────────────────
    elif action == "resume":
        if app_state.status == SystemStatus.RUNNING:
            return {"ok": True, "status": "already running"}
        if app_state.status not in (SystemStatus.PAUSED, SystemStatus.STOPPED):
            return {"ok": True, "status": app_state.status.value}
        app_state.status = SystemStatus.RUNNING
        try:
            sorting_controller.start_conveyor()
        except Exception as exc:
            logger.warning(f"Conveyor resume error: {exc}")
        return {"ok": True, "status": "running"}

    # ── RESET ─────────────────────────────────────────────────────────────
    elif action == "reset":
        app_state.sort_counts    = SortCounts()
        app_state.recent_beans   = []
        app_state.alerts         = []
        app_state._bean_counter  = 0
        app_state._alert_counter = 0
        if app_state.status == SystemStatus.RUNNING:
            app_state.start_time = datetime.now()
        return {"ok": True, "status": "reset"}

    # ── EMERGENCY STOP ────────────────────────────────────────────────────
    elif action == "emergency_stop":
        sid = _sid()
        try:
            sorting_controller.emergency_stop()
        except Exception as exc:
            logger.error(f"Emergency stop GPIO error: {exc}")
        try:
            camera_manager.stop()
        except Exception as exc:
            logger.error(f"Emergency stop camera error: {exc}")

        app_state.status = SystemStatus.ERROR

        alert = app_state.add_alert(
            AlertLevel.CRITICAL, "EMERGENCY STOP",
            "All outputs de-energised. Restart required.", "system",
        )
        if sid:
            try:
                db_service.create_alert_from_model(db, alert, sid)
                db_service.close_sorting_session(db, sid, notes="Emergency stop triggered")
            except Exception as exc:
                logger.error(f"Failed to close DB session on E-Stop: {exc}")

        app_state._db_session_id = None
        return {"ok": True, "status": "emergency_stop"}

    raise HTTPException(status_code=400, detail=f"Unknown command: {action}")


# ══════════════════════════════════════════════════════════════════════════
# SETTINGS
# ══════════════════════════════════════════════════════════════════════════

@router.get("/settings")
async def get_settings():
    return app_state.settings.model_dump()


@router.post("/settings")
async def update_settings(settings: SortingSettings, db: Session = Depends(get_db)):
    app_state.settings = settings
    sorting_controller.ejection_ms = settings.ejection_duration_ms
    # Persist to DB so settings survive restarts
    db_service.save_settings(db, settings, bean_detector.ppm)
    return {"ok": True, "settings": settings.model_dump()}


# ══════════════════════════════════════════════════════════════════════════
# LIVE STATS
# ══════════════════════════════════════════════════════════════════════════

@router.get("/stats")
async def get_stats():
    import platform
    try:
        cpu_temp = int(open("/sys/class/thermal/thermal_zone0/temp").read()) / 1000.0 \
            if platform.system() == "Linux" else 0.0
    except Exception:
        cpu_temp = 0.0

    last_bean = app_state.recent_beans[0] if app_state.recent_beans else None
    return SystemStats(
        status=app_state.status,
        uptime_seconds=app_state.uptime_seconds,
        beans_processed=app_state.sort_counts.total,
        beans_per_minute=app_state.beans_per_minute,
        good_yield_pct=app_state.good_yield_pct,
        defect_rate_pct=app_state.defect_rate_pct,
        sort_counts=app_state.sort_counts,
        last_bean=last_bean,
        air_pressure_mpa=app_state._pressure_mpa,
        conveyor_rpm=app_state.settings.conveyor_rpm,
        camera_fps=camera_manager.fps,
        cpu_temp_c=cpu_temp,
        active_alerts=app_state.active_alert_count(),
    ).model_dump()


# ══════════════════════════════════════════════════════════════════════════
# SORTING_SESSIONS
# ══════════════════════════════════════════════════════════════════════════

def _fmt_session(s) -> dict:
    return {
        "session_id":    s.session_id,
        "session_name":  s.session_name,
        "started_at":    s.started_at.isoformat() if s.started_at else None,
        "ended_at":      s.ended_at.isoformat()   if s.ended_at   else None,
        "is_active":     bool(s.is_active),
        "total_beans":   s.total_beans,
        "grade1_count":  s.grade1_count,
        "grade2_count":  s.grade2_count,
        "grade3_count":  s.grade3_count,
        "grade4_count":  s.grade4_count,
        "notes":         s.notes,
    }


@router.get("/sessions")
async def list_sessions(
    limit:       int  = Query(50, ge=1, le=500),
    offset:      int  = Query(0,  ge=0),
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    sessions = db_service.get_sorting_sessions(db, limit=limit, offset=offset, active_only=active_only)
    return [_fmt_session(s) for s in sessions]


@router.get("/sessions/{session_id}")
async def get_session(session_id: int, db: Session = Depends(get_db)):
    s = db_service.get_sorting_session(db, session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    return db_service.get_session_summary(db, session_id)


@router.get("/sessions/{session_id}/beans")
async def session_beans(
    session_id: int,
    grade:  Optional[str] = Query(None),
    limit:  int = Query(100, ge=1, le=1000),
    offset: int = Query(0,   ge=0),
    db: Session = Depends(get_db),
):
    records = db_service.get_bean_records(db, session_id=session_id, grade=grade,
                                          limit=limit, offset=offset)
    return [_fmt_bean(r) for r in records]


@router.get("/sessions/{session_id}/logs")
async def session_logs(
    session_id: int,
    limit:  int = Query(100, ge=1, le=1000),
    offset: int = Query(0,   ge=0),
    db: Session = Depends(get_db),
):
    logs = db_service.get_detection_logs(db, session_id=session_id, limit=limit, offset=offset)
    return [_fmt_log(l) for l in logs]


@router.get("/sessions/{session_id}/actions")
async def session_actions(
    session_id: int,
    limit:  int = Query(100, ge=1, le=1000),
    offset: int = Query(0,   ge=0),
    db: Session = Depends(get_db),
):
    actions = db_service.get_sorting_actions(db, session_id=session_id, limit=limit, offset=offset)
    return [_fmt_action(a) for a in actions]


@router.get("/sessions/{session_id}/alerts")
async def session_alerts(
    session_id: int,
    severity:     Optional[str]  = Query(None),
    acknowledged: Optional[bool] = Query(None),
    limit:  int = Query(100, ge=1, le=1000),
    offset: int = Query(0,   ge=0),
    db: Session = Depends(get_db),
):
    alerts = db_service.get_sorting_alerts(
        db, session_id=session_id, severity=severity,
        acknowledged=acknowledged, limit=limit, offset=offset,
    )
    return [_fmt_alert(a) for a in alerts]


# ══════════════════════════════════════════════════════════════════════════
# BEAN_RECORDS
# ══════════════════════════════════════════════════════════════════════════

def _fmt_bean(r) -> dict:
    return {
        "Brecords_id":  r.Brecords_id,
        "session_id":   r.session_id,
        "detected_at":  r.detected_at.isoformat() if r.detected_at else None,
        "grade":        r.grade,
        "color_value":  r.color_value,
        "size_mm":      float(r.size_mm)     if r.size_mm     else None,
        "confidence":   float(r.confidence)  if r.confidence  else None,
        "bbox_x":       r.bbox_x,
        "bbox_y":       r.bbox_y,
        "bbox_w":       r.bbox_w,
        "bbox_h":       r.bbox_h,
        "image_path":   r.image_path,
    }


@router.get("/beans")
async def list_beans(
    session_id: Optional[int] = Query(None),
    grade:      Optional[str] = Query(None),
    limit:  int = Query(100, ge=1, le=1000),
    offset: int = Query(0,   ge=0),
    db: Session = Depends(get_db),
):
    records = db_service.get_bean_records(db, session_id=session_id,
                                          grade=grade, limit=limit, offset=offset)
    return [_fmt_bean(r) for r in records]


@router.get("/beans/stats")
async def bean_stats(
    session_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    return db_service.get_bean_stats(db, session_id=session_id)


@router.get("/beans/{record_id}")
async def get_bean(record_id: int, db: Session = Depends(get_db)):
    r = db_service.get_bean_record(db, record_id)
    if not r:
        raise HTTPException(404, "Bean record not found")
    return _fmt_bean(r)


# ══════════════════════════════════════════════════════════════════════════
# DETECTION_LOGS
# ══════════════════════════════════════════════════════════════════════════

def _fmt_log(l) -> dict:
    return {
        "Dlogs_id":          l.Dlogs_id,
        "session_id":        l.session_id,
        "logged_at":         l.logged_at.isoformat() if l.logged_at else None,
        "frame_number":      l.frame_number,
        "beans_detected":    l.beans_detected,
        "processing_time_ms":float(l.processing_time_ms) if l.processing_time_ms else None,
        "raw_result":        l.raw_result,
    }


@router.get("/detection_logs")
async def list_detection_logs(
    session_id: Optional[int] = Query(None),
    limit:  int = Query(100, ge=1, le=1000),
    offset: int = Query(0,   ge=0),
    db: Session = Depends(get_db),
):
    logs = db_service.get_detection_logs(db, session_id=session_id,
                                         limit=limit, offset=offset)
    return [_fmt_log(l) for l in logs]


@router.get("/detection_logs/{log_id}")
async def get_detection_log(log_id: int, db: Session = Depends(get_db)):
    l = db_service.get_detection_log(db, log_id)
    if not l:
        raise HTTPException(404, "Detection log not found")
    return _fmt_log(l)


# ══════════════════════════════════════════════════════════════════════════
# SORTING_ACTIONS
# ══════════════════════════════════════════════════════════════════════════

def _fmt_action(a) -> dict:
    return {
        "Sactions_id":      a.Sactions_id,
        "session_id":       a.session_id,
        "bean_record_id":   a.bean_record_id,
        "grade":            a.grade,
        "target_container": a.target_container,
        "actuator_id":      a.actuator_id,
        "actuator_pin":     a.actuator_pin,
        "signal_sent_at":   a.signal_sent_at.isoformat() if a.signal_sent_at else None,
        "success":          bool(a.success),
        "error_message":    a.error_message,
        "latency_ms":       float(a.latency_ms) if a.latency_ms else None,
    }


@router.get("/actions")
async def list_actions(
    session_id:     Optional[int] = Query(None),
    bean_record_id: Optional[int] = Query(None),
    limit:  int = Query(100, ge=1, le=1000),
    offset: int = Query(0,   ge=0),
    db: Session = Depends(get_db),
):
    actions = db_service.get_sorting_actions(
        db, session_id=session_id,
        bean_record_id=bean_record_id,
        limit=limit, offset=offset,
    )
    return [_fmt_action(a) for a in actions]


@router.get("/actions/{action_id}")
async def get_action(action_id: int, db: Session = Depends(get_db)):
    a = db_service.get_sorting_action(db, action_id)
    if not a:
        raise HTTPException(404, "Sorting action not found")
    return _fmt_action(a)


# ══════════════════════════════════════════════════════════════════════════
# SORTING_ALERTS
# ══════════════════════════════════════════════════════════════════════════

def _fmt_alert(a) -> dict:
    return {
        "Salerts_id":        a.Salerts_id,
        "session_id":        a.session_id,
        "bean_record_id":    a.bean_record_id,
        "sorting_action_id": a.sorting_action_id,
        "alert_type":        a.alert_type,
        "severity":          a.severity,
        "title":             a.title,
        "message":           a.message,
        "context_value":     float(a.context_value)   if a.context_value   else None,
        "threshold_value":   float(a.threshold_value) if a.threshold_value else None,
        "extra_data":        a.extra_data,
        "triggered_at":      a.triggered_at.isoformat()    if a.triggered_at    else None,
        "acknowledged":      bool(a.acknowledged),
        "acknowledged_at":   a.acknowledged_at.isoformat() if a.acknowledged_at else None,
    }


@router.get("/alerts")
async def list_alerts(
    session_id:   Optional[int]  = Query(None),
    severity:     Optional[str]  = Query(None),
    acknowledged: Optional[bool] = Query(None),
    limit:  int = Query(100, ge=1, le=1000),
    offset: int = Query(0,   ge=0),
    db: Session = Depends(get_db),
):
    alerts = db_service.get_sorting_alerts(
        db, session_id=session_id, severity=severity,
        acknowledged=acknowledged, limit=limit, offset=offset,
    )
    return [_fmt_alert(a) for a in alerts]


@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: int, db: Session = Depends(get_db)):
    a = db_service.get_sorting_alert(db, alert_id)
    if not a:
        raise HTTPException(404, "Alert not found")
    return _fmt_alert(a)


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: int, db: Session = Depends(get_db)):
    a = db_service.acknowledge_alert(db, alert_id)
    if not a:
        raise HTTPException(404, "Alert not found")
    # sync in-memory list
    for mem in app_state.alerts:
        if mem.id == alert_id:
            mem.resolved = True
    return {"ok": True, "Salerts_id": alert_id}


@router.post("/alerts/acknowledge_all")
async def acknowledge_all_alerts(db: Session = Depends(get_db)):
    count = db_service.acknowledge_all_alerts(db, session_id=_sid())
    for mem in app_state.alerts:
        mem.resolved = True
    return {"ok": True, "acknowledged": count}


# ── legacy aliases so existing React code keeps working ──────────────────
@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert_compat(alert_id: int, db: Session = Depends(get_db)):
    return await acknowledge_alert(alert_id, db)


@router.post("/alerts/resolve_all")
async def resolve_all_compat(db: Session = Depends(get_db)):
    return await acknowledge_all_alerts(db)


# ══════════════════════════════════════════════════════════════════════════
# ANALYTICS
# ══════════════════════════════════════════════════════════════════════════

@router.get("/analytics/summary")
async def all_time_summary(db: Session = Depends(get_db)):
    return db_service.get_all_time_totals(db)


@router.get("/analytics/session/{session_id}")
async def session_summary(session_id: int, db: Session = Depends(get_db)):
    s = db_service.get_session_summary(db, session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    return s


# ══════════════════════════════════════════════════════════════════════════
# CALIBRATION
# ══════════════════════════════════════════════════════════════════════════

@router.post("/calibrate/pixels_per_mm")
async def calibrate(pixels_per_mm: float, db: Session = Depends(get_db)):
    if pixels_per_mm <= 0:
        raise HTTPException(400, "pixels_per_mm must be > 0")
    bean_detector.set_pixels_per_mm(pixels_per_mm)
    # Persist calibration alongside current settings
    db_service.save_settings(db, app_state.settings, pixels_per_mm)
    return {"ok": True, "pixels_per_mm": pixels_per_mm}


# ══════════════════════════════════════════════════════════════════════════
# ADMIN AUTH  — simple token-based login for the Admin Dashboard
# Token is a signed HMAC-SHA256 of "admin:<timestamp>" with the password
# as the key. Valid for 8 hours. No DB storage needed.
# ══════════════════════════════════════════════════════════════════════════

import hashlib, hmac, time as _time

_TOKEN_TTL = 8 * 3600   # 8 hours in seconds

def _make_token(username: str) -> str:
    ts  = int(_time.time())
    msg = f"{username}:{ts}".encode()
    sig = hmac.new(_cfg.ADMIN_PASSWORD.encode(), msg, hashlib.sha256).hexdigest()
    return f"{username}:{ts}:{sig}"

def _verify_token(token: str) -> bool:
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return False
        username, ts_str, sig = parts
        ts = int(ts_str)
        if _time.time() - ts > _TOKEN_TTL:
            return False
        msg      = f"{username}:{ts}".encode()
        expected = hmac.new(_cfg.ADMIN_PASSWORD.encode(), msg, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)
    except Exception:
        return False


from pydantic import BaseModel as _BaseModel

class AdminLoginRequest(_BaseModel):
    username: str
    password: str


@router.post("/admin/login")
async def admin_login(req: AdminLoginRequest):
    if (req.username != _cfg.ADMIN_USERNAME or
            req.password != _cfg.ADMIN_PASSWORD):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = _make_token(req.username)
    return {"ok": True, "token": token, "username": req.username}


@router.get("/admin/verify")
async def admin_verify(token: str = Query(...)):
    if not _verify_token(token):
        raise HTTPException(status_code=401, detail="Token invalid or expired")
    return {"ok": True, "valid": True}




@router.get("/camera/snapshot")
async def camera_snapshot():
    jpeg = camera_manager.get_jpeg(quality=90)
    if jpeg is None:
        raise HTTPException(503, "Camera not available")
    return StreamingResponse(io.BytesIO(jpeg), media_type="image/jpeg")


# ══════════════════════════════════════════════════════════════════════════
# TRAINING  — upload example images, trigger re-train, query status
# ══════════════════════════════════════════════════════════════════════════

import asyncio as _asyncio
from fastapi import UploadFile, File, Form

from ..core.detector import TRAINING_DIR, PROFILE_PATH
from ..core import trainer as _trainer

_TRAIN_LOCK = _asyncio.Lock()   # prevents concurrent train runs


@router.get("/training/status")
async def training_status():
    """
    Returns current detector mode (ML vs HSV-Fallback),
    per-grade sample counts, paths, and training image inventory.
    """
    status   = bean_detector.get_training_status()
    images   = _trainer.list_training_images(TRAINING_DIR)
    img_counts = {k: len(v) for k, v in images.items()}
    return {
        **status,
        "image_counts": img_counts,
    }


@router.get("/training/images")
async def list_training_images():
    """List all training images by grade with filenames and sizes."""
    return _trainer.list_training_images(TRAINING_DIR)


@router.post("/training/upload")
async def upload_training_image(
    grade: str = Form(...),
    file:  UploadFile = File(...),
):
    """
    Upload a single example image for the given grade.

    grade — one of: grade1  grade2  grade3  grade4
    file  — JPEG / PNG / BMP / WebP image

    The image is saved to data/training/<grade>/ and the AI profile is
    immediately updated incrementally (Welford online update) so the
    classifier improves without a full rebuild.  A full rebuild is also
    triggered in the background so the profile stays accurate.
    """
    valid_grades = {"grade1", "grade2", "grade3", "grade4"}
    if grade not in valid_grades:
        raise HTTPException(400, f"Invalid grade '{grade}'. Must be one of {sorted(valid_grades)}")

    ct = (file.content_type or "").lower()
    allowed_ct = {"image/jpeg", "image/jpg", "image/png", "image/bmp", "image/webp"}
    if ct and ct not in allowed_ct:
        raise HTTPException(
            415,
            f"Unsupported file type '{ct}'. Upload a JPEG, PNG, BMP, or WebP image.",
        )

    MAX_SIZE = 20 * 1024 * 1024
    data = await file.read(MAX_SIZE + 1)
    if len(data) > MAX_SIZE:
        raise HTTPException(413, "Image too large — maximum 20 MB per upload")

    # ── Save image ───────────────────────────────────────────────────────
    try:
        saved_path = _trainer.save_uploaded_image(
            image_bytes       = data,
            grade_key         = grade,
            training_dir      = TRAINING_DIR,
            original_filename = file.filename or "",
        )
    except Exception as exc:
        logger.error(f"Failed to save training image: {exc}")
        raise HTTPException(500, f"Could not save image: {exc}")

    # ── Incremental profile update (fast — runs in < 100ms) ──────────────
    # Extract features from the new image and fold them into the existing
    # profile via Welford's online mean/variance algorithm.
    # This avoids a full rebuild (which re-reads every image on disk) but
    # still improves the classifier immediately.
    incremental_samples = 0
    incremental_error   = None
    try:
        feats = _trainer.extract_features_from_image(saved_path, bean_detector.ppm)
        if feats:
            for feat_vec in feats:
                bean_detector.profiles.update(grade, feat_vec)
            bean_detector.profiles.save()
            incremental_samples = len(feats)
            logger.info(
                f"Incremental profile update: +{incremental_samples} samples "
                f"for {grade} from {saved_path.name}"
            )
    except Exception as exc:
        incremental_error = str(exc)
        logger.warning(f"Incremental update failed: {exc} — full retrain will fix this")

    # ── Full rebuild in background (accurate but slower) ─────────────────
    # Schedule as a background task so the HTTP response returns immediately.
    # The full rebuild re-reads ALL training images + labelled snapshots and
    # recomputes the centroid from scratch, correcting any drift from
    # incremental updates.
    retrain_result = None
    try:
        loop   = _asyncio.get_event_loop()
        retrain_result = await loop.run_in_executor(
            None, bean_detector.train_from_examples
        )
        logger.info(f"Full retrain after upload: {retrain_result.get('stats')}")
    except Exception as exc:
        logger.warning(f"Background retrain failed: {exc}")

    return {
        "ok":                 True,
        "grade":              grade,
        "filename":           saved_path.name,
        "size":               len(data),
        "incremental_samples": incremental_samples,
        "incremental_error":  incremental_error,
        "retrain":            retrain_result,
        "mode":               "ML" if bean_detector.profiles.is_trained else "HSV",
    }


@router.post("/training/train")
async def run_training():
    """
    Re-train the grade profiles from all images in data/training/.
    This is CPU-bound and may take a few seconds on a Raspberry Pi —
    it runs in a thread pool so the event loop is not blocked.
    Returns a summary with per-grade sample counts and any errors.
    """
    if _TRAIN_LOCK.locked():
        raise HTTPException(409, "Training already in progress — try again shortly")

    async with _TRAIN_LOCK:
        loop   = _asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, bean_detector.train_from_examples
        )

    if not result.get("ok"):
        raise HTTPException(422, result.get("message", "Training failed"))

    logger.info(f"Training complete: {result}")
    return result


@router.delete("/training/images/{grade}/{filename}")
async def delete_training_image(grade: str, filename: str):
    """Delete a specific training image by grade and filename."""
    valid_grades = {"grade1", "grade2", "grade3", "grade4"}
    if grade not in valid_grades:
        raise HTTPException(400, f"Invalid grade '{grade}'")

    # Sanitise filename — no path traversal
    safe = Path(filename).name
    if safe != filename or "/" in filename or "\\" in filename:
        raise HTTPException(400, "Invalid filename")

    target = TRAINING_DIR / grade / safe
    if not target.exists():
        raise HTTPException(404, "Image not found")

    ok = _trainer.delete_training_image(target)
    if not ok:
        raise HTTPException(500, "Could not delete image")

    return {"ok": True, "deleted": filename, "grade": grade}


@router.delete("/training/images/{grade}")
async def clear_grade_images(grade: str):
    """Delete ALL training images for one grade."""
    valid_grades = {"grade1", "grade2", "grade3", "grade4"}
    if grade not in valid_grades:
        raise HTTPException(400, f"Invalid grade '{grade}'")

    count = _trainer.clear_grade_folder(TRAINING_DIR, grade)
    return {"ok": True, "grade": grade, "deleted": count}


@router.delete("/training/profiles")
async def reset_profiles():
    """
    Delete the saved profiles JSON, reverting the detector to HSV-fallback mode.
    Does NOT delete training images — you can re-train after a reset.
    """
    if PROFILE_PATH.exists():
        PROFILE_PATH.unlink()
    bean_detector.profiles._profiles = {}
    bean_detector.profiles._loaded   = False
    return {"ok": True, "message": "Profiles deleted — detector reverted to HSV-fallback mode"}


# ══════════════════════════════════════════════════════════════════════════
# SNAPSHOTS  — auto-captured idle frames for AI learning
#
# Workflow:
#   1. System auto-saves frames to data/snapshots/unlabelled/ when no
#      beans are detected (every ~5s while conveyor is empty).
#   2. Operator reviews snapshots via GET /api/snapshots
#   3. Operator labels each snapshot via POST /api/snapshots/{filename}/label
#      which moves it to data/snapshots/labelled/<grade>/
#   4. POST /api/training/train picks up labelled snapshots automatically
#      and includes them in the retrain alongside regular training images.
#   5. The AI improves its grading knowledge from real beans it has seen.
# ══════════════════════════════════════════════════════════════════════════

from ..core.detector import SNAPSHOT_DIR


@router.get("/snapshots")
async def list_snapshots():
    """
    List all auto-captured snapshots.
    Returns unlabelled (pending review) and labelled (per grade) counts + filenames.
    """
    return _trainer.list_snapshots(SNAPSHOT_DIR)


@router.post("/snapshots/{filename}/label")
async def label_snapshot(filename: str, grade: str):
    """
    Label a snapshot — moves it from unlabelled/ to labelled/<grade>/.
    It will be included in the next training run automatically.

    Also triggers an immediate incremental profile update so the AI
    improves right away without waiting for a full retrain.

    grade — one of: grade1  grade2  grade3  grade4
    """
    valid_grades = {"grade1", "grade2", "grade3", "grade4"}
    if grade not in valid_grades:
        raise HTTPException(400, f"Invalid grade '{grade}'")

    # Sanitise filename — no path traversal
    safe = Path(filename).name
    if safe != filename or "/" in filename or "\\" in filename:
        raise HTTPException(400, "Invalid filename")

    try:
        dest = _trainer.label_snapshot(SNAPSHOT_DIR, safe, grade)
    except FileNotFoundError:
        raise HTTPException(404, f"Snapshot '{filename}' not found in unlabelled/")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(500, str(exc))

    # ── Incremental update — learn from this snapshot immediately ─────────
    incremental_samples = 0
    try:
        feats = _trainer.extract_features_from_image(dest, bean_detector.ppm)
        if feats:
            for feat_vec in feats:
                bean_detector.profiles.update(grade, feat_vec)
            bean_detector.profiles.save()
            incremental_samples = len(feats)
            logger.info(
                f"Snapshot labelled as {grade}: {safe} "
                f"(+{incremental_samples} samples, profile updated)"
            )
    except Exception as exc:
        logger.warning(f"Incremental update from snapshot failed: {exc}")

    return {
        "ok":                 True,
        "filename":           safe,
        "grade":              grade,
        "dest":               str(dest),
        "incremental_samples": incremental_samples,
        "mode":               "ML" if bean_detector.profiles.is_trained else "HSV",
    }


@router.delete("/snapshots/{filename}")
async def delete_snapshot(filename: str):
    """
    Delete a snapshot from unlabelled/ (reject it — not useful for training).
    """
    safe = Path(filename).name
    if safe != filename or "/" in filename or "\\" in filename:
        raise HTTPException(400, "Invalid filename")

    ok = _trainer.delete_snapshot(SNAPSHOT_DIR, safe)
    if not ok:
        raise HTTPException(404, f"Snapshot '{filename}' not found")
    return {"ok": True, "deleted": safe}


@router.post("/snapshots/label_batch")
async def label_batch(items: list[dict]):
    """
    Label multiple snapshots in one request.

    Body: [ {"filename": "snap_abc.jpg", "grade": "grade1"}, ... ]

    Returns per-item results.
    """
    results = []
    total_samples = 0

    for item in items:
        filename = item.get("filename", "")
        grade    = item.get("grade", "")
        safe     = Path(filename).name

        if grade not in {"grade1", "grade2", "grade3", "grade4"}:
            results.append({"filename": filename, "ok": False, "error": "Invalid grade"})
            continue
        if not safe or safe != filename:
            results.append({"filename": filename, "ok": False, "error": "Invalid filename"})
            continue

        try:
            dest  = _trainer.label_snapshot(SNAPSHOT_DIR, safe, grade)
            feats = _trainer.extract_features_from_image(dest, bean_detector.ppm)
            if feats:
                for feat_vec in feats:
                    bean_detector.profiles.update(grade, feat_vec)
                total_samples += len(feats)
            results.append({"filename": safe, "ok": True, "grade": grade, "samples": len(feats) if feats else 0})
        except Exception as exc:
            results.append({"filename": safe, "ok": False, "error": str(exc)})

    # Save once after all incremental updates
    if total_samples > 0:
        bean_detector.profiles.save()
        logger.info(f"Batch label: {total_samples} total samples added across {len(items)} snapshots")

    return {
        "ok":             True,
        "results":        results,
        "total_samples":  total_samples,
        "mode":           "ML" if bean_detector.profiles.is_trained else "HSV",
    }


@router.post("/snapshots/retrain")
async def retrain_from_snapshots():
    """
    Trigger a full retrain that includes all labelled snapshots.
    Use this after labelling a batch of snapshots to do a clean rebuild.
    """
    if _TRAIN_LOCK.locked():
        raise HTTPException(409, "Training already in progress")

    async with _TRAIN_LOCK:
        loop   = _asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, bean_detector.train_from_examples
        )

    if not result.get("ok"):
        raise HTTPException(422, result.get("message", "Training failed"))

    logger.info(f"Retrain from snapshots complete: {result}")
    return result
