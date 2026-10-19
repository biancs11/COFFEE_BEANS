"""
Database engine, session factory, and Base — production hardened.

Changes from dev version:
  • busy_timeout=5000ms   — prevents "database is locked" under concurrent writes
  • wal_autocheckpoint=0  — manual checkpoint only, avoids mid-write pauses
  • temp_store=MEMORY     — temp tables in RAM, faster sorts/aggregates
  • mmap_size             — memory-mapped I/O for faster reads on RPi SSD/SD
  • NullPool              — fresh connection per request (recommended for SQLite)
  • DB path driven by config.settings.db_url
"""

from __future__ import annotations
import logging
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool

from backend.core.config import settings

logger = logging.getLogger(__name__)

# ── Engine ─────────────────────────────────────────────────────────────────
engine = create_engine(
    settings.db_url,
    connect_args={"check_same_thread": False},
    poolclass=NullPool,      # new connection per request — avoids WAL contention
    echo=False,
)


@event.listens_for(engine, "connect")
def _set_pragmas(dbapi_conn, _record):
    """Apply SQLite pragmas on every new connection."""
    cur = dbapi_conn.cursor()

    # Crash-safe concurrent writes
    cur.execute("PRAGMA journal_mode=WAL")

    # Durability vs speed trade-off (NORMAL = safe enough for RPi SD card)
    cur.execute("PRAGMA synchronous=NORMAL")

    # Enforce FK relationships
    cur.execute("PRAGMA foreign_keys=ON")

    # 32 MB page cache — reduces SD card I/O
    cur.execute("PRAGMA cache_size=-32000")

    # CRITICAL FIX: prevent "database is locked" under heavy concurrent writes
    # Detection loop writes ~40 rows/s; REST reads happen simultaneously
    cur.execute("PRAGMA busy_timeout=5000")

    # Keep temp tables in RAM
    cur.execute("PRAGMA temp_store=MEMORY")

    # Memory-mapped I/O: 256 MB — faster sequential reads
    cur.execute("PRAGMA mmap_size=268435456")

    # Disable auto-checkpoint — we checkpoint manually on session close
    # This prevents a mid-detection-loop pause on the Pi
    cur.execute("PRAGMA wal_autocheckpoint=0")

    cur.close()
    logger.debug("SQLite pragmas applied")


@event.listens_for(engine, "close")
def _checkpoint_on_close(dbapi_conn, _record):
    """
    Run a WAL checkpoint when a connection closes.
    With wal_autocheckpoint=0 this is the only time we flush WAL to the main db.
    PASSIVE mode — does not block ongoing readers or writers.
    """
    try:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA wal_checkpoint(PASSIVE)")
        cur.close()
    except Exception:
        pass   # best-effort — don't raise during connection teardown


# ── Session factory ────────────────────────────────────────────────────────
# autoflush=False: we control when writes hit the DB
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ── Declarative base ───────────────────────────────────────────────────────
Base = declarative_base()


# ── FastAPI dependency ─────────────────────────────────────────────────────
def get_db():
    """
    Yields a SQLAlchemy session and guarantees it is closed after the request,
    even if an exception is raised.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ── One-time table creation ────────────────────────────────────────────────
def init_db() -> None:
    """
    Create all ORM-defined tables if they do not exist.
    Safe to call on every startup — uses CREATE TABLE IF NOT EXISTS semantics.
    """
    from backend.core import db_models  # noqa: F401 — registers models with Base
    Base.metadata.create_all(bind=engine)
    logger.info(f"Database initialised at: {settings.db_url}")


# ── Manual WAL checkpoint (call periodically or on session end) ────────────
def checkpoint_db() -> dict:
    """
    Force a full WAL checkpoint.
    Returns {"busy": int, "log": int, "checkpointed": int}.
    Call this after closing a sorting session to keep the WAL file small.
    """
    with engine.connect() as conn:
        row = conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE)")).fetchone()
    return {"busy": row[0], "log": row[1], "checkpointed": row[2]}
