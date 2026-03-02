"""UI 路由，提供 Dashboard 页面入口。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["ui"])


@router.get("/dashboard")
async def dashboard_page() -> FileResponse:
    """返回 Dashboard 页面。"""
    root = Path(__file__).resolve().parents[2]
    html_path = root / "ui" / "static" / "dashboard.html"
    return FileResponse(html_path)


@router.get("/dashboard/integrations")
async def dashboard_integrations_page() -> FileResponse:
    """返回信息源管理页面。"""
    root = Path(__file__).resolve().parents[2]
    html_path = root / "ui" / "static" / "integrations.html"
    return FileResponse(html_path)


@router.get("/dashboard/executions")
async def dashboard_executions_page() -> FileResponse:
    """返回执行结果页面。"""
    root = Path(__file__).resolve().parents[2]
    html_path = root / "ui" / "static" / "executions.html"
    return FileResponse(html_path)
