"""
Alembic environment — wires SQLAlchemy metadata and DB URL from config.

Usage:
    # Generate a new migration after changing db_models.py:
    alembic revision --autogenerate -m "describe your change"

    # Apply all pending migrations:
    alembic upgrade head

    # Roll back one step:
    alembic downgrade -1

    # Show current migration state:
    alembic current
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path so backend imports resolve
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ── Pull config + ORM metadata ─────────────────────────────────────────────
from backend.core.config import settings
from backend.core.database import Base
import backend.core.db_models  # noqa: F401 — registers all ORM models

config = context.config

# Override sqlalchemy.url from our settings (ignores blank value in alembic.ini)
config.set_main_option("sqlalchemy.url", settings.db_url)

# Set up Python logging from alembic.ini [loggers] section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The metadata Alembic uses for --autogenerate
target_metadata = Base.metadata


# ── Offline mode (generates SQL without connecting) ────────────────────────
def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,   # required for SQLite ALTER TABLE support
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online mode (connects and migrates) ────────────────────────────────────
def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,   # required for SQLite ALTER TABLE support
            compare_type=True,      # detect column type changes
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
