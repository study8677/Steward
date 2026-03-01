"""简报路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from steward.api.deps import get_services, get_session
from steward.domain.schemas import BriefResponse
from steward.services.container import ServiceContainer

router = APIRouter(prefix="/api/v1/briefs", tags=["briefs"])


@router.get("/latest", response_model=BriefResponse)
async def latest_brief(
    session: AsyncSession = Depends(get_session),
    services: ServiceContainer = Depends(get_services),
) -> BriefResponse:
    """返回最新简报。"""
    return await services.briefing_service.generate_latest(
        session,
        services.settings.brief_window_hours,
    )
