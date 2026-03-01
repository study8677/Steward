"""健康检查路由。"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    """存活检查。"""
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict[str, str]:
    """就绪检查。"""
    return {"status": "ready"}
