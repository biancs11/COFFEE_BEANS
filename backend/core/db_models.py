"""
SQLAlchemy ORM — exact schema from ERD diagram.

Tables (5):
  sorting_sessions   PK: session_id
  detection_logs     PK: Dlogs_id     FK → sorting_sessions
  bean_records       PK: Brecords_id  FK → sorting_sessions
  sorting_alerts     PK: Salerts_id   FK → sorting_sessions, bean_records, sorting_actions
  sorting_actions    PK: Sactions_id  FK → sorting_sessions, bean_records
"""

from __future__ import annotations
from datetime import datetime

from sqlalchemy import (
    Column, Integer, Float, String, Boolean,
    DateTime, Text, ForeignKey, Index,
    Numeric, TIMESTAMP,
)
from sqlalchemy.orm import relationship

from .database import Base


# ══════════════════════════════════════════════════════════════════════════
# 1. SORTING_SESSIONS
# ══════════════════════════════════════════════════════════════════════════

class SortingSession(Base):
    __tablename__ = "sorting_sessions"

    # PK
    session_id   = Column(Integer,      primary_key=True, autoincrement=True)   # NUMBER(10)

    # Columns (starred = NOT NULL in ERD)
    session_name = Column(String(100),  nullable=False)                          # VARCHAR2(100)  *
    started_at   = Column(TIMESTAMP,    nullable=False, default=datetime.utcnow) # TIMESTAMP      *
    ended_at     = Column(TIMESTAMP,    nullable=True)                           # TIMESTAMP
    is_active    = Column(Integer,      nullable=False, default=1)               # NUMBER(1)      *
    total_beans  = Column(Integer,      nullable=False, default=0)               # NUMBER(10)     *
    grade1_count = Column(Integer,      nullable=False, default=0)               # NUMBER(10)     *
    grade2_count = Column(Integer,      nullable=False, default=0)               # NUMBER(10)     *
    grade3_count = Column(Integer,      nullable=False, default=0)               # NUMBER(10)     *
    grade4_count = Column(Integer,      nullable=False, default=0)               # NUMBER(10)     *
    notes        = Column(Text,         nullable=True)                           # CLOB

    # Relationships
    detection_logs  = relationship("DetectionLog",   back_populates="session",  cascade="all, delete-orphan")
    bean_records    = relationship("BeanRecord",     back_populates="session",  cascade="all, delete-orphan")
    sorting_alerts  = relationship("SortingAlert",   back_populates="session",  cascade="all, delete-orphan")
    sorting_actions = relationship("SortingAction",  back_populates="session",  cascade="all, delete-orphan")

    # Constraint
    __table_args__ = (
        Index("pk_sorting_sessions", "session_id", unique=True),
    )

    def __repr__(self):
        return f"<SortingSession id={self.session_id} name={self.session_name!r} active={self.is_active}>"


# ══════════════════════════════════════════════════════════════════════════
# 2. DETECTION_LOGS
# ══════════════════════════════════════════════════════════════════════════

class DetectionLog(Base):
    __tablename__ = "detection_logs"

    # PK
    Dlogs_id           = Column(Integer,       primary_key=True, autoincrement=True)  # NUMBER(10)   P *

    # FK
    session_id         = Column(Integer,       ForeignKey("sorting_sessions.session_id", ondelete="CASCADE"),
                                               nullable=False)                         # NUMBER(10)   F *

    # Columns
    logged_at          = Column(TIMESTAMP,     nullable=False, default=datetime.utcnow) # TIMESTAMP   *
    frame_number       = Column(Integer,       nullable=True)                           # NUMBER(10)
    beans_detected     = Column(Integer,       nullable=True, default=0)                # NUMBER(10)
    processing_time_ms = Column(Numeric(12, 3),nullable=True)                           # NUMBER(12,3)
    raw_result         = Column(Text,          nullable=True)                           # CLOB

    # Relationship
    session = relationship("SortingSession", back_populates="detection_logs")

    __table_args__ = (
        Index("pk_detection_logs",       "Dlogs_id",  unique=True),
        Index("fk_detection_session_idx","session_id"),
    )

    def __repr__(self):
        return f"<DetectionLog id={self.Dlogs_id} session={self.session_id} frame={self.frame_number}>"


