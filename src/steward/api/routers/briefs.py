"""简报路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from steward.api.deps import get_services, get_session
from steward.domain.schemas import (
    BriefResponse,
    BriefSettingsResponse,
    BriefSettingsUpdateRequest,
)
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
        content_level=services.settings.brief_content_level,
    )


@router.get("/settings", response_model=BriefSettingsResponse)
async def get_brief_settings(
    services: ServiceContainer = Depends(get_services),
) -> BriefSettingsResponse:
    """读取简报偏好配置。"""
    return services.brief_preference_service.get_settings()


@router.put("/settings", response_model=BriefSettingsResponse)
async def update_brief_settings(
    payload: BriefSettingsUpdateRequest,
    request: Request,
    services: ServiceContainer = Depends(get_services),
) -> BriefSettingsResponse:
    """更新简报偏好配置并立即生效。"""
    updated = services.brief_preference_service.update_settings(
        frequency_hours=payload.frequency_hours,
        content_level=payload.content_level,
    )
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is not None and services.settings.enable_scheduler:
        scheduler.reschedule_periodic_brief(updated.frequency_hours)
    return updated
