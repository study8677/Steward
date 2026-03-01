"""冲突检测服务。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from steward.domain.enums import ConflictResolution, ConflictType, PlanState, Reversibility
from steward.infra.db.models import ActionPlan, ConflictCase, PlanEffect


class ConflictService:
    """执行计划冲突检测器。"""

    async def detect_plan_time_conflict(
        self,
        session: AsyncSession,
        plan: ActionPlan,
    ) -> ConflictCase | None:
        """在计划阶段检测资源冲突。"""
        current_effects_stmt = select(PlanEffect).where(PlanEffect.plan_id == plan.plan_id)
        current_effects = list((await session.execute(current_effects_stmt)).scalars().all())
        if not current_effects:
            return None

        resource_keys = [effect.resource_key for effect in current_effects]
        stmt = (
            select(PlanEffect)
            .join(ActionPlan, PlanEffect.plan_id == ActionPlan.plan_id)
            .where(
                PlanEffect.resource_key.in_(resource_keys),
                PlanEffect.plan_id != plan.plan_id,
                ActionPlan.state.in_(
                    [
                        PlanState.PLANNED.value,
                        PlanState.GATED.value,
                        PlanState.RUNNING.value,
                        PlanState.WAITING.value,
                    ]
                ),
            )
            .limit(1)
        )
        conflict_effect = (await session.execute(stmt)).scalars().first()
        if conflict_effect is None:
            return None

        current_reversibility = current_effects[0].reversibility
        resolution = (
            ConflictResolution.ESCALATE.value
            if current_reversibility == Reversibility.IRREVERSIBLE.value
            else ConflictResolution.SERIALIZE.value
        )

        conflict = ConflictCase(
            plan_a_id=plan.plan_id,
            plan_b_id=conflict_effect.plan_id,
            conflict_type=ConflictType.RESOURCE.value,
            resolution=resolution,
            status="open",
        )
        session.add(conflict)
        if resolution == ConflictResolution.ESCALATE.value:
            plan.state = PlanState.CONFLICTED.value
        await session.flush()
        return conflict
