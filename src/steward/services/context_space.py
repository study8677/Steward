"""Context Space 聚合服务。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from steward.domain.enums import SpaceState
from steward.infra.db.models import ContextEvent, ContextSpace
from steward.services.model_gateway import ModelGateway, SpaceCandidate


class ContextSpaceService:
    """负责事件归拢与空间复活。"""

    def __init__(self, model_gateway: ModelGateway) -> None:
        self._model_gateway = model_gateway

    async def route_event(self, session: AsyncSession, event: ContextEvent) -> ContextSpace:
        """将事件路由到空间。"""
        candidates = await self._fetch_candidates(session)
        decision = await self._model_gateway.route_space(
            event.summary,
            event.entity_set,
            [
                SpaceCandidate(
                    space_id=item.space_id, focus_ref=item.focus_ref, entities=item.entity_set
                )
                for item in candidates
            ],
            # 屏幕信号强调低延迟，避免每次窗口切换都触发远端模型调用。
            allow_model=event.source != "screen",
        )

        if decision.target != "NEW":
            for candidate in candidates:
                if candidate.space_id == decision.target:
                    candidate.evidence_events.append(event.event_id)
                    candidate.entity_set = sorted(set(candidate.entity_set + event.entity_set))
                    candidate.space_score = max(candidate.space_score, decision.confidence)
                    candidate.last_reactivated_at = datetime.now(UTC)
                    if candidate.state != SpaceState.ACTIVE.value:
                        candidate.state = SpaceState.ACTIVE.value
                    await session.flush()
                    return candidate

        space_id = f"SPACE_{uuid4().hex[:10]}"
        new_space = ContextSpace(
            space_id=space_id,
            focus_type="project",
            focus_ref=event.source_ref,
            entity_set=event.entity_set,
            evidence_events=[event.event_id],
            space_score=max(0.6, decision.confidence),
            state=SpaceState.ACTIVE.value,
            is_pinned=False,
        )
        session.add(new_space)
        await session.flush()
        return new_space

    async def list_spaces(self, session: AsyncSession, limit: int = 50) -> list[ContextSpace]:
        """返回空间列表。"""
        stmt = (
            select(ContextSpace)
            .order_by(ContextSpace.is_pinned.desc(), ContextSpace.updated_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _fetch_candidates(self, session: AsyncSession) -> list[ContextSpace]:
        """加载候选空间（Pinned + 最近活跃）。"""
        stmt = (
            select(ContextSpace)
            .where(ContextSpace.state.in_([state.value for state in SpaceState]))
            .order_by(ContextSpace.is_pinned.desc(), ContextSpace.updated_at.desc())
            .limit(50)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
