"""执行状态机规则定义。"""

from __future__ import annotations

from steward.domain.enums import PlanState

ALLOWED_TRANSITIONS: dict[PlanState, set[PlanState]] = {
    PlanState.NEW: {PlanState.PLANNED},
    PlanState.PLANNED: {PlanState.GATED, PlanState.CONFLICTED, PlanState.FAILED},
    PlanState.GATED: {
        PlanState.RUNNING,
        PlanState.WAITING,
        PlanState.CONFLICTED,
        PlanState.FAILED,
    },
    PlanState.RUNNING: {
        PlanState.WAITING,
        PlanState.CONFLICTED,
        PlanState.SUCCEEDED,
        PlanState.FAILED,
        PlanState.ROLLED_BACK,
    },
    PlanState.WAITING: {PlanState.GATED, PlanState.RUNNING, PlanState.FAILED},
    PlanState.CONFLICTED: {PlanState.GATED, PlanState.FAILED},
    PlanState.SUCCEEDED: set(),
    PlanState.FAILED: set(),
    PlanState.ROLLED_BACK: set(),
}


def can_transition(current: PlanState, target: PlanState) -> bool:
    """检查状态迁移是否允许。"""
    return target in ALLOWED_TRANSITIONS[current]
