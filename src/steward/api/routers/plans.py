"""ActionPlan 人工决策路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from steward.api.deps import get_services, get_session
from steward.domain.enums import PlanState
from steward.domain.schemas import PlanDecisionResponse
from steward.services.container import ServiceContainer

router = APIRouter(prefix="/api/v1/plans", tags=["plans"])


@router.post("/{plan_id}/confirm", response_model=PlanDecisionResponse)
async def confirm_plan(
    plan_id: str,
    session: AsyncSession = Depends(get_session),
    services: ServiceContainer = Depends(get_services),
) -> PlanDecisionResponse:
    """确认计划并执行。"""
    try:
        plan = await services.plan_control_service.confirm(session, plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await session.commit()
    return PlanDecisionResponse(plan_id=plan.plan_id, state=PlanState(plan.state))


@router.post("/{plan_id}/reject", response_model=PlanDecisionResponse)
async def reject_plan(
    plan_id: str,
    session: AsyncSession = Depends(get_session),
    services: ServiceContainer = Depends(get_services),
) -> PlanDecisionResponse:
    """拒绝计划。"""
    try:
        plan = await services.plan_control_service.reject(session, plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await session.commit()
    return PlanDecisionResponse(plan_id=plan.plan_id, state=PlanState(plan.state))
