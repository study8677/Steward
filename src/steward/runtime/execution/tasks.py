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

        start_index = max(0, int(plan.current_step))
        idx = start_index
        while idx < len(plan.steps):
            raw_step = plan.steps[idx]

            if not isinstance(raw_step, dict):
                plan.execution_status = "failed"
                plan.last_error = f"step_{idx}_invalid"
                if can_transition(PlanState(plan.state), PlanState.FAILED):
                    plan.state = PlanState.FAILED.value
                await attempt_store.mark_dispatch_finished(session, dispatch, status="failed")
                await session.commit()
                return

            connector_name = str(raw_step.get("connector", "")).strip()
            if not connector_name:
                connector_name = "manual"
            retryable = bool(raw_step.get("retryable", True))
            idempotency_key = f"{dispatch.dispatch_id}:{idx}:r{dispatch.retry_count}"

            plan.current_step = idx
            await session.flush()

            started = perf_counter()
            try:
                connector = services.connectors.get(connector_name)
                result = await connector.execute(raw_step)
                duration_ms = int((perf_counter() - started) * 1000)
            except Exception as exc:  # noqa: BLE001
                duration_ms = int((perf_counter() - started) * 1000)
                await attempt_store.record_attempt(
                    session,
                    dispatch_id=dispatch.dispatch_id,
                    plan_id=plan.plan_id,
                    connector_instance_id=connector_name,
                    step_index=idx,
                    idempotency_key=idempotency_key,
                    status="failed",
                    detail=f"exception:{type(exc).__name__}",
                    duration_ms=duration_ms,
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:500],
                    retryable=retryable,
                )
                if retryable and dispatch.retry_count < settings.execution_max_retries:
                    await attempt_store.add_retry(session, dispatch)
                    await session.commit()
                    retry_step.apply_async(
                        args=[dispatch.dispatch_id],
                        countdown=settings.execution_retry_delay_seconds,
                    )
                    return

                plan.execution_status = "failed"
                plan.last_error = f"step_{idx}_exception:{type(exc).__name__}"
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
                await session.commit()
                return

            if not result.success:
                await attempt_store.record_attempt(
                    session,
                    dispatch_id=dispatch.dispatch_id,
                    plan_id=plan.plan_id,
                    connector_instance_id=connector_name,
                    step_index=idx,
                    idempotency_key=idempotency_key,
                    status="failed",
                    detail=result.detail[:500],
                    duration_ms=duration_ms,
                    error_type="connector_error",
                    error_message=result.detail[:500],
                    retryable=retryable,
                )
                if retryable and dispatch.retry_count < settings.execution_max_retries:
                    await attempt_store.add_retry(session, dispatch)
                    await session.commit()
                    retry_step.apply_async(
                        args=[dispatch.dispatch_id],
                        countdown=settings.execution_retry_delay_seconds,
                    )
                    return

                plan.execution_status = "failed"
                plan.last_error = f"step_{idx}_failed:{result.detail[:180]}"
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
                await session.commit()
                return

            reflection = {
                "decision": "continue",
                "summary": "本步骤已完成，继续执行后续步骤。",
                "next_steps": [],
            }
            try:
                reflection = await services.model_gateway.reflect_execution_step(
                    plan_id=plan.plan_id,
                    intent=intent,
                    step_index=idx,
                    step=raw_step,
                    step_success=True,
                    step_detail=result.detail,
                    remaining_steps=max(0, len(plan.steps) - idx - 1),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "execution_reflection_failed",
                    plan_id=plan.plan_id,
                    step_index=idx,
                    error=str(exc),
                )

            reflection_summary = str(reflection.get("summary", "")).strip()[:180]
            attempt_detail = result.detail[:350]
            if reflection_summary:
                attempt_detail = f"{attempt_detail} | reflection:{reflection_summary}"
            await attempt_store.record_attempt(
                session,
                dispatch_id=dispatch.dispatch_id,
                plan_id=plan.plan_id,
                connector_instance_id=connector_name,
                step_index=idx,
                idempotency_key=idempotency_key,
                status="succeeded",
                detail=attempt_detail[:500],
                duration_ms=duration_ms,
                retryable=retryable,
            )

            decision = str(reflection.get("decision", "continue")).strip().lower()
            if decision == "halt":
                plan.execution_status = "failed"
                plan.last_error = f"reflection_halt:{reflection_summary[:140]}"
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
                await session.commit()
                return

            if decision == "replan":
                next_steps_raw = reflection.get("next_steps", [])
                next_steps = next_steps_raw if isinstance(next_steps_raw, list) else []
                valid_steps: list[dict[str, object]] = []
                for next_step in next_steps:
                    if not isinstance(next_step, dict):
                        continue
                    connector = str(next_step.get("connector", "")).strip().lower()
                    action_type = str(next_step.get("action_type", "")).strip()
                    payload_raw = next_step.get("payload", {})
                    payload = payload_raw if isinstance(payload_raw, dict) else {}
                    if not connector or not action_type:
                        continue

                    is_valid, reason = services.connectors.validate_action(
                        connector=connector,
                        action_type=action_type,
                        payload=payload,
                    )
                    if not is_valid:
                        plan.execution_status = "failed"
                        plan.last_error = f"reflection_replan_invalid:{reason}"
                        if can_transition(PlanState(plan.state), PlanState.FAILED):
                            plan.state = PlanState.FAILED.value
                        await attempt_store.mark_dispatch_finished(
                            session, dispatch, status="failed"
                        )
                        await services.decision_log_service.append(
                            session,
                            plan_id=plan.plan_id,
                            gate_result=GateResult.BLOCKED,
                            state_from=PlanState.RUNNING.value,
                            state_to=plan.state,
                            reason=plan.last_error,
                            outcome=DecisionOutcome.FAILED,
                        )
                        await session.commit()
                        return
                    valid_steps.append(next_step)

                if valid_steps:
                    plan.steps = list(plan.steps[: idx + 1]) + valid_steps
                    await services.decision_log_service.append(
                        session,
                        plan_id=plan.plan_id,
                        gate_result=GateResult.AUTO,
                        state_from=PlanState.RUNNING.value,
                        state_to=PlanState.RUNNING.value,
                        reason=f"reflection_replan_step_{idx}:{reflection_summary[:80]}",
                        outcome=DecisionOutcome.SUCCEEDED,
                    )
                    await session.flush()

            idx += 1

        plan.current_step = len(plan.steps)
        if plan.wait_condition:
            if can_transition(PlanState(plan.state), PlanState.WAITING):
                plan.state = PlanState.WAITING.value
            plan.execution_status = "waiting"
            await attempt_store.mark_dispatch_finished(session, dispatch, status="waiting")
            await services.decision_log_service.append(
                session,
                plan_id=plan.plan_id,
                gate_result=GateResult.AUTO,
                state_from=PlanState.RUNNING.value,
                state_to=plan.state,
                reason="async_execution_waiting",
                outcome=DecisionOutcome.SUCCEEDED,
            )
            await session.commit()
            return

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
            reason="async_execution_completed",
            outcome=DecisionOutcome.SUCCEEDED,
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