# ══════════════════════════════════════════════════════════════════════════
# 3. BEAN_RECORDS
# ══════════════════════════════════════════════════════════════════════════

class BeanRecord(Base):
    __tablename__ = "bean_records"

    # PK
    Brecords_id  = Column(Integer,       primary_key=True, autoincrement=True)   # NUMBER(10)    P *

    # FK
    session_id   = Column(Integer,       ForeignKey("sorting_sessions.session_id", ondelete="CASCADE"),
                                         nullable=False)                          # NUMBER(10)    F *

    # Columns (starred = NOT NULL)
    detected_at  = Column(TIMESTAMP,     nullable=False, default=datetime.utcnow) # TIMESTAMP     *
    grade        = Column(String(10),    nullable=False)                          # VARCHAR2(10)  *
    color_value  = Column(String(20),    nullable=True)                           # VARCHAR2(20)
    size_mm      = Column(Numeric(10, 3),nullable=True)                           # NUMBER(10,3)
    confidence   = Column(Numeric(10, 8),nullable=True)                           # NUMBER(10,8)
    bbox_x       = Column(Integer,       nullable=True)                           # NUMBER(10)
    bbox_y       = Column(Integer,       nullable=True)                           # NUMBER(10)
    bbox_w       = Column(Integer,       nullable=True)                           # NUMBER(10)
    bbox_h       = Column(Integer,       nullable=True)                           # NUMBER(10)
    image_path   = Column(String(255),   nullable=True)                           # VARCHAR2(255)

    # Relationships
    session         = relationship("SortingSession", back_populates="bean_records")
    sorting_alerts  = relationship("SortingAlert",   back_populates="bean_record")
    sorting_actions = relationship("SortingAction",  back_populates="bean_record")

    __table_args__ = (
        Index("pk_bean_records",      "Brecords_id", unique=True),
        Index("fk_bean_session_idx",  "session_id"),
    )

    def __repr__(self):
        return f"<BeanRecord id={self.Brecords_id} grade={self.grade} size={self.size_mm}mm>"


# ══════════════════════════════════════════════════════════════════════════
# 4. SORTING_ACTIONS
# (defined before sorting_alerts so FK can reference it)
# ══════════════════════════════════════════════════════════════════════════

class SortingAction(Base):
    __tablename__ = "sorting_actions"

    # PK
    Sactions_id     = Column(Integer,       primary_key=True, autoincrement=True)  # NUMBER(10)    P *

    # FKs
    session_id      = Column(Integer,       ForeignKey("sorting_sessions.session_id", ondelete="CASCADE"),
                                            nullable=False)                         # NUMBER(10)    F *
    bean_record_id  = Column(Integer,       ForeignKey("bean_records.Brecords_id",   ondelete="CASCADE"),
                                            nullable=False)                         # NUMBER(10)    F *

    # Columns (starred = NOT NULL)
    grade           = Column(String(10),    nullable=False)                         # VARCHAR2(10)  *
    target_container= Column(String(50),    nullable=False)                         # VARCHAR2(50)  *
    actuator_id     = Column(String(50),    nullable=True)                          # VARCHAR2(50)
    actuator_pin    = Column(Integer,       nullable=True)                          # NUMBER(10)
    signal_sent_at  = Column(TIMESTAMP,     nullable=False, default=datetime.utcnow)# TIMESTAMP     *
    success         = Column(Integer,       nullable=False, default=1)              # NUMBER(1)     *
    error_message   = Column(Text,          nullable=True)                          # CLOB
    latency_ms      = Column(Numeric(12, 3),nullable=True)                          # NUMBER(12,3)

    # Relationships
    session     = relationship("SortingSession", back_populates="sorting_actions")
    bean_record = relationship("BeanRecord",     back_populates="sorting_actions")
    alerts      = relationship("SortingAlert",   back_populates="sorting_action")

    __table_args__ = (
        Index("pk_sorting_actions",       "Sactions_id",    unique=True),
        Index("fk_action_bean_idx",       "bean_record_id"),
        Index("fk_action_session_idx",    "session_id"),
    )

    def __repr__(self):
        return f"<SortingAction id={self.Sactions_id} grade={self.grade} container={self.target_container} ok={self.success}>"


