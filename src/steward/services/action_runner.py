"""Action Runner 服务：编排门禁结果并分发异步执行。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from steward.connectors.registry import ConnectorRegistry
from steward.domain.enums import DecisionOutcome, GateResult, PlanState
from steward.domain.state_machine import can_transition
from steward.infra.db.models import ActionPlan
from steward.observability.metrics import ACTION_EXECUTION_TOTAL
from steward.runtime.execution.dispatcher import ExecutionDispatcher
from steward.services.decision_log import DecisionLogService


class ActionRunnerService:
    """计划执行编排器。"""

    def __init__(
        self,
        connector_registry: ConnectorRegistry,
        decision_log_service: DecisionLogService,
        execution_dispatcher: ExecutionDispatcher,
        execution_enabled: bool = True,
    ) -> None:
        self._connector_registry = connector_registry
        self._decision_log_service = decision_log_service
        self._execution_dispatcher = execution_dispatcher
        self._execution_enabled = execution_enabled

    async def execute_with_gate(
        self,
        session: AsyncSession,
        plan: ActionPlan,
        gate_result: GateResult,
        gate_reason: str,
    ) -> ActionPlan:
        """根据 gate_result 分发执行或等待人工确认。"""
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
            if gate_result == GateResult.BLOCKED:
                plan.execution_status = "failed"
                plan.last_error = gate_reason
                if can_transition(PlanState(plan.state), PlanState.FAILED):
                    plan.state = PlanState.FAILED.value
            else:
                plan.execution_status = "pending_confirmation"
            return plan

        if not self._execution_enabled:
            plan.execution_status = "disabled"
            plan.last_error = "execution_engine_disabled"
            if can_transition(PlanState(plan.state), PlanState.FAILED):
                plan.state = PlanState.FAILED.value
            ACTION_EXECUTION_TOTAL.labels(outcome="failed").inc()
            return plan

        if not plan.steps:
            plan.execution_status = "failed"
            plan.last_error = "plan_has_no_executable_steps"
            if can_transition(PlanState(plan.state), PlanState.FAILED):
                plan.state = PlanState.FAILED.value
            ACTION_EXECUTION_TOTAL.labels(outcome="failed").inc()
            await self._decision_log_service.append(
                session,
                plan_id=plan.plan_id,
                gate_result=GateResult.BLOCKED,
                state_from=PlanState.GATED.value,
                state_to=plan.state,
                reason=plan.last_error,
                outcome=DecisionOutcome.FAILED,
            )
            return plan

        for index, step in enumerate(plan.steps):
            connector_name = str(step.get("connector", "")).strip().lower()
            action_type = str(step.get("action_type", "")).strip()
            payload = step.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}

            is_valid, reason = self._connector_registry.validate_action(
                connector=connector_name,
                action_type=action_type,
                payload=payload,
            )
            if not is_valid:
                plan.execution_status = "failed"
                plan.last_error = f"step_{index}_invalid:{reason}"
                if can_transition(PlanState(plan.state), PlanState.FAILED):
                    plan.state = PlanState.FAILED.value
                ACTION_EXECUTION_TOTAL.labels(outcome="failed").inc()
                await self._decision_log_service.append(
                    session,
                    plan_id=plan.plan_id,
                    gate_result=GateResult.BLOCKED,
                    state_from=PlanState.GATED.value,
                    state_to=plan.state,
                    reason=plan.last_error,
                    outcome=DecisionOutcome.FAILED,
                )
                return plan

        dispatch = await self._execution_dispatcher.dispatch_plan(
            session,
            plan=plan,
            trigger_reason=gate_reason,
        )
        plan.execution_status = dispatch.status
        ACTION_EXECUTION_TOTAL.labels(
            outcome="queued" if dispatch.status == "queued" else "failed"
        ).inc()
        await self._decision_log_service.append(
            session,
            plan_id=plan.plan_id,
            gate_result=GateResult.AUTO,
            state_from=PlanState.GATED.value,
            state_to=plan.state,
            reason=f"auto_execution_dispatched:{dispatch.dispatch_id}",
            outcome=DecisionOutcome.SUCCEEDED
            if dispatch.status == "queued"
            else DecisionOutcome.FAILED,
        )
        return plan

    async def reject_plan(self, session: AsyncSession, plan: ActionPlan, reason: str) -> ActionPlan:
        """拒绝计划并置为 FAILED。"""
        state_from = plan.state
        if plan.state in {
            PlanState.GATED.value,
            PlanState.CONFLICTED.value,
            PlanState.PLANNED.value,
        }:
            plan.state = PlanState.FAILED.value
        plan.execution_status = "rejected"
        plan.last_error = reason
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
            plan.execution_status = "pending_confirmation"
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
            plan.execution_status = "queued"
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
