"""Dashboard 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from steward.api.deps import get_services, get_session
from steward.services.container import ServiceContainer

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/overview")
async def overview(
    session: AsyncSession = Depends(get_session),
    services: ServiceContainer = Depends(get_services),
) -> dict[str, object]:
    """返回运行总览数据。"""
    return await services.dashboard_service.overview(session)


@router.get("/snapshot")
async def snapshot(
    session: AsyncSession = Depends(get_session),
    services: ServiceContainer = Depends(get_services),
) -> dict[str, object]:
    """返回 Dashboard 聚合快照。"""
    return await services.dashboard_service.snapshot(session)


@router.get("/logs")
async def runtime_logs(
    session: AsyncSession = Depends(get_session),
    services: ServiceContainer = Depends(get_services),
) -> dict[str, object]:
    """返回运行日志列表。"""
    items = await services.dashboard_service.recent_runtime_logs(session)
    return {"items": items}
