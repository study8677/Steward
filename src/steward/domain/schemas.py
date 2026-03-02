"""Pydantic 数据模型，定义 API 输入输出与服务间契约。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from steward.domain.enums import (
    FeedbackType,
    GateResult,
    PlanState,
    Reversibility,
    RiskLevel,
    SourceType,
    SpaceState,
)


class EventIngestRequest(BaseModel):
    """手动事件写入请求。"""

    source: SourceType = SourceType.MANUAL
    source_ref: str = Field(default="manual-input")
    actor: str = Field(default="user")
    summary: str
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    raw_ref: str | None = None
    entities: list[str] = Field(default_factory=list)


class NaturalLanguageEventRequest(BaseModel):
    """自然语言事件提交请求。"""

    text: str = Field(min_length=1, max_length=1000)
    source_hint: SourceType = SourceType.MANUAL


class EventIngestResponse(BaseModel):
    """事件写入响应。"""

    event_id: str
    space_id: str
    task_id: str
    plan_id: str
    gate_result: GateResult
    dispatch_id: str | None = None
    execution_status: str | None = None


class IntegrationNlRequest(BaseModel):
    """自然语言信息源配置请求。"""

    text: str = Field(min_length=1, max_length=2000)


class IntegrationApplyResponse(BaseModel):
    """信息源配置应用响应。"""

    applied_fields: list[str] = Field(default_factory=list)
    message: str
    providers: list[dict[str, Any]] = Field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = Field(default_factory=list)
    skills: list[dict[str, Any]] = Field(default_factory=list)
    raw_parse_reason: str = ""


class IntegrationProviderResponse(BaseModel):
    """信息源接入状态响应。"""

    providers: list[dict[str, Any]] = Field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = Field(default_factory=list)
    skills: list[dict[str, Any]] = Field(default_factory=list)


class SpaceItem(BaseModel):
    """上下文空间输出模型。"""

    space_id: str
    focus_type: str
    focus_ref: str
    entity_set: list[str]
    state: SpaceState
    is_pinned: bool
    space_score: float
    updated_at: datetime


class SpacesResponse(BaseModel):
    """上下文空间列表响应。"""

    items: list[SpaceItem]


class PlanDecisionResponse(BaseModel):
    """计划确认/拒绝响应。"""

    plan_id: str
    state: PlanState
    dispatch_id: str | None = None
    execution_status: str | None = None


class RouteDecision(BaseModel):
    """路由模型输出约束。"""

    target: str = Field(pattern=r"^(SPACE_[A-Za-z0-9_-]+|NEW)$")
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class BriefSection(BaseModel):
    """简报分区结构。"""

    title: str
    items: list[str] = Field(default_factory=list)


class BriefResponse(BaseModel):
    """简报响应。"""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    markdown: str
    sections: list[BriefSection]


BriefContentLevel = Literal["simple", "medium", "rich"]


class BriefSettingsResponse(BaseModel):
    """简报偏好配置。"""

    frequency_hours: int = Field(ge=1, le=24)
    content_level: BriefContentLevel


class BriefSettingsUpdateRequest(BaseModel):
    """更新简报偏好配置请求。"""

    frequency_hours: int | None = Field(default=None, ge=1, le=24)
    content_level: BriefContentLevel | None = None


class ActionStep(BaseModel):
    """动作步骤定义。"""

    connector: str
    action_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class PlannedAction(BaseModel):
    """计划动作定义。"""

    task_id: str
    steps: list[ActionStep]
    reversibility: Reversibility
    risk_level: RiskLevel
    requires_confirmation: bool


class FeedbackRequest(BaseModel):
    """反馈写入请求。"""

    plan_id: str
    feedback_type: FeedbackType
    note: str | None = None


class FeedbackResponse(BaseModel):
    """反馈写入响应。"""

    feedback_id: str
    plan_id: str
    feedback_type: FeedbackType
