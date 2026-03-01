"""反馈路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from steward.api.deps import get_services, get_session
from steward.domain.schemas import FeedbackRequest, FeedbackResponse
from steward.services.container import ServiceContainer

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackResponse)
async def create_feedback(
    request: FeedbackRequest,
    session: AsyncSession = Depends(get_session),
    services: ServiceContainer = Depends(get_services),
) -> FeedbackResponse:
    """写入反馈事件。"""
    feedback = await services.feedback_service.record_feedback(
        session,
        plan_id=request.plan_id,
        feedback_type=request.feedback_type,
        note=request.note,
    )
    await session.commit()
    return FeedbackResponse(
        feedback_id=feedback.feedback_id,
        plan_id=feedback.plan_id,
        feedback_type=request.feedback_type,
    )
