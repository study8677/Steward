"""计划确认/拒绝控制服务。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from steward.domain.enums import FeedbackType, GateResult, RiskLevel
from steward.infra.db.models import ActionPlan, TaskCandidate
from steward.learning.feedback import FeedbackLearningService
from steward.services.action_runner import ActionRunnerService
from steward.services.policy_gate import PolicyGateService


class PlanControlService:
    """处理计划人工确认与拒绝。"""

    def __init__(
        self,
        *,
        action_runner_service: ActionRunnerService,
        policy_gate_service: PolicyGateService,
        feedback_service: FeedbackLearningService,
    ) -> None:
        self._action_runner_service = action_runner_service
        self._policy_gate_service = policy_gate_service
        self._feedback_service = feedback_service

    async def confirm(self, session: AsyncSession, plan_id: str) -> ActionPlan:
        """确认计划并尝试执行。"""
        plan = await session.get(ActionPlan, plan_id)
        if plan is None:
            raise ValueError(f"Plan not found: {plan_id}")

        task = await session.get(TaskCandidate, plan.task_id)
        if task is None:
            raise ValueError(f"Task not found for plan: {plan_id}")

        gate_result, gate_reason = await self._policy_gate_service.evaluate(
            session,
            plan,
            RiskLevel(task.risk_level),
            confidence=0.99,
        )
        # 人工确认后的 gate 至少允许自动执行。
        if gate_result != GateResult.AUTO:
            gate_result = GateResult.AUTO
            gate_reason = f"manual_confirm_override:{gate_reason}"

        await self._feedback_service.record_feedback(
            session,
            plan_id=plan.plan_id,
            feedback_type=FeedbackType.APPROVE,
            note="manual_confirm",
        )
        return await self._action_runner_service.execute_with_gate(
            session, plan, gate_result, gate_reason
        )

    async def reject(self, session: AsyncSession, plan_id: str) -> ActionPlan:
        """拒绝计划。"""
        plan = await session.get(ActionPlan, plan_id)
        if plan is None:
            raise ValueError(f"Plan not found: {plan_id}")

        await self._feedback_service.record_feedback(
            session,
            plan_id=plan.plan_id,
            feedback_type=FeedbackType.REJECT,
            note="manual_reject",
        )
        return await self._action_runner_service.reject_plan(session, plan, "manual_reject")
