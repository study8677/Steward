"""领域枚举定义，保证状态与类型的可审计性。"""

from __future__ import annotations

from enum import StrEnum


class SourceType(StrEnum):
    """事件来源类型。"""

    GITHUB = "github"
    EMAIL = "email"
    CHAT = "chat"
    CALENDAR = "calendar"
    SCREEN = "screen"
    LOCAL = "local"
    MANUAL = "manual"
    CUSTOM = "custom"


class SpaceState(StrEnum):
    """Context Space 生命周期状态。"""

    ACTIVE = "active"
    DORMANT = "dormant"
    PARKED = "parked"
    ARCHIVED = "archived"


class PriorityLevel(StrEnum):
    """任务优先级。"""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class RiskLevel(StrEnum):
    """风险级别。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PlanState(StrEnum):
    """执行计划状态机。"""

    NEW = "NEW"
    PLANNED = "PLANNED"
    GATED = "GATED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    CONFLICTED = "CONFLICTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class GateResult(StrEnum):
    """门禁判定结果。"""

    AUTO = "auto"
    BRIEF = "brief"
    CONFIRM = "confirm"
    BLOCKED = "blocked"


class DecisionOutcome(StrEnum):
    """决策执行结果。"""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class Reversibility(StrEnum):
    """动作可逆性分类。"""

    REVERSIBLE = "reversible"
    UNDO_WINDOW = "undo_window"
    IRREVERSIBLE = "irreversible"


class TriggerStatus(StrEnum):
    """等待触发器状态。"""

    ACTIVE = "active"
    CONSUMED = "consumed"
    EXPIRED = "expired"


class ConflictType(StrEnum):
    """冲突类型。"""

    RESOURCE = "resource"
    SEMANTIC = "semantic"


class ConflictResolution(StrEnum):
    """冲突处置策略。"""

    MERGE = "merge"
    SERIALIZE = "serialize"
    REPLAN = "replan"
    ESCALATE = "escalate"


class FeedbackType(StrEnum):
    """用户反馈类型。"""

    APPROVE = "approve"
    REJECT = "reject"
    EDIT_PRIORITY = "edit_priority"
    SNOOZE = "snooze"
    ACCEPT_INSTALL = "accept_install"
    DECLINE_INSTALL = "decline_install"
