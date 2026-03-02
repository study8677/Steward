"""Celery tasks for asynchronous plan execution."""

from __future__ import annotations

import asyncio
from time import perf_counter

from steward.core.config import Settings, get_settings
from steward.core.logging import configure_logging, get_logger
from steward.core.model_config import enforce_model_config
from steward.domain.enums import DecisionOutcome, GateResult, PlanState
from steward.domain.state_machine import can_transition
from steward.infra.db.models import ActionPlan, ExecutionDispatch
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

        await attempt_store.mark_dispatch_started(session, dispatch)
        plan.execution_status = "running"
        plan.last_error = None
        if can_transition(PlanState(plan.state), PlanState.RUNNING):
            plan.state = PlanState.RUNNING.value
        await session.flush()

        start_index = max(0, int(plan.current_step))
        for idx, raw_step in enumerate(plan.steps):
            if idx < start_index:
                continue

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

            await attempt_store.record_attempt(
                session,
                dispatch_id=dispatch.dispatch_id,
                plan_id=plan.plan_id,
                connector_instance_id=connector_name,
                step_index=idx,
                idempotency_key=idempotency_key,
                status="succeeded",
                detail=result.detail[:500],
                duration_ms=duration_ms,
                retryable=retryable,
            )

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
