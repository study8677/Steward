"""事件接入编排服务。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from steward.connectors.normalizers import normalize_webhook_payload
from steward.domain.enums import GateResult, PlanState, RiskLevel, SourceType
from steward.domain.schemas import EventIngestRequest, EventIngestResponse
from steward.infra.db.models import ContextEvent
from steward.observability.metrics import EVENT_INGESTED_TOTAL, GATE_RESULT_TOTAL
from steward.services.action_runner import ActionRunnerService
from steward.services.conflict import ConflictService
from steward.services.context_space import ContextSpaceService
from steward.services.planner import PlannerService
from steward.services.policy_gate import PolicyGateService


class EventIngestService:
    """将事件写入并推进执行闭环。"""

    def __init__(
        self,
        *,
        context_space_service: ContextSpaceService,
        planner_service: PlannerService,
        policy_gate_service: PolicyGateService,
        action_runner_service: ActionRunnerService,
        conflict_service: ConflictService,
    ) -> None:
        self._context_space_service = context_space_service
        self._planner_service = planner_service
        self._policy_gate_service = policy_gate_service
        self._action_runner_service = action_runner_service
        self._conflict_service = conflict_service
        self._logger = structlog.get_logger("event_ingest")

    async def ingest_manual_event(
        self,
        session: AsyncSession,
        request: EventIngestRequest,
    ) -> EventIngestResponse:
        """处理手动事件并执行主流程。"""
        return await self._ingest_request(session, request)

    async def ingest_channel_webhook(
        self,
        session: AsyncSession,
        channel: str,
        payload: dict[str, Any],
    ) -> EventIngestResponse:
        """处理外部渠道 webhook 事件。"""
        request = normalize_webhook_payload(channel, payload)
        return await self._ingest_request(session, request)

    async def _ingest_request(
        self,
        session: AsyncSession,
        request: EventIngestRequest,
    ) -> EventIngestResponse:
        """执行统一事件接入主链路。"""
        event = ContextEvent(
            source=request.source.value,
            source_ref=request.source_ref,
            occurred_at=datetime.now(UTC),
            actor=request.actor,
            summary=request.summary,
            confidence=request.confidence,
            raw_ref=request.raw_ref,
            entity_set=request.entities,
            dedup_key=f"manual:{request.source_ref}:{request.summary[:64]}",
            match_key=request.source_ref,
        )
        session.add(event)
        await session.flush()
        EVENT_INGESTED_TOTAL.labels(source=request.source.value).inc()

        self._logger.info(
            "ingest_pipeline_start",
            event_id=event.event_id,
            source=event.source,
            summary=event.summary[:50],
        )

        space = await self._context_space_service.route_event(session, event)
        task, plan = await self._planner_service.build_plan(session, event, space)

        conflict = await self._conflict_service.detect_plan_time_conflict(session, plan)
        if conflict is not None and conflict.resolution == "escalate":
            await session.commit()
            GATE_RESULT_TOTAL.labels(result=GateResult.CONFIRM.value).inc()
            return EventIngestResponse(
                event_id=event.event_id,
                space_id=space.space_id,
                task_id=task.task_id,
                plan_id=plan.plan_id,
                gate_result=GateResult.CONFIRM,
            )

        risk_level = RiskLevel(task.risk_level)
        gate_result, gate_reason = await self._policy_gate_service.evaluate(
            session,
            plan,
            risk_level,
            event.confidence,
        )
        GATE_RESULT_TOTAL.labels(result=gate_result.value).inc()

        if plan.state == PlanState.CONFLICTED.value:
            gate_result = GateResult.CONFIRM
            gate_reason = "conflicted_plan_needs_manual_confirmation"

        self._logger.info(
            "ingest_pipeline_completed",
            event_id=event.event_id,
            space_id=space.space_id,
            plan_id=plan.plan_id,
            gate_result=gate_result.value,
        )

        await self._action_runner_service.execute_with_gate(session, plan, gate_result, gate_reason)
        await session.commit()

        return EventIngestResponse(
            event_id=event.event_id,
            space_id=space.space_id,
            task_id=task.task_id,
            plan_id=plan.plan_id,
            gate_result=gate_result,
        )

    async def ingest_webhook_event(
        self,
        session: AsyncSession,
        payload: dict[str, object],
    ) -> EventIngestResponse:
        """处理 webhook 事件（首版用统一逻辑）。"""
        request = normalize_webhook_payload("github", payload)
        request.source = SourceType.GITHUB
        return await self._ingest_request(session, request)
