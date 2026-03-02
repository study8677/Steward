"""Dashboard 路由。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
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


@router.get("/executions")
async def executions(
    limit: int = Query(default=30, ge=1, le=200),
    lang: str = Query(default="zh", pattern="^(zh|en)$"),
    session: AsyncSession = Depends(get_session),
    services: ServiceContainer = Depends(get_services),
) -> dict[str, object]:
    """返回最近执行结果（dispatch + attempts）。"""
    items = await services.dashboard_service.recent_executions(session, limit=limit, lang=lang)
    return {"items": items, "count": len(items)}


@router.get("/records/{filename}", response_class=PlainTextResponse)
async def execution_record(
    filename: str,
    services: ServiceContainer = Depends(get_services),
) -> PlainTextResponse:
    """返回 manual.record_note 落盘的 journal 文件内容。"""
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name.endswith(".md"):
        raise HTTPException(status_code=400, detail="invalid_record_filename")

    journal_path = Path(services.settings.brain_dir).expanduser().resolve() / "journal" / safe_name
    if not journal_path.exists():
        raise HTTPException(status_code=404, detail="record_not_found")

    content = journal_path.read_text(encoding="utf-8")
    return PlainTextResponse(content=content, media_type="text/markdown; charset=utf-8")
