"""Dispatch plans into Celery execution workers."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from steward.core.logging import get_logger
from steward.infra.db.models import ActionPlan, ExecutionDispatch
from steward.runtime.execution.celery_app import celery_app

logger = get_logger(component="execution_dispatcher")


@dataclass(slots=True)
class ExecutionDispatchResult:
    """Execution dispatch result."""

    dispatch_id: str
    status: str


class ExecutionDispatcher:
    """Create dispatch records and enqueue worker jobs."""

    async def dispatch_plan(
        self,
        session: AsyncSession,
        *,
        plan: ActionPlan,
        trigger_reason: str,
    ) -> ExecutionDispatchResult:
        """Create one dispatch row and enqueue Celery execution."""
        dispatch = ExecutionDispatch(
            plan_id=plan.plan_id,
            status="queued",
            trigger_reason=trigger_reason[:120],
        )
        session.add(dispatch)
        await session.flush()

        plan.dispatch_id = dispatch.dispatch_id
        plan.execution_status = "queued"
        await session.flush()

        # Delay the task slightly so the enclosing DB transaction can commit first.
        try:
            celery_app.send_task(
                "steward.dispatch_plan",
                args=[dispatch.dispatch_id],
                countdown=1,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "execution_dispatch_enqueue_failed",
                dispatch_id=dispatch.dispatch_id,
                error=str(exc),
            )
            dispatch.status = "failed"
            plan.execution_status = "failed"
            plan.last_error = f"dispatch_enqueue_failed:{type(exc).__name__}"
            await session.flush()
            return ExecutionDispatchResult(dispatch_id=dispatch.dispatch_id, status="failed")

        logger.info("execution_dispatched", plan_id=plan.plan_id, dispatch_id=dispatch.dispatch_id)
        return ExecutionDispatchResult(dispatch_id=dispatch.dispatch_id, status="queued")
