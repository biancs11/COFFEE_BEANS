"""Initial schema — 5 tables from ERD

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-14 00:00:00.000000

Tables created:
  sorting_sessions
  detection_logs
  bean_records
  sorting_actions
  sorting_alerts
"""

from __future__ import annotations
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on:    Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── sorting_sessions ──────────────────────────────────────────────────
    op.create_table(
        "sorting_sessions",
        sa.Column("session_id",    sa.Integer(),     nullable=False),
        sa.Column("session_name",  sa.String(100),   nullable=False),
        sa.Column("started_at",    sa.TIMESTAMP(),   nullable=False),
        sa.Column("ended_at",      sa.TIMESTAMP(),   nullable=True),
        sa.Column("is_active",     sa.Integer(),     nullable=False, server_default="1"),
        sa.Column("total_beans",   sa.Integer(),     nullable=False, server_default="0"),
        sa.Column("grade1_count",  sa.Integer(),     nullable=False, server_default="0"),
        sa.Column("grade2_count",  sa.Integer(),     nullable=False, server_default="0"),
        sa.Column("grade3_count",  sa.Integer(),     nullable=False, server_default="0"),
        sa.Column("grade4_count",  sa.Integer(),     nullable=False, server_default="0"),
        sa.Column("notes",         sa.Text(),        nullable=True),
        sa.PrimaryKeyConstraint("session_id", name="pk_sorting_sessions"),
    )
    op.create_index("ix_sessions_is_active",  "sorting_sessions", ["is_active"])
    op.create_index("ix_sessions_started_at", "sorting_sessions", ["started_at"])

    # ── detection_logs ────────────────────────────────────────────────────
    op.create_table(
        "detection_logs",
        sa.Column("Dlogs_id",           sa.Integer(),        nullable=False),
        sa.Column("session_id",         sa.Integer(),        nullable=False),
        sa.Column("logged_at",          sa.TIMESTAMP(),      nullable=False),
        sa.Column("frame_number",       sa.Integer(),        nullable=True),
        sa.Column("beans_detected",     sa.Integer(),        nullable=True),
        sa.Column("processing_time_ms", sa.Numeric(12, 3),   nullable=True),
        sa.Column("raw_result",         sa.Text(),           nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sorting_sessions.session_id"],
            name="fk_detection_session",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("Dlogs_id", name="pk_detection_logs"),
    )
    op.create_index("ix_dlog_session",    "detection_logs", ["session_id"])
    op.create_index("ix_dlog_logged_at",  "detection_logs", ["logged_at"])

    # ── bean_records ──────────────────────────────────────────────────────
    op.create_table(
        "bean_records",
        sa.Column("Brecords_id",  sa.Integer(),        nullable=False),
        sa.Column("session_id",   sa.Integer(),        nullable=False),
        sa.Column("detected_at",  sa.TIMESTAMP(),      nullable=False),
        sa.Column("grade",        sa.String(10),       nullable=False),
        sa.Column("color_value",  sa.String(20),       nullable=True),
        sa.Column("size_mm",      sa.Numeric(10, 3),   nullable=True),
        sa.Column("confidence",   sa.Numeric(10, 8),   nullable=True),
        sa.Column("bbox_x",       sa.Integer(),        nullable=True),
        sa.Column("bbox_y",       sa.Integer(),        nullable=True),
        sa.Column("bbox_w",       sa.Integer(),        nullable=True),
        sa.Column("bbox_h",       sa.Integer(),        nullable=True),
        sa.Column("image_path",   sa.String(255),      nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sorting_sessions.session_id"],
            name="fk_bean_session",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("Brecords_id", name="pk_bean_records"),
    )
    op.create_index("ix_bean_session",     "bean_records", ["session_id"])
    op.create_index("ix_bean_grade",       "bean_records", ["grade"])
    op.create_index("ix_bean_detected_at", "bean_records", ["detected_at"])

    # ── sorting_actions ───────────────────────────────────────────────────
    op.create_table(
        "sorting_actions",
        sa.Column("Sactions_id",      sa.Integer(),        nullable=False),
        sa.Column("session_id",       sa.Integer(),        nullable=False),
        sa.Column("bean_record_id",   sa.Integer(),        nullable=False),
        sa.Column("grade",            sa.String(10),       nullable=False),
        sa.Column("target_container", sa.String(50),       nullable=False),
        sa.Column("actuator_id",      sa.String(50),       nullable=True),
        sa.Column("actuator_pin",     sa.Integer(),        nullable=True),
        sa.Column("signal_sent_at",   sa.TIMESTAMP(),      nullable=False),
        sa.Column("success",          sa.Integer(),        nullable=False, server_default="1"),
        sa.Column("error_message",    sa.Text(),           nullable=True),
        sa.Column("latency_ms",       sa.Numeric(12, 3),   nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sorting_sessions.session_id"],
            name="fk_action_session",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["bean_record_id"], ["bean_records.Brecords_id"],
            name="fk_action_bean",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("Sactions_id", name="pk_sorting_actions"),
    )
    op.create_index("ix_action_session",    "sorting_actions", ["session_id"])
    op.create_index("ix_action_bean",       "sorting_actions", ["bean_record_id"])
    op.create_index("ix_action_sent_at",    "sorting_actions", ["signal_sent_at"])

    # ── sorting_alerts ────────────────────────────────────────────────────
    op.create_table(
        "sorting_alerts",
        sa.Column("Salerts_id",        sa.Integer(),        nullable=False),
        sa.Column("session_id",        sa.Integer(),        nullable=False),
        sa.Column("bean_record_id",    sa.Integer(),        nullable=True),
        sa.Column("sorting_action_id", sa.Integer(),        nullable=True),
        sa.Column("alert_type",        sa.String(30),       nullable=False),
        sa.Column("severity",          sa.String(10),       nullable=False),
        sa.Column("title",             sa.String(120),      nullable=False),
        sa.Column("message",           sa.Text(),           nullable=False),
        sa.Column("context_value",     sa.Numeric(10, 3),   nullable=True),
        sa.Column("threshold_value",   sa.Numeric(10, 3),   nullable=True),
        sa.Column("extra_data",        sa.Text(),           nullable=True),
        sa.Column("triggered_at",      sa.TIMESTAMP(),      nullable=False),
        sa.Column("acknowledged",      sa.Integer(),        nullable=False, server_default="0"),
        sa.Column("acknowledged_at",   sa.TIMESTAMP(),      nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sorting_sessions.session_id"],
            name="fk_alert_session",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["bean_record_id"], ["bean_records.Brecords_id"],
            name="fk_alert_bean",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["sorting_action_id"], ["sorting_actions.Sactions_id"],
            name="fk_alert_action",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("Salerts_id", name="pk_sorting_alerts"),
    )
    op.create_index("ix_alert_session",      "sorting_alerts", ["session_id"])
    op.create_index("ix_alert_severity",     "sorting_alerts", ["severity"])
    op.create_index("ix_alert_triggered_at", "sorting_alerts", ["triggered_at"])
    op.create_index("ix_alert_acknowledged", "sorting_alerts", ["acknowledged"])


def downgrade() -> None:
    op.drop_table("sorting_alerts")
    op.drop_table("sorting_actions")
    op.drop_table("bean_records")
    op.drop_table("detection_logs")
    op.drop_table("sorting_sessions")
