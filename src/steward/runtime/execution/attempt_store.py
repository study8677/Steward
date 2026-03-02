"""Persistence helpers for execution attempts and dispatch lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from steward.infra.db.models import ExecutionAttempt, ExecutionDispatch


class AttemptStore:
    """Persist execution dispatch/attempt records."""

    async def mark_dispatch_started(
        self,
        session: AsyncSession,
        dispatch: ExecutionDispatch,
    ) -> None:
        """Mark dispatch as running."""
        dispatch.status = "running"
        dispatch.started_at = datetime.now(UTC)
        await session.flush()

    async def mark_dispatch_finished(
        self,
        session: AsyncSession,
        dispatch: ExecutionDispatch,
        *,
        status: str,
    ) -> None:
        """Mark dispatch as finished with a terminal status."""
        dispatch.status = status
        dispatch.finished_at = datetime.now(UTC)
        await session.flush()

    async def add_retry(self, session: AsyncSession, dispatch: ExecutionDispatch) -> None:
        """Increase dispatch retry counter and mark retrying."""
        dispatch.retry_count += 1
        dispatch.status = "retrying"
        await session.flush()

    async def record_attempt(
        self,
        session: AsyncSession,
        *,
        dispatch_id: str,
        plan_id: str,
        connector_instance_id: str,
        step_index: int,
        idempotency_key: str,
        status: str,
        detail: str,
        duration_ms: int,
        error_type: str | None = None,
        error_message: str | None = None,
        retryable: bool = True,
    ) -> ExecutionAttempt:
        """Insert one execution attempt row."""
        attempt = ExecutionAttempt(
            dispatch_id=dispatch_id,
            plan_id=plan_id,
            connector_instance_id=connector_instance_id,
            step_index=step_index,
            idempotency_key=idempotency_key,
            status=status,
            detail=detail,
            duration_ms=duration_ms,
            error_type=error_type,
            error_message=error_message,
            retryable=retryable,
        )
        session.add(attempt)
        await session.flush()
        return attempt
