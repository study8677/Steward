"""Policy Gate 服务：基于风险、预算和可逆性做执行判定。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from steward.core.config import Settings
from steward.core.policy import PolicyLoader
from steward.domain.enums import GateResult, Reversibility, RiskLevel
from steward.infra.db.models import ActionPlan, DecisionLog


class PolicyGateService:
    """执行门禁判定器。"""

    def __init__(self, settings: Settings, policy_loader: PolicyLoader) -> None:
        self._settings = settings
        self._policy_loader = policy_loader

    async def evaluate(
        self,
        session: Any,
        plan: ActionPlan,
        risk_level: RiskLevel,
        confidence: float,
    ) -> tuple[GateResult, str]:
        """返回 gate_result 与原因。"""
        policy = self._policy_loader.load()
        risk_policy = policy.get("risk", {})
        threshold = float(risk_policy.get("high_risk_confidence_threshold", 0.92))
        high_risk_auto_enabled = bool(risk_policy.get("high_risk_auto_enabled", True))

        if plan.reversibility == Reversibility.IRREVERSIBLE.value:
            return GateResult.CONFIRM, "irreversible_requires_manual_confirmation"

        if risk_level == RiskLevel.HIGH and not high_risk_auto_enabled:
            return GateResult.CONFIRM, "high_risk_auto_disabled"

        if risk_level == RiskLevel.HIGH and confidence < threshold:
            return GateResult.CONFIRM, "high_risk_confidence_below_threshold"

        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        today_count_stmt = (
            select(func.count())
            .select_from(DecisionLog)
            .where(
                DecisionLog.created_at >= today_start,
                DecisionLog.gate_result.in_([GateResult.CONFIRM.value, GateResult.BRIEF.value]),
            )
        )
        today_count = int((await session.execute(today_count_stmt)).scalar_one())
        if today_count >= self._settings.interruption_budget_per_day:
            return GateResult.BRIEF, "interruption_budget_exhausted"

        if risk_level == RiskLevel.MEDIUM:
            return GateResult.BRIEF, "medium_risk_default_to_brief"

        return GateResult.AUTO, "low_risk_auto_execute"
