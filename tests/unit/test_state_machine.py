"""状态机规则单元测试。"""

from __future__ import annotations

from steward.domain.enums import PlanState
from steward.domain.state_machine import can_transition


def test_can_transition_from_new_to_planned() -> None:
    """NEW 应允许迁移到 PLANNED。"""
    assert can_transition(PlanState.NEW, PlanState.PLANNED)


def test_cannot_transition_from_succeeded_to_running() -> None:
    """结束态不允许回到运行态。"""
    assert not can_transition(PlanState.SUCCEEDED, PlanState.RUNNING)
