"""Policy Gate 单元测试。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from steward.core.config import Settings
from steward.core.policy import PolicyLoader
from steward.domain.enums import Reversibility, RiskLevel
from steward.infra.db.models import ActionPlan
from steward.services.policy_gate import PolicyGateService


@dataclass(slots=True)
class _ScalarResult:
    """模拟 SQLAlchemy scalar 结果。"""

    value: int

    def scalar_one(self) -> int:
        """返回单个标量值。"""
        return self.value


class FakeSession:
    """最小可用会话模拟。"""

    def __init__(self, count: int) -> None:
        self._count = count

    async def execute(self, _statement):  # noqa: ANN001
        """忽略 SQL 并返回预设计数。"""
        return _ScalarResult(self._count)


@pytest.mark.asyncio()
async def test_irreversible_requires_confirm(tmp_path: Path) -> None:
    """不可逆动作必须人工确认。"""
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text("risk: {high_risk_confidence_threshold: 0.92}\n", encoding="utf-8")

    settings = Settings(policy_file=str(policy_file))
    service = PolicyGateService(settings, PolicyLoader(policy_file))

    plan = ActionPlan(
        task_id="task-1",
        reversibility=Reversibility.IRREVERSIBLE.value,
        steps=[],
        rollback=[],
    )
    gate_result, reason = await service.evaluate(FakeSession(0), plan, RiskLevel.HIGH, 0.99)

    assert gate_result.value == "confirm"
    assert "irreversible" in reason


@pytest.mark.asyncio()
async def test_budget_exhausted_moves_to_brief(tmp_path: Path) -> None:
    """打扰预算耗尽时应进入简报。"""
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text("risk: {high_risk_confidence_threshold: 0.92}\n", encoding="utf-8")

    settings = Settings(interruption_budget_per_day=1, policy_file=str(policy_file))
    service = PolicyGateService(settings, PolicyLoader(policy_file))

    plan = ActionPlan(
        task_id="task-1",
        reversibility=Reversibility.REVERSIBLE.value,
        steps=[],
        rollback=[],
    )
    gate_result, _reason = await service.evaluate(FakeSession(3), plan, RiskLevel.LOW, 0.95)

    assert gate_result.value == "brief"
