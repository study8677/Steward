"""Steward 核心数据模型定义。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from steward.domain.enums import (
    ConflictResolution,
    ConflictType,
    DecisionOutcome,
    FeedbackType,
    GateResult,
    PlanState,
    PriorityLevel,
    Reversibility,
    RiskLevel,
    SourceType,
    SpaceState,
    TriggerStatus,
)
from steward.infra.db.base import Base, TimestampMixin


def _uuid() -> str:
    """生成字符串 UUID。"""
    return str(uuid4())


class ContextEvent(Base, TimestampMixin):
    """事件事实表。"""

    __tablename__ = "context_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    source: Mapped[str] = mapped_column(String(32), default=SourceType.MANUAL.value, index=True)
    source_ref: Mapped[str] = mapped_column(String(255), default="")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )
    actor: Mapped[str] = mapped_column(String(128), default="system")
    summary: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    raw_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    entity_set: Mapped[list[str]] = mapped_column(JSON, default=list)
    dedup_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    match_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)


class ContextSpace(Base, TimestampMixin):
    """上下文空间表。"""

    __tablename__ = "context_spaces"

    space_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    focus_type: Mapped[str] = mapped_column(String(32), default="project")
    focus_ref: Mapped[str] = mapped_column(String(255), default="")
    entity_set: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_events: Mapped[list[str]] = mapped_column(JSON, default=list)
    space_score: Mapped[float] = mapped_column(Float, default=0.0)
    state: Mapped[str] = mapped_column(String(32), default=SpaceState.ACTIVE.value, index=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    pin_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    open_commitments_count: Mapped[int] = mapped_column(Integer, default=0)
    last_reactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TaskCandidate(Base, TimestampMixin):
    """候选任务表。"""

    __tablename__ = "task_candidates"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    derived_from: Mapped[str] = mapped_column(String(64), index=True)
    intent: Mapped[str] = mapped_column(String(128), default="follow_up")
    priority: Mapped[str] = mapped_column(String(8), default=PriorityLevel.P2.value, index=True)
    risk_level: Mapped[str] = mapped_column(String(16), default=RiskLevel.LOW.value)
    impact_score: Mapped[int] = mapped_column(Integer, default=0)
    urgency_score: Mapped[int] = mapped_column(Integer, default=0)
    blocking_on: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ActionPlan(Base, TimestampMixin):
    """执行计划主表。"""

    __tablename__ = "action_plans"

    plan_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("task_candidates.task_id"), index=True
    )
    state: Mapped[str] = mapped_column(String(32), default=PlanState.NEW.value, index=True)
    steps: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    rollback: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    reversibility: Mapped[str] = mapped_column(String(16), default=Reversibility.REVERSIBLE.value)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    wait_condition: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resume_trigger: Mapped[str | None] = mapped_column(String(255), nullable=True)
    wait_timeout_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    on_wait_timeout: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    execution_status: Mapped[str] = mapped_column(String(32), default="idle", index=True)
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    dispatch_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class DecisionLog(Base, TimestampMixin):
    """执行决策审计表。"""

    __tablename__ = "decision_logs"

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    plan_id: Mapped[str] = mapped_column(String(64), ForeignKey("action_plans.plan_id"), index=True)
    gate_result: Mapped[str] = mapped_column(String(16), default=GateResult.BRIEF.value, index=True)
    state_from: Mapped[str] = mapped_column(String(32), default=PlanState.NEW.value)
    state_to: Mapped[str] = mapped_column(String(32), default=PlanState.NEW.value)
    reason: Mapped[str] = mapped_column(Text, default="")
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    outcome: Mapped[str] = mapped_column(String(16), default=DecisionOutcome.SUCCEEDED.value)


class ExecutionDispatch(Base, TimestampMixin):
    """异步执行分发记录。"""

    __tablename__ = "execution_dispatches"

    dispatch_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    plan_id: Mapped[str] = mapped_column(String(64), ForeignKey("action_plans.plan_id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    trigger_reason: Mapped[str] = mapped_column(String(128), default="")
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)


class ExecutionAttempt(Base, TimestampMixin):
    """异步执行步骤尝试记录。"""

    __tablename__ = "execution_attempts"

    attempt_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    dispatch_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("execution_dispatches.dispatch_id"), index=True
    )
    plan_id: Mapped[str] = mapped_column(String(64), ForeignKey("action_plans.plan_id"), index=True)
    connector_instance_id: Mapped[str] = mapped_column(String(64), default="")
    step_index: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    external_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, default=True)


class ConnectorSpec(Base, TimestampMixin):
    """Connector 声明式规格。"""

    __tablename__ = "connector_specs"

    spec_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    connector_name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    version: Mapped[str] = mapped_column(String(32), default="v1")
    spec_payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(128), default="repo")


class ConnectorInstance(Base, TimestampMixin):
    """Connector 运行实例。"""

    __tablename__ = "connector_instances"

    instance_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    connector_name: Mapped[str] = mapped_column(String(64), index=True)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    config_ref: Mapped[str] = mapped_column(String(255), default="")
    auth_ref: Mapped[str] = mapped_column(String(255), default="")


class ConnectorSyncState(Base, TimestampMixin):
    """Connector 增量同步游标状态。"""

    __tablename__ = "connector_sync_states"

    state_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    instance_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("connector_instances.instance_id"), index=True
    )
    stream_name: Mapped[str] = mapped_column(String(128), index=True)
    cursor_payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    bookmark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    checkpoint_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WaitingTrigger(Base, TimestampMixin):
    """等待触发器表。"""

    __tablename__ = "waiting_triggers"

    trigger_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    plan_id: Mapped[str] = mapped_column(String(64), ForeignKey("action_plans.plan_id"), index=True)
    match_key: Mapped[str] = mapped_column(String(255), index=True)
    trigger_status: Mapped[str] = mapped_column(
        String(16), default=TriggerStatus.ACTIVE.value, index=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FeedbackEvent(Base, TimestampMixin):
    """用户反馈表。"""

    __tablename__ = "feedback_events"

    feedback_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    decision_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("decision_logs.decision_id"), nullable=True
    )
    plan_id: Mapped[str] = mapped_column(String(64), ForeignKey("action_plans.plan_id"), index=True)
    feedback_type: Mapped[str] = mapped_column(String(32), default=FeedbackType.APPROVE.value)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class UserPreferenceProfile(Base, TimestampMixin):
    """用户偏好画像表。"""

    __tablename__ = "user_preference_profiles"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    interruption_budget_target: Mapped[int] = mapped_column(Integer, default=10)
    interruption_budget_floor: Mapped[int] = mapped_column(Integer, default=6)
    interruption_budget_ceiling: Mapped[int] = mapped_column(Integer, default=16)
    priority_profile: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    autonomy_profile: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class MetricSnapshot(Base):
    """指标快照表。"""

    __tablename__ = "metric_snapshots"

    metric_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    metric_name: Mapped[str] = mapped_column(String(128), index=True)
    metric_labels: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    value: Mapped[float] = mapped_column(Float)
    window: Mapped[str] = mapped_column(String(8), default="1m")
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class AlertEvent(Base):
    """告警事件表。"""

    __tablename__ = "alert_events"

    alert_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    alert_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="info")
    status: Mapped[str] = mapped_column(String(16), default="firing", index=True)
    trigger_value: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PlanEffect(Base, TimestampMixin):
    """计划影响资源表，用于冲突检测。"""

    __tablename__ = "plan_effects"

    effect_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    plan_id: Mapped[str] = mapped_column(String(64), ForeignKey("action_plans.plan_id"), index=True)
    resource_key: Mapped[str] = mapped_column(String(255), index=True)
    operation: Mapped[str] = mapped_column(String(255))
    expected_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reversibility: Mapped[str] = mapped_column(String(16), default=Reversibility.REVERSIBLE.value)


class ConflictCase(Base, TimestampMixin):
    """冲突工单表。"""

    __tablename__ = "conflict_cases"

    conflict_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    plan_a_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("action_plans.plan_id"), index=True
    )
    plan_b_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("action_plans.plan_id"), index=True
    )
    conflict_type: Mapped[str] = mapped_column(String(16), default=ConflictType.RESOURCE.value)
    resolution: Mapped[str] = mapped_column(String(16), default=ConflictResolution.SERIALIZE.value)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    resolved_by: Mapped[str | None] = mapped_column(String(16), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


Index("ix_waiting_match_state", WaitingTrigger.match_key, WaitingTrigger.trigger_status)
Index("ix_plan_waiting_timeout", ActionPlan.state, ActionPlan.wait_timeout_at)
Index("ix_event_source_occurred", ContextEvent.source, ContextEvent.occurred_at)
Index("ix_space_state_updated", ContextSpace.state, ContextSpace.updated_at)
Index("ix_execution_dispatch_status_queued", ExecutionDispatch.status, ExecutionDispatch.queued_at)
Index(
    "ux_execution_attempt_connector_idempotency",
    ExecutionAttempt.connector_instance_id,
    ExecutionAttempt.idempotency_key,
    unique=True,
)
Index(
    "ux_connector_sync_state_instance_stream",
    ConnectorSyncState.instance_id,
    ConnectorSyncState.stream_name,
    unique=True,
)
