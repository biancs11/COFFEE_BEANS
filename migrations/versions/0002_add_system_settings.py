"""Add system_settings table

Revision ID: 0002_add_system_settings
Revises: 0001_initial_schema
Create Date: 2026-09-14 01:00:00.000000

Adds a single-row settings table so operator configuration
persists across process restarts without manual .env edits.
"""

from __future__ import annotations
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision:       str                          = "0002_add_system_settings"
down_revision:  Union[str, None]             = "0001_initial_schema"
branch_labels:  Union[str, Sequence[str], None] = None
depends_on:     Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("id",                    sa.Integer(),  nullable=False),
        sa.Column("conveyor_rpm",          sa.Integer(),  nullable=False, server_default="180"),
        sa.Column("sensitivity",           sa.Float(),    nullable=False, server_default="0.85"),
        sa.Column("min_bean_area_px",      sa.Integer(),  nullable=False, server_default="400"),
        sa.Column("max_bean_area_px",      sa.Integer(),  nullable=False, server_default="8000"),
        sa.Column("ejection_duration_ms",  sa.Integer(),  nullable=False, server_default="40"),
        sa.Column("air_pressure_mpa",      sa.Float(),    nullable=False, server_default="0.6"),
        sa.Column("auto_sort",             sa.Boolean(),  nullable=False, server_default="1"),
        sa.Column("pixels_per_mm",         sa.Float(),    nullable=False, server_default="18.0"),
        sa.Column("updated_at",            sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_system_settings"),
    )

    # Insert the default row immediately so load_settings() always finds one
    op.execute(
        """
        INSERT INTO system_settings
          (id, conveyor_rpm, sensitivity, min_bean_area_px, max_bean_area_px,
           ejection_duration_ms, air_pressure_mpa, auto_sort, pixels_per_mm, updated_at)
        VALUES
          (1, 180, 0.85, 400, 8000, 40, 0.6, 1, 18.0, datetime('now'))
        """
    )


def downgrade() -> None:
    op.drop_table("system_settings")
