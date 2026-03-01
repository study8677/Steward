"""FastAPI 依赖注入定义。"""

from __future__ import annotations

from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from steward.infra.db.session import get_db_session
from steward.services.container import ServiceContainer


async def get_session(session: AsyncSession = Depends(get_db_session)) -> AsyncSession:
    """注入数据库会话。"""
    return session


def get_services(request: Request) -> ServiceContainer:
    """注入服务容器。"""
    return cast(ServiceContainer, request.app.state.services)
