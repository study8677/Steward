"""execution runtime and connector runtime schema

Revision ID: 20260302_0002
Revises: 20260301_0001
Create Date: 2026-03-02 10:58:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260302_0002"
down_revision = "20260301_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add async execution and connector runtime tables."""
    op.add_column(
        "action_plans",
        sa.Column("execution_status", sa.String(length=32), nullable=False, server_default="idle"),
    )
    op.add_column(
        "action_plans",
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("action_plans", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column("action_plans", sa.Column("dispatch_id", sa.String(length=64), nullable=True))
    op.create_index("ix_action_plans_execution_status", "action_plans", ["execution_status"])
    op.create_index("ix_action_plans_dispatch_id", "action_plans", ["dispatch_id"])

    op.create_table(
        "execution_dispatches",
        sa.Column("dispatch_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "plan_id", sa.String(length=64), sa.ForeignKey("action_plans.plan_id"), nullable=False
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("trigger_reason", sa.String(length=128), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_execution_dispatches_plan_id", "execution_dispatches", ["plan_id"])
    op.create_index("ix_execution_dispatches_status", "execution_dispatches", ["status"])
    op.create_index(
        "ix_execution_dispatch_status_queued",
        "execution_dispatches",
        ["status", "queued_at"],
    )

    op.create_table(
        "execution_attempts",
        sa.Column("attempt_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "dispatch_id",
            sa.String(length=64),
            sa.ForeignKey("execution_dispatches.dispatch_id"),
            nullable=False,
        ),
        sa.Column(
            "plan_id", sa.String(length=64), sa.ForeignKey("action_plans.plan_id"), nullable=False
        ),
        sa.Column("connector_instance_id", sa.String(length=64), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("external_request_id", sa.String(length=128), nullable=True),
        sa.Column("error_type", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_execution_attempts_dispatch_id", "execution_attempts", ["dispatch_id"])
    op.create_index("ix_execution_attempts_plan_id", "execution_attempts", ["plan_id"])
    op.create_index("ix_execution_attempts_status", "execution_attempts", ["status"])
    op.create_index(
        "ix_execution_attempts_idempotency_key", "execution_attempts", ["idempotency_key"]
    )
    op.create_index(
        "ux_execution_attempt_connector_idempotency",
        "execution_attempts",
        ["connector_instance_id", "idempotency_key"],
        unique=True,
    )

    op.create_table(
        "connector_specs",
        sa.Column("spec_id", sa.String(length=64), primary_key=True),
        sa.Column("connector_name", sa.String(length=64), nullable=False, unique=True),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("spec_payload", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_connector_specs_connector_name", "connector_specs", ["connector_name"])

    op.create_table(
        "connector_instances",
        sa.Column("instance_id", sa.String(length=64), primary_key=True),
        sa.Column("connector_name", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("config_ref", sa.String(length=255), nullable=False),
        sa.Column("auth_ref", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_connector_instances_connector_name", "connector_instances", ["connector_name"]
    )
    op.create_index("ix_connector_instances_enabled", "connector_instances", ["enabled"])

    op.create_table(
        "connector_sync_states",
        sa.Column("state_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "instance_id",
            sa.String(length=64),
            sa.ForeignKey("connector_instances.instance_id"),
            nullable=False,
        ),
        sa.Column("stream_name", sa.String(length=128), nullable=False),
        sa.Column("cursor_payload", sa.JSON(), nullable=False),
        sa.Column("bookmark", sa.String(length=255), nullable=True),
        sa.Column("checkpoint_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_connector_sync_states_instance_id", "connector_sync_states", ["instance_id"]
    )
    op.create_index(
        "ix_connector_sync_states_stream_name", "connector_sync_states", ["stream_name"]
    )
    op.create_index(
        "ux_connector_sync_state_instance_stream",
        "connector_sync_states",
        ["instance_id", "stream_name"],
        unique=True,
    )


def downgrade() -> None:
    """Rollback async execution schema."""
    op.drop_index("ux_connector_sync_state_instance_stream", table_name="connector_sync_states")
    op.drop_index("ix_connector_sync_states_stream_name", table_name="connector_sync_states")
    op.drop_index("ix_connector_sync_states_instance_id", table_name="connector_sync_states")
    op.drop_table("connector_sync_states")

    op.drop_index("ix_connector_instances_enabled", table_name="connector_instances")
    op.drop_index("ix_connector_instances_connector_name", table_name="connector_instances")
    op.drop_table("connector_instances")

    op.drop_index("ix_connector_specs_connector_name", table_name="connector_specs")
    op.drop_table("connector_specs")

    op.drop_index("ux_execution_attempt_connector_idempotency", table_name="execution_attempts")
    op.drop_index("ix_execution_attempts_idempotency_key", table_name="execution_attempts")
    op.drop_index("ix_execution_attempts_status", table_name="execution_attempts")
    op.drop_index("ix_execution_attempts_plan_id", table_name="execution_attempts")
    op.drop_index("ix_execution_attempts_dispatch_id", table_name="execution_attempts")
    op.drop_table("execution_attempts")

    op.drop_index("ix_execution_dispatch_status_queued", table_name="execution_dispatches")
    op.drop_index("ix_execution_dispatches_status", table_name="execution_dispatches")
    op.drop_index("ix_execution_dispatches_plan_id", table_name="execution_dispatches")
    op.drop_table("execution_dispatches")

    op.drop_index("ix_action_plans_dispatch_id", table_name="action_plans")
    op.drop_index("ix_action_plans_execution_status", table_name="action_plans")
    op.drop_column("action_plans", "dispatch_id")
    op.drop_column("action_plans", "last_error")
    op.drop_column("action_plans", "current_step")
    op.drop_column("action_plans", "execution_status")
