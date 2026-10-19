"""
Database service layer — all CRUD operations for the 5 ERD tables.

Tables:
  sorting_sessions   — one row per operator session
  detection_logs     — one row per camera frame processed
  bean_records       — one row per detected bean
  sorting_actions    — one row per ejection/routing action
  sorting_alerts     — one row per raised alert
"""

from __future__ import annotations
import json
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from .database import SessionLocal
from .db_models import (
    SortingSession,
    DetectionLog,
    BeanRecord,
    SortingAction,
    SortingAlert,
)
from .models import BeanResult, Alert, AlertLevel


# ══════════════════════════════════════════════════════════════════════════
# SORTING_SESSIONS
# ══════════════════════════════════════════════════════════════════════════

def create_sorting_session(db: Session, session_name: str = "") -> SortingSession:
    """Open a new sorting session row. Returns the persisted object."""
    name = session_name or f"Session {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
    sess = SortingSession(
        session_name = name,
        started_at   = datetime.utcnow(),
        is_active    = 1,
        total_beans  = 0,
        grade1_count = 0,
        grade2_count = 0,
        grade3_count = 0,
        grade4_count = 0,
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def close_sorting_session(
    db: Session,
    session_id: int,
    notes: str = "",
) -> Optional[SortingSession]:
    """
    Close an active session.
    Recomputes grade counts from bean_records rows.
    """
    sess = db.get(SortingSession, session_id)
    if not sess:
        return None

    sess.ended_at  = datetime.utcnow()
    sess.is_active = 0
    if notes:
        sess.notes = notes

    # Recount from actual bean rows
    rows = (
        db.query(BeanRecord.grade, func.count(BeanRecord.Brecords_id))
        .filter(BeanRecord.session_id == session_id)
        .group_by(BeanRecord.grade)
        .all()
    )
    grade_map = {r[0]: r[1] for r in rows}

    # Map new 4-grade system to DB columns
    sess.grade1_count = grade_map.get("Grade 1", 0)
    sess.grade2_count = grade_map.get("Grade 2", 0)
    sess.grade3_count = grade_map.get("Grade 3", 0)
    sess.grade4_count = grade_map.get("Grade 4", 0)
    sess.total_beans  = sum(grade_map.values())

    db.commit()
    db.refresh(sess)
    return sess


def get_sorting_sessions(
    db: Session,
    limit: int  = 50,
    offset: int = 0,
    active_only: bool = False,
) -> list[SortingSession]:
    q = db.query(SortingSession).order_by(desc(SortingSession.started_at))
    if active_only:
        q = q.filter(SortingSession.is_active == 1)
    return q.offset(offset).limit(limit).all()


def get_sorting_session(db: Session, session_id: int) -> Optional[SortingSession]:
    return db.get(SortingSession, session_id)


def update_session_counts(db: Session, session_id: int, grade: str) -> None:
    """Increment the matching grade counter on the session row in place."""
    sess = db.get(SortingSession, session_id)
    if not sess:
        return
    sess.total_beans = (sess.total_beans or 0) + 1
    if grade == "Grade 1":
        sess.grade1_count = (sess.grade1_count or 0) + 1
    elif grade == "Grade 2":
        sess.grade2_count = (sess.grade2_count or 0) + 1
    elif grade == "Grade 3":
        sess.grade3_count = (sess.grade3_count or 0) + 1
    else:  # Grade 4 — Defect
        sess.grade4_count = (sess.grade4_count or 0) + 1
    db.commit()


# ══════════════════════════════════════════════════════════════════════════
# DETECTION_LOGS
# ══════════════════════════════════════════════════════════════════════════

def create_detection_log(
    db: Session,
    session_id: int,
    frame_number: int,
    beans_detected: int,
    processing_time_ms: float,
    raw_result: dict | None = None,
) -> DetectionLog:
    """
    Insert one detection log row per camera frame processed.
    raw_result is stored as JSON text in the CLOB column.
    """
    log = DetectionLog(
        session_id         = session_id,
        logged_at          = datetime.utcnow(),
        frame_number       = frame_number,
        beans_detected     = beans_detected,
        processing_time_ms = processing_time_ms,
        raw_result         = json.dumps(raw_result) if raw_result else None,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def get_detection_logs(
    db: Session,
    session_id: Optional[int] = None,
    limit: int  = 100,
    offset: int = 0,
) -> list[DetectionLog]:
    q = db.query(DetectionLog).order_by(desc(DetectionLog.logged_at))
    if session_id is not None:
        q = q.filter(DetectionLog.session_id == session_id)
    return q.offset(offset).limit(limit).all()


def get_detection_log(db: Session, log_id: int) -> Optional[DetectionLog]:
    return db.get(DetectionLog, log_id)


# ══════════════════════════════════════════════════════════════════════════
# BEAN_RECORDS
# ══════════════════════════════════════════════════════════════════════════

def create_bean_record(
    db: Session,
    bean: BeanResult,
    session_id: int,
    image_path: str = "",
) -> BeanRecord:
    """
    Persist one detected bean from the OpenCV pipeline.
    Maps BeanResult Pydantic fields to BeanRecord ORM columns.
    """
    record = BeanRecord(
        session_id  = session_id,
        detected_at = datetime.utcnow(),
        grade       = bean.grade.value,
        color_value = bean.color_name[:20] if bean.color_name else None,
        size_mm     = float(bean.size_mm),
        confidence  = float(bean.confidence) / 100.0,  # store as 0.0–1.0 per NUMBER(10,8)
        bbox_x      = bean.bbox_x,
        bbox_y      = bean.bbox_y,
        bbox_w      = bean.bbox_w,
        bbox_h      = bean.bbox_h,
        image_path  = image_path or None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # Also increment session grade counters
    update_session_counts(db, session_id, bean.grade.value)

    return record


def get_bean_records(
    db: Session,
    session_id: Optional[int] = None,
    grade: Optional[str]      = None,
    limit: int  = 100,
    offset: int = 0,
) -> list[BeanRecord]:
    q = db.query(BeanRecord).order_by(desc(BeanRecord.detected_at))
    if session_id is not None:
        q = q.filter(BeanRecord.session_id == session_id)
    if grade:
        q = q.filter(BeanRecord.grade == grade)
    return q.offset(offset).limit(limit).all()


def get_bean_record(db: Session, record_id: int) -> Optional[BeanRecord]:
    return db.get(BeanRecord, record_id)


def get_bean_stats(
    db: Session,
    session_id: Optional[int] = None,
) -> dict:
    """Aggregate stats: counts per grade, avg size, avg confidence."""
    q_base = db.query(BeanRecord)
    if session_id:
        q_base = q_base.filter(BeanRecord.session_id == session_id)

    agg = db.query(
        func.count(BeanRecord.Brecords_id).label("total"),
        func.avg(BeanRecord.size_mm).label("avg_size"),
        func.avg(BeanRecord.confidence).label("avg_conf"),
        func.min(BeanRecord.size_mm).label("min_size"),
        func.max(BeanRecord.size_mm).label("max_size"),
    )
    if session_id:
        agg = agg.filter(BeanRecord.session_id == session_id)
    row = agg.one()

    dist_q = db.query(BeanRecord.grade, func.count(BeanRecord.Brecords_id)).group_by(BeanRecord.grade)
    if session_id:
        dist_q = dist_q.filter(BeanRecord.session_id == session_id)
    distribution = {r[0]: r[1] for r in dist_q.all()}

    total    = row.total or 0
    defective= distribution.get("Defective", 0)
    good     = total - defective

    return {
        "total":            total,
        "avg_size_mm":      round(float(row.avg_size  or 0), 3),
        "avg_confidence":   round(float(row.avg_conf  or 0) * 100, 1),
        "min_size_mm":      round(float(row.min_size  or 0), 3),
        "max_size_mm":      round(float(row.max_size  or 0), 3),
        "good_yield_pct":   round((good     / total * 100) if total > 0 else 0, 1),
        "defect_rate_pct":  round((defective/ total * 100) if total > 0 else 0, 1),
        "grade_distribution": distribution,
    }


# ══════════════════════════════════════════════════════════════════════════
# SORTING_ACTIONS
# ══════════════════════════════════════════════════════════════════════════

def create_sorting_action(
    db: Session,
    session_id: int,
    bean_record_id: int,
    grade: str,
    target_container: str,
    actuator_id: str       = "",
    actuator_pin: int      = 0,
    success: bool          = True,
    error_message: str     = "",
    latency_ms: float      = 0.0,
) -> SortingAction:
    action = SortingAction(
        session_id       = session_id,
        bean_record_id   = bean_record_id,
        grade            = grade,
        target_container = target_container,
        actuator_id      = actuator_id or None,
        actuator_pin     = actuator_pin or None,
        signal_sent_at   = datetime.utcnow(),
        success          = 1 if success else 0,
        error_message    = error_message or None,
        latency_ms       = latency_ms or None,
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


def get_sorting_actions(
    db: Session,
    session_id: Optional[int]     = None,
    bean_record_id: Optional[int] = None,
    limit: int  = 100,
    offset: int = 0,
) -> list[SortingAction]:
    q = db.query(SortingAction).order_by(desc(SortingAction.signal_sent_at))
    if session_id is not None:
        q = q.filter(SortingAction.session_id == session_id)
    if bean_record_id is not None:
        q = q.filter(SortingAction.bean_record_id == bean_record_id)
    return q.offset(offset).limit(limit).all()


def get_sorting_action(db: Session, action_id: int) -> Optional[SortingAction]:
    return db.get(SortingAction, action_id)


# ══════════════════════════════════════════════════════════════════════════
# SORTING_ALERTS
# ══════════════════════════════════════════════════════════════════════════

def create_sorting_alert(
    db: Session,
    session_id: int,
    alert_type: str,
    severity: str,
    title: str,
    message: str,
    bean_record_id: Optional[int]   = None,
    sorting_action_id: Optional[int]= None,
    context_value: Optional[float]  = None,
    threshold_value: Optional[float]= None,
    extra_data: Optional[dict]      = None,
) -> SortingAlert:
    alert = SortingAlert(
        session_id        = session_id,
        bean_record_id    = bean_record_id,
        sorting_action_id = sorting_action_id,
        alert_type        = alert_type,
        severity          = severity,
        title             = title,
        message           = message,
        context_value     = context_value,
        threshold_value   = threshold_value,
        extra_data        = json.dumps(extra_data) if extra_data else None,
        triggered_at      = datetime.utcnow(),
        acknowledged      = 0,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def create_alert_from_model(
    db: Session,
    alert: Alert,
    session_id: int,
    bean_record_id: Optional[int]   = None,
    sorting_action_id: Optional[int]= None,
    context_value: Optional[float]  = None,
    threshold_value: Optional[float]= None,
) -> SortingAlert:
    """Convenience wrapper — converts Alert Pydantic model to SortingAlert row."""
    severity_map = {
        AlertLevel.INFO:     "info",
        AlertLevel.WARNING:  "warning",
        AlertLevel.CRITICAL: "critical",
    }
    return create_sorting_alert(
        db                = db,
        session_id        = session_id,
        alert_type        = alert.source,
        severity          = severity_map.get(alert.level, "info"),
        title             = alert.title,
        message           = alert.description,
        bean_record_id    = bean_record_id,
        sorting_action_id = sorting_action_id,
        context_value     = context_value,
        threshold_value   = threshold_value,
    )


def get_sorting_alerts(
    db: Session,
    session_id: Optional[int]    = None,
    severity: Optional[str]      = None,
    acknowledged: Optional[bool] = None,
    limit: int  = 100,
    offset: int = 0,
) -> list[SortingAlert]:
    q = db.query(SortingAlert).order_by(desc(SortingAlert.triggered_at))
    if session_id is not None:
        q = q.filter(SortingAlert.session_id == session_id)
    if severity:
        q = q.filter(SortingAlert.severity == severity)
    if acknowledged is not None:
        q = q.filter(SortingAlert.acknowledged == (1 if acknowledged else 0))
    return q.offset(offset).limit(limit).all()


def acknowledge_alert(db: Session, alert_id: int) -> Optional[SortingAlert]:
    alert = db.get(SortingAlert, alert_id)
    if alert:
        alert.acknowledged    = 1
        alert.acknowledged_at = datetime.utcnow()
        db.commit()
        db.refresh(alert)
    return alert


def acknowledge_all_alerts(
    db: Session,
    session_id: Optional[int] = None,
) -> int:
    q = db.query(SortingAlert).filter(SortingAlert.acknowledged == 0)
    if session_id:
        q = q.filter(SortingAlert.session_id == session_id)
    count = q.count()
    q.update(
        {"acknowledged": 1, "acknowledged_at": datetime.utcnow()},
        synchronize_session=False,
    )
    db.commit()
    return count


def get_sorting_alert(db: Session, alert_id: int) -> Optional[SortingAlert]:
    return db.get(SortingAlert, alert_id)


# ══════════════════════════════════════════════════════════════════════════
# ANALYTICS  — cross-table queries
# ══════════════════════════════════════════════════════════════════════════

def get_session_summary(db: Session, session_id: int) -> dict:
    """Full summary for one session: counts, bean stats, action count, alert counts."""
    sess = db.get(SortingSession, session_id)
    if not sess:
        return {}

    bean_stats   = get_bean_stats(db, session_id=session_id)
    action_count = db.query(func.count(SortingAction.Sactions_id)) \
                     .filter(SortingAction.session_id == session_id).scalar() or 0
    alert_counts = dict(
        db.query(SortingAlert.severity, func.count(SortingAlert.Salerts_id))
          .filter(SortingAlert.session_id == session_id)
          .group_by(SortingAlert.severity).all()
    )
    failed_actions = db.query(func.count(SortingAction.Sactions_id)) \
                       .filter(SortingAction.session_id == session_id,
                               SortingAction.success == 0).scalar() or 0
    avg_latency = db.query(func.avg(SortingAction.latency_ms)) \
                    .filter(SortingAction.session_id == session_id).scalar()

    duration = None
    if sess.started_at and sess.ended_at:
        duration = int((sess.ended_at - sess.started_at).total_seconds())

    return {
        "session_id":       sess.session_id,
        "session_name":     sess.session_name,
        "started_at":       sess.started_at.isoformat() if sess.started_at else None,
        "ended_at":         sess.ended_at.isoformat()   if sess.ended_at   else None,
        "duration_seconds": duration,
        "is_active":        bool(sess.is_active),
        "notes":            sess.notes,
        "bean_stats":       bean_stats,
        "action_count":     action_count,
        "failed_actions":   failed_actions,
        "avg_latency_ms":   round(float(avg_latency or 0), 3),
        "alert_counts":     alert_counts,
    }


def get_all_time_totals(db: Session) -> dict:
    """Grand totals across all completed sessions."""
    row = db.query(
        func.count(SortingSession.session_id).label("sessions"),
        func.sum(SortingSession.total_beans).label("total"),
        func.sum(SortingSession.grade1_count).label("grade1"),
        func.sum(SortingSession.grade2_count).label("grade2"),
        func.sum(SortingSession.grade3_count).label("grade3"),
        func.sum(SortingSession.grade4_count).label("grade4"),
    ).filter(SortingSession.is_active == 0).one()

    total = row.total or 0
    return {
        "total_sessions": row.sessions or 0,
        "total_beans":    total,
        "premium":        row.grade1 or 0,
        "grade1":         row.grade2 or 0,
        "grade2":         row.grade3 or 0,
        "grade3_defect":  row.grade4 or 0,
    }


# ══════════════════════════════════════════════════════════════════════════
# THREAD-SAFE SYNC WRITERS  (called from background detection thread)
# ══════════════════════════════════════════════════════════════════════════

def write_bean_sync(
    bean: BeanResult,
    session_id: int,
    image_path: str = "",
) -> int:
    """
    Write a BeanRecord from a background thread.
    Opens its own session, commits, closes.
    Returns the new Brecords_id.
    """
    db = SessionLocal()
    try:
        record = create_bean_record(db, bean, session_id, image_path)
        return record.Brecords_id
    except Exception as exc:
        db.rollback()
        raise exc
    finally:
        db.close()


def write_action_sync(
    session_id: int,
    bean_record_id: int,
    grade: str,
    target_container: str,
    actuator_id: str   = "",
    actuator_pin: int  = 0,
    success: bool      = True,
    latency_ms: float  = 0.0,
) -> int:
    """Write a SortingAction from a background thread. Returns Sactions_id."""
    db = SessionLocal()
    try:
        action = create_sorting_action(
            db, session_id, bean_record_id, grade,
            target_container, actuator_id, actuator_pin,
            success, "", latency_ms,
        )
        return action.Sactions_id
    except Exception as exc:
        db.rollback()
        raise exc
    finally:
        db.close()


def write_alert_sync(
    alert: Alert,
    session_id: int,
    bean_record_id: Optional[int]    = None,
    sorting_action_id: Optional[int] = None,
    context_value: Optional[float]   = None,
    threshold_value: Optional[float] = None,
) -> int:
    """Write a SortingAlert from a background thread. Returns Salerts_id."""
    db = SessionLocal()
    try:
        rec = create_alert_from_model(
            db, alert, session_id,
            bean_record_id, sorting_action_id,
            context_value, threshold_value,
        )
        return rec.Salerts_id
    except Exception as exc:
        db.rollback()
        raise exc
    finally:
        db.close()


def write_detection_log_sync(
    session_id: int,
    frame_number: int,
    beans_detected: int,
    processing_time_ms: float,
    raw_result: dict | None = None,
) -> int:
    """Write a DetectionLog from a background thread. Returns Dlogs_id."""
    db = SessionLocal()
    try:
        log = create_detection_log(
            db, session_id, frame_number,
            beans_detected, processing_time_ms, raw_result,
        )
        return log.Dlogs_id
    except Exception as exc:
        db.rollback()
        raise exc
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════
# SYSTEM_SETTINGS  — persisted operator configuration
# ══════════════════════════════════════════════════════════════════════════

from .db_models import SystemSettings   # local import avoids circular at module level
from .models    import SortingSettings


def load_settings(db: Session) -> Optional[SystemSettings]:
    """
    Load the single settings row (id=1).
    Returns None if settings have never been saved — callers fall back
    to defaults from config.settings.

    Called once on every application startup from main.py lifespan.
    """
    return db.get(SystemSettings, 1)


def save_settings(
    db:            Session,
    settings:      SortingSettings,
    pixels_per_mm: float = 18.0,
) -> SystemSettings:
    """
    Upsert the single settings row (id=1).

    Called from:
      • POST /api/settings  — operator changes settings via UI
      • POST /api/calibrate/pixels_per_mm — camera calibration
      • Startup if defaults need persisting for the first time

    Returns the saved SystemSettings ORM object.
    """
    from datetime import datetime as _dt

    existing = db.get(SystemSettings, 1)
    if existing:
        existing.conveyor_rpm         = settings.conveyor_rpm
        existing.sensitivity          = settings.sensitivity
        existing.min_bean_area_px     = settings.min_bean_area_px
        existing.max_bean_area_px     = settings.max_bean_area_px
        existing.ejection_duration_ms = settings.ejection_duration_ms
        existing.air_pressure_mpa     = settings.air_pressure_mpa
        existing.auto_sort            = settings.auto_sort
        existing.pixels_per_mm        = pixels_per_mm
        existing.updated_at           = _dt.utcnow()
        db.commit()
        db.refresh(existing)
        return existing

    new_row = SystemSettings(
        id                   = 1,
        conveyor_rpm         = settings.conveyor_rpm,
        sensitivity          = settings.sensitivity,
        min_bean_area_px     = settings.min_bean_area_px,
        max_bean_area_px     = settings.max_bean_area_px,
        ejection_duration_ms = settings.ejection_duration_ms,
        air_pressure_mpa     = settings.air_pressure_mpa,
        auto_sort            = settings.auto_sort,
        pixels_per_mm        = pixels_per_mm,
        updated_at           = _dt.utcnow(),
    )
    db.add(new_row)
    db.commit()
    db.refresh(new_row)
    return new_row


def save_settings_sync(
    settings:      SortingSettings,
    pixels_per_mm: float = 18.0,
) -> None:
    """
    Thread-safe settings save — opens its own session, commits, closes.
    Use from background threads when no request session is available.
    """
    db = SessionLocal()
    try:
        save_settings(db, settings, pixels_per_mm)
    except Exception as exc:
        db.rollback()
        raise exc
    finally:
        db.close()