# ══════════════════════════════════════════════════════════════════════════
# 5. SORTING_ALERTS
# ══════════════════════════════════════════════════════════════════════════

class SortingAlert(Base):
    __tablename__ = "sorting_alerts"

    # PK
    Salerts_id       = Column(Integer,       primary_key=True, autoincrement=True)  # NUMBER(10)    P *

    # FKs
    session_id       = Column(Integer,       ForeignKey("sorting_sessions.session_id", ondelete="CASCADE"),
                                             nullable=False)                         # NUMBER(10)    F *
    bean_record_id   = Column(Integer,       ForeignKey("bean_records.Brecords_id",   ondelete="SET NULL"),
                                             nullable=True)                          # NUMBER(10)    F
    sorting_action_id= Column(Integer,       ForeignKey("sorting_actions.Sactions_id",ondelete="SET NULL"),
                                             nullable=True)                          # NUMBER(10)    F

    # Columns (starred = NOT NULL)
    alert_type       = Column(String(30),    nullable=False)                         # VARCHAR2(30)  *
    severity         = Column(String(10),    nullable=False)                         # VARCHAR2(10)  *
    title            = Column(String(120),   nullable=False)                         # VARCHAR2(120) *
    message          = Column(Text,          nullable=False)                         # CLOB          *
    context_value    = Column(Numeric(10, 3),nullable=True)                          # NUMBER(10,3)
    threshold_value  = Column(Numeric(10, 3),nullable=True)                          # NUMBER(10,3)
    extra_data       = Column(Text,          nullable=True)                          # CLOB
    triggered_at     = Column(TIMESTAMP,     nullable=False, default=datetime.utcnow)# TIMESTAMP     *
    acknowledged     = Column(Integer,       nullable=False, default=0)              # NUMBER(1)     *
    acknowledged_at  = Column(TIMESTAMP,     nullable=True)                          # TIMESTAMP

    # Relationships
    session        = relationship("SortingSession", back_populates="sorting_alerts")
    bean_record    = relationship("BeanRecord",     back_populates="sorting_alerts")
    sorting_action = relationship("SortingAction",  back_populates="alerts")

    __table_args__ = (
        Index("pk_sorting_alerts",        "Salerts_id",       unique=True),
        Index("fk_alert_action_idx",      "sorting_action_id"),
        Index("fk_alert_bean_idx",        "bean_record_id"),
        Index("fk_alert_session_idx",     "session_id"),
        Index("ix_alert_severity",        "severity"),
        Index("ix_alert_triggered_at",    "triggered_at"),
    )

    def __repr__(self):
        return f"<SortingAlert id={self.Salerts_id} type={self.alert_type} severity={self.severity}>"


# ══════════════════════════════════════════════════════════════════════════
# 6. SYSTEM_SETTINGS  (single persisted row, id=1 always)
# ══════════════════════════════════════════════════════════════════════════

class SystemSettings(Base):
    """
    Persisted operator settings — one row (id=1), upserted on every save.

    Allows settings to survive process restarts without re-configuring
    from the UI. On startup, main.py loads this row into AppState.
    """
    __tablename__ = "system_settings"

    id                    = Column(Integer,  primary_key=True, default=1)
    conveyor_rpm          = Column(Integer,  nullable=False, default=180)
    sensitivity           = Column(Float,    nullable=False, default=0.85)
    min_bean_area_px      = Column(Integer,  nullable=False, default=400)
    max_bean_area_px      = Column(Integer,  nullable=False, default=8000)
    ejection_duration_ms  = Column(Integer,  nullable=False, default=40)
    air_pressure_mpa      = Column(Float,    nullable=False, default=0.6)
    auto_sort             = Column(Boolean,  nullable=False, default=True)
    pixels_per_mm         = Column(Float,    nullable=False, default=18.0)
    updated_at            = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return (
            f"<SystemSettings rpm={self.conveyor_rpm} "
            f"sensitivity={self.sensitivity} ppm={self.pixels_per_mm}>"
        )


class ColorCalibrationSample(Base):
    """One currently registered camera color for each coffee grade."""
    __tablename__ = "color_calibration_samples"

    grade = Column(String(16), primary_key=True)
    color_hex = Column(String(7), nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
