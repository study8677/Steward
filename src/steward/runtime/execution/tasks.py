"""Celery tasks for asynchronous plan execution."""

from __future__ import annotations

import asyncio
from time import perf_counter

from steward.core.config import Settings, get_settings
from steward.core.logging import configure_logging, get_logger
from steward.core.model_config import enforce_model_config
from steward.domain.enums import DecisionOutcome, GateResult, PlanState
from steward.domain.state_machine import can_transition
from steward.infra.db.models import ActionPlan, ExecutionDispatch, TaskCandidate
from steward.infra.db.session import db
from steward.runtime.execution.attempt_store import AttemptStore
from steward.runtime.execution.celery_app import celery_app
from steward.services.container import ServiceContainer, build_service_container

logger = get_logger(component="execution_tasks")

_runtime: ServiceContainer | None = None
_runtime_settings: Settings | None = None


def _get_runtime() -> tuple[Settings, ServiceContainer]:
    global _runtime, _runtime_settings
    settings = get_settings()
    enforce_model_config(settings)
    configure_logging(settings.log_level)

    if (
        _runtime is not None
        and _runtime_settings is not None
        and _runtime_settings.database_url == settings.database_url
    ):
        return settings, _runtime

    db.configure(settings.database_url)
    _runtime = build_service_container(settings)
    _runtime_settings = settings
    return settings, _runtime


async def _run_dispatch_async(dispatch_id: str) -> None:
    settings, services = _get_runtime()
    attempt_store = AttemptStore()

    async with db.session_factory() as session:
        dispatch = await session.get(ExecutionDispatch, dispatch_id)
        if dispatch is None:
            logger.warning("dispatch_not_found", dispatch_id=dispatch_id)
            return

        plan = await session.get(ActionPlan, dispatch.plan_id)
        if plan is None:
            dispatch.status = "failed"
            await session.commit()
            logger.warning("plan_not_found_for_dispatch", dispatch_id=dispatch_id)
            return
        task = await session.get(TaskCandidate, plan.task_id)
        intent = task.intent if task is not None else "follow_up"

        await attempt_store.mark_dispatch_started(session, dispatch)
        plan.execution_status = "running"
        plan.last_error = None
        if can_transition(PlanState(plan.state), PlanState.RUNNING):
            plan.state = PlanState.RUNNING.value
        await session.flush()

        # =====================================================================
        # 唯一执行路径：ExecutionAgent（LiteLLM + Tool Calling ReAct Loop）
        # =====================================================================
        started = perf_counter()
        try:
            # 从 plan steps 中提取上下文信息
            extra_context = ""
            if plan.steps:
                step0 = plan.steps[0] if isinstance(plan.steps[0], dict) else {}
                payload = step0.get("payload", {})
                if isinstance(payload, dict):
                    event_summary = str(payload.get("event_summary", ""))
                    source_ref = str(payload.get("source_ref", ""))
                    source = str(payload.get("source", ""))
                    extra_context = f"来源: {source}, 引用: {source_ref}" if source else ""
                else:
                    event_summary = ""
            else:
                event_summary = ""

            agent_result = await services.execution_agent.execute(
                intent=intent,
                event_summary=event_summary or f"Plan {plan.plan_id[:8]} — {intent}",
                plan_id=plan.plan_id,
                extra_context=extra_context,
            )
            duration_ms = int((perf_counter() - started) * 1000)

            if agent_result.success:
                plan.current_step = len(plan.steps)
                if can_transition(PlanState(plan.state), PlanState.SUCCEEDED):
                    plan.state = PlanState.SUCCEEDED.value
                plan.execution_status = "succeeded"
                plan.last_error = None
                await attempt_store.mark_dispatch_finished(session, dispatch, status="succeeded")
                await services.decision_log_service.append(
                    session,
                    plan_id=plan.plan_id,
                    gate_result=GateResult.AUTO,
                    state_from=PlanState.RUNNING.value,
                    state_to=plan.state,
                    reason=f"agent_completed:{agent_result.summary[:120]}",
                    outcome=DecisionOutcome.SUCCEEDED,
                )
                logger.info(
                    "agent_execution_succeeded",
                    plan_id=plan.plan_id,
                    turns_used=agent_result.turns_used,
                    duration_ms=duration_ms,
                    summary=agent_result.summary[:100],
                )
            else:
                plan.execution_status = "failed"
                plan.last_error = f"agent_failed:{agent_result.summary[:200]}"
                if can_transition(PlanState(plan.state), PlanState.FAILED):
                    plan.state = PlanState.FAILED.value
                await attempt_store.mark_dispatch_finished(session, dispatch, status="failed")
                await services.decision_log_service.append(
                    session,
                    plan_id=plan.plan_id,
                    gate_result=GateResult.AUTO,
                    state_from=PlanState.RUNNING.value,
                    state_to=plan.state,
                    reason=plan.last_error,
                    outcome=DecisionOutcome.FAILED,
                )
                logger.warning(
                    "agent_execution_failed",
                    plan_id=plan.plan_id,
                    duration_ms=duration_ms,
                    error=agent_result.summary[:200],
                )

        except Exception as exc:  # noqa: BLE001
            duration_ms = int((perf_counter() - started) * 1000)
            plan.execution_status = "failed"
            plan.last_error = f"agent_exception:{type(exc).__name__}:{str(exc)[:200]}"
            if can_transition(PlanState(plan.state), PlanState.FAILED):
                plan.state = PlanState.FAILED.value
            await attempt_store.mark_dispatch_finished(session, dispatch, status="failed")
            await services.decision_log_service.append(
                session,
                plan_id=plan.plan_id,
                gate_result=GateResult.AUTO,
                state_from=PlanState.RUNNING.value,
                state_to=plan.state,
                reason=plan.last_error,
                outcome=DecisionOutcome.FAILED,
            )
            logger.error(
                "agent_execution_exception",
                plan_id=plan.plan_id,
                duration_ms=duration_ms,
                error=str(exc)[:200],
            )

        await session.commit()


@celery_app.task(name="steward.dispatch_plan")
def dispatch_plan(dispatch_id: str) -> None:
    """Run the execution pipeline for a queued dispatch."""
    asyncio.run(_run_dispatch_async(dispatch_id))


@celery_app.task(name="steward.retry_step")
def retry_step(dispatch_id: str) -> None:
    """Retry a previously failed dispatch from the persisted step pointer."""
    asyncio.run(_run_dispatch_async(dispatch_id))


@celery_app.task(name="steward.finalize_plan")
def finalize_plan(dispatch_id: str) -> None:
    """Finalize dispatch state if async workers were interrupted."""
    asyncio.run(_run_dispatch_async(dispatch_id))
