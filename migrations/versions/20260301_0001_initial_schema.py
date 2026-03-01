"""initial schema"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260301_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建初始数据表与索引。"""
    op.create_table(
        "context_events",
        sa.Column("event_id", sa.String(length=64), primary_key=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("raw_ref", sa.String(length=1024), nullable=True),
        sa.Column("entity_set", sa.JSON(), nullable=False),
        sa.Column("dedup_key", sa.String(length=255), nullable=True),
        sa.Column("match_key", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_context_events_source", "context_events", ["source"])
    op.create_index("ix_context_events_occurred_at", "context_events", ["occurred_at"])
    op.create_index("ix_context_events_dedup_key", "context_events", ["dedup_key"])
    op.create_index("ix_context_events_match_key", "context_events", ["match_key"])
    op.create_index("ix_event_source_occurred", "context_events", ["source", "occurred_at"])

    op.create_table(
        "context_spaces",
        sa.Column("space_id", sa.String(length=64), primary_key=True),
        sa.Column("focus_type", sa.String(length=32), nullable=False),
        sa.Column("focus_ref", sa.String(length=255), nullable=False),
        sa.Column("entity_set", sa.JSON(), nullable=False),
        sa.Column("evidence_events", sa.JSON(), nullable=False),
        sa.Column("space_score", sa.Float(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("is_pinned", sa.Boolean(), nullable=False),
        sa.Column("pin_reason", sa.String(length=128), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("open_commitments_count", sa.Integer(), nullable=False),
        sa.Column("last_reactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_context_spaces_state", "context_spaces", ["state"])
    op.create_index("ix_context_spaces_is_pinned", "context_spaces", ["is_pinned"])
    op.create_index("ix_space_state_updated", "context_spaces", ["state", "updated_at"])

    op.create_table(
        "task_candidates",
        sa.Column("task_id", sa.String(length=64), primary_key=True),
        sa.Column("derived_from", sa.String(length=64), nullable=False),
        sa.Column("intent", sa.String(length=128), nullable=False),
        sa.Column("priority", sa.String(length=8), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("impact_score", sa.Integer(), nullable=False),
        sa.Column("urgency_score", sa.Integer(), nullable=False),
        sa.Column("blocking_on", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_task_candidates_derived_from", "task_candidates", ["derived_from"])
    op.create_index("ix_task_candidates_priority", "task_candidates", ["priority"])

    op.create_table(
        "action_plans",
        sa.Column("plan_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "task_id",
            sa.String(length=64),
            sa.ForeignKey("task_candidates.task_id"),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("rollback", sa.JSON(), nullable=False),
        sa.Column("reversibility", sa.String(length=16), nullable=False),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False),
        sa.Column("wait_condition", sa.String(length=255), nullable=True),
        sa.Column("resume_trigger", sa.String(length=255), nullable=True),
        sa.Column("wait_timeout_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("on_wait_timeout", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_action_plans_task_id", "action_plans", ["task_id"])
    op.create_index("ix_action_plans_state", "action_plans", ["state"])
    op.create_index("ix_action_plans_wait_timeout_at", "action_plans", ["wait_timeout_at"])
    op.create_index("ix_plan_waiting_timeout", "action_plans", ["state", "wait_timeout_at"])

    op.create_table(
        "decision_logs",
        sa.Column("decision_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "plan_id", sa.String(length=64), sa.ForeignKey("action_plans.plan_id"), nullable=False
        ),
        sa.Column("gate_result", sa.String(length=16), nullable=False),
        sa.Column("state_from", sa.String(length=32), nullable=False),
        sa.Column("state_to", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_decision_logs_plan_id", "decision_logs", ["plan_id"])
    op.create_index("ix_decision_logs_gate_result", "decision_logs", ["gate_result"])

    op.create_table(
        "waiting_triggers",
        sa.Column("trigger_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "plan_id", sa.String(length=64), sa.ForeignKey("action_plans.plan_id"), nullable=False
        ),
        sa.Column("match_key", sa.String(length=255), nullable=False),
        sa.Column("trigger_status", sa.String(length=16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_waiting_triggers_plan_id", "waiting_triggers", ["plan_id"])
    op.create_index("ix_waiting_triggers_match_key", "waiting_triggers", ["match_key"])
    op.create_index("ix_waiting_triggers_trigger_status", "waiting_triggers", ["trigger_status"])
    op.create_index("ix_waiting_match_state", "waiting_triggers", ["match_key", "trigger_status"])

    op.create_table(
        "feedback_events",
        sa.Column("feedback_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "decision_id",
            sa.String(length=64),
            sa.ForeignKey("decision_logs.decision_id"),
            nullable=True,
        ),
        sa.Column(
            "plan_id", sa.String(length=64), sa.ForeignKey("action_plans.plan_id"), nullable=False
        ),
        sa.Column("feedback_type", sa.String(length=32), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_feedback_events_plan_id", "feedback_events", ["plan_id"])

    op.create_table(
        "user_preference_profiles",
        sa.Column("user_id", sa.String(length=64), primary_key=True),
        sa.Column("interruption_budget_target", sa.Integer(), nullable=False),
        sa.Column("interruption_budget_floor", sa.Integer(), nullable=False),
        sa.Column("interruption_budget_ceiling", sa.Integer(), nullable=False),
        sa.Column("priority_profile", sa.JSON(), nullable=False),
        sa.Column("autonomy_profile", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "metric_snapshots",
        sa.Column("metric_id", sa.String(length=64), primary_key=True),
        sa.Column("metric_name", sa.String(length=128), nullable=False),
        sa.Column("metric_labels", sa.JSON(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("window", sa.String(length=8), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_metric_snapshots_metric_name", "metric_snapshots", ["metric_name"])

    op.create_table(
        "alert_events",
        sa.Column("alert_id", sa.String(length=64), primary_key=True),
        sa.Column("alert_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("trigger_value", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_alert_events_alert_type", "alert_events", ["alert_type"])
    op.create_index("ix_alert_events_status", "alert_events", ["status"])

    op.create_table(
        "plan_effects",
        sa.Column("effect_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "plan_id", sa.String(length=64), sa.ForeignKey("action_plans.plan_id"), nullable=False
        ),
        sa.Column("resource_key", sa.String(length=255), nullable=False),
        sa.Column("operation", sa.String(length=255), nullable=False),
        sa.Column("expected_version", sa.String(length=128), nullable=True),
        sa.Column("reversibility", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_plan_effects_plan_id", "plan_effects", ["plan_id"])
    op.create_index("ix_plan_effects_resource_key", "plan_effects", ["resource_key"])

    op.create_table(
        "conflict_cases",
        sa.Column("conflict_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "plan_a_id", sa.String(length=64), sa.ForeignKey("action_plans.plan_id"), nullable=False
        ),
        sa.Column(
            "plan_b_id", sa.String(length=64), sa.ForeignKey("action_plans.plan_id"), nullable=False
        ),
        sa.Column("conflict_type", sa.String(length=16), nullable=False),
        sa.Column("resolution", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("resolved_by", sa.String(length=16), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_conflict_cases_plan_a_id", "conflict_cases", ["plan_a_id"])
    op.create_index("ix_conflict_cases_plan_b_id", "conflict_cases", ["plan_b_id"])
    op.create_index("ix_conflict_cases_status", "conflict_cases", ["status"])


def downgrade() -> None:
    """删除初始数据表与索引。"""
    op.drop_table("conflict_cases")
    op.drop_table("plan_effects")
    op.drop_table("alert_events")
    op.drop_table("metric_snapshots")
    op.drop_table("user_preference_profiles")
    op.drop_table("feedback_events")
    op.drop_table("waiting_triggers")
    op.drop_table("decision_logs")
    op.drop_table("action_plans")
    op.drop_table("task_candidates")
    op.drop_table("context_spaces")
    op.drop_table("context_events")
