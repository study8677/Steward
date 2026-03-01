"""WAITING 引擎服务。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from steward.domain.enums import PlanState, TriggerStatus
from steward.infra.db.models import ActionPlan, WaitingTrigger
from steward.observability.metrics import WAITING_QUEUE_SIZE
from steward.services.action_runner import ActionRunnerService


class WaitingService:
    """处理 WAITING 触发与超时扫描。"""

    def __init__(self, action_runner_service: ActionRunnerService) -> None:
        self._action_runner_service = action_runner_service

    async def resume_by_match_key(self, session: AsyncSession, match_key: str) -> int:
        """根据事件 match_key 恢复等待计划。"""
        stmt = select(WaitingTrigger).where(
            WaitingTrigger.match_key == match_key,
            WaitingTrigger.trigger_status == TriggerStatus.ACTIVE.value,
        )
        triggers = list((await session.execute(stmt)).scalars().all())
        resumed = 0
        for trigger in triggers:
            plan = await session.get(ActionPlan, trigger.plan_id)
            if plan is None:
                continue
            await self._action_runner_service.resume_waiting_plan(session, plan)
            trigger.trigger_status = TriggerStatus.CONSUMED.value
            resumed += 1
        await self._refresh_waiting_size(session)
        return resumed

    async def scan_timeouts(self, session: AsyncSession) -> int:
        """扫描 WAITING 超时计划。"""
        now = datetime.now(UTC)
        stmt = select(ActionPlan).where(
            ActionPlan.state == PlanState.WAITING.value,
            ActionPlan.wait_timeout_at.is_not(None),
            ActionPlan.wait_timeout_at <= now,
        )
        plans = list((await session.execute(stmt)).scalars().all())
        for plan in plans:
            await self._action_runner_service.mark_wait_timeout(session, plan)

        await self._refresh_waiting_size(session)
        return len(plans)

    async def _refresh_waiting_size(self, session: AsyncSession) -> None:
        """刷新 WAITING 队列指标。"""
        stmt = select(ActionPlan).where(ActionPlan.state == PlanState.WAITING.value)
        waiting_count = len(list((await session.execute(stmt)).scalars().all()))
        WAITING_QUEUE_SIZE.set(waiting_count)
