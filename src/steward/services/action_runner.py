"""Action Runner 服务：执行计划步骤并落盘状态。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from steward.connectors.registry import ConnectorRegistry
from steward.domain.enums import DecisionOutcome, GateResult, PlanState, TriggerStatus
from steward.domain.state_machine import can_transition
from steward.infra.db.models import ActionPlan, WaitingTrigger
from steward.observability.metrics import ACTION_EXECUTION_TOTAL
from steward.services.decision_log import DecisionLogService
from steward.services.verifier import VerifierService


class ActionRunnerService:
    """计划执行器。"""

    def __init__(
        self,
        connector_registry: ConnectorRegistry,
        verifier_service: VerifierService,
        decision_log_service: DecisionLogService,
    ) -> None:
        self._connector_registry = connector_registry
        self._verifier_service = verifier_service
        self._decision_log_service = decision_log_service

    async def execute_with_gate(
        self,
        session: AsyncSession,
        plan: ActionPlan,
        gate_result: GateResult,
        gate_reason: str,
    ) -> ActionPlan:
        """根据 gate_result 执行或等待人工确认。"""
        original_state = plan.state
        if can_transition(PlanState(plan.state), PlanState.GATED):
            plan.state = PlanState.GATED.value

        await self._decision_log_service.append(
            session,
            plan_id=plan.plan_id,
            gate_result=gate_result,
            state_from=original_state,
            state_to=plan.state,
            reason=gate_reason,
            outcome=DecisionOutcome.SUCCEEDED,
        )

        if gate_result != GateResult.AUTO:
            return plan

        if can_transition(PlanState(plan.state), PlanState.RUNNING):
            plan.state = PlanState.RUNNING.value

        results = []
        for step in plan.steps:
            connector_name = str(step.get("connector", "manual"))
            connector = self._connector_registry.get(connector_name)
            result = await connector.execute(step)
            results.append(result)

        verified, detail = self._verifier_service.verify(results)
        if not verified:
            if can_transition(PlanState(plan.state), PlanState.FAILED):
                plan.state = PlanState.FAILED.value
            ACTION_EXECUTION_TOTAL.labels(outcome="failed").inc()
            await self._decision_log_service.append(
                session,
                plan_id=plan.plan_id,
                gate_result=GateResult.AUTO,
                state_from=PlanState.RUNNING.value,
                state_to=plan.state,
                reason=detail,
                outcome=DecisionOutcome.FAILED,
            )
            return plan

        if plan.wait_condition:
            if can_transition(PlanState(plan.state), PlanState.WAITING):
                plan.state = PlanState.WAITING.value
            trigger = WaitingTrigger(
                plan_id=plan.plan_id,
                match_key=plan.resume_trigger or f"plan:{plan.plan_id}:resume",
                trigger_status=TriggerStatus.ACTIVE.value,
                expires_at=plan.wait_timeout_at,
            )
            session.add(trigger)
            ACTION_EXECUTION_TOTAL.labels(outcome="waiting").inc()
            await self._decision_log_service.append(
                session,
                plan_id=plan.plan_id,
                gate_result=GateResult.AUTO,
                state_from=PlanState.RUNNING.value,
                state_to=plan.state,
                reason="wait_condition_registered",
                outcome=DecisionOutcome.SUCCEEDED,
            )
            return plan

        if can_transition(PlanState(plan.state), PlanState.SUCCEEDED):
            plan.state = PlanState.SUCCEEDED.value
        ACTION_EXECUTION_TOTAL.labels(outcome="succeeded").inc()
        await self._decision_log_service.append(
            session,
            plan_id=plan.plan_id,
            gate_result=GateResult.AUTO,
            state_from=PlanState.RUNNING.value,
            state_to=plan.state,
            reason="auto_execution_completed",
            outcome=DecisionOutcome.SUCCEEDED,
        )
        return plan

    async def reject_plan(self, session: AsyncSession, plan: ActionPlan, reason: str) -> ActionPlan:
        """拒绝计划并置为 FAILED。"""
        state_from = plan.state
        if plan.state in {PlanState.GATED.value, PlanState.CONFLICTED.value}:
            plan.state = PlanState.FAILED.value
        await self._decision_log_service.append(
            session,
            plan_id=plan.plan_id,
            gate_result=GateResult.BLOCKED,
            state_from=state_from,
            state_to=plan.state,
            reason=reason,
            outcome=DecisionOutcome.FAILED,
        )
        return plan

    async def mark_wait_timeout(self, session: AsyncSession, plan: ActionPlan) -> ActionPlan:
        """处理 WAITING 超时并回到 GATED。"""
        if plan.state == PlanState.WAITING.value and can_transition(
            PlanState.WAITING, PlanState.GATED
        ):
            plan.state = PlanState.GATED.value
            await self._decision_log_service.append(
                session,
                plan_id=plan.plan_id,
                gate_result=GateResult.BRIEF,
                state_from=PlanState.WAITING.value,
                state_to=PlanState.GATED.value,
                reason="wait_timeout_triggered",
                outcome=DecisionOutcome.SUCCEEDED,
            )
        return plan

    async def resume_waiting_plan(self, session: AsyncSession, plan: ActionPlan) -> ActionPlan:
        """事件命中后恢复 WAITING 计划到 GATED。"""
        if plan.state == PlanState.WAITING.value and can_transition(
            PlanState.WAITING, PlanState.GATED
        ):
            plan.state = PlanState.GATED.value
            plan.wait_timeout_at = datetime.now(UTC)
            await self._decision_log_service.append(
                session,
                plan_id=plan.plan_id,
                gate_result=GateResult.AUTO,
                state_from=PlanState.WAITING.value,
                state_to=PlanState.GATED.value,
                reason="resume_trigger_matched",
                outcome=DecisionOutcome.SUCCEEDED,
            )
        return plan
