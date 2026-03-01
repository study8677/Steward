"""Context Space 查询路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from steward.api.deps import get_services, get_session
from steward.domain.enums import SpaceState
from steward.domain.schemas import SpaceItem, SpacesResponse
from steward.services.container import ServiceContainer

router = APIRouter(prefix="/api/v1/spaces", tags=["spaces"])


@router.get("", response_model=SpacesResponse)
async def list_spaces(
    session: AsyncSession = Depends(get_session),
    services: ServiceContainer = Depends(get_services),
) -> SpacesResponse:
    """列出当前上下文空间。"""
    spaces = await services.context_space_service.list_spaces(session)
    return SpacesResponse(
        items=[
            SpaceItem(
                space_id=item.space_id,
                focus_type=item.focus_type,
                focus_ref=item.focus_ref,
                entity_set=item.entity_set,
                state=SpaceState(item.state),
                is_pinned=item.is_pinned,
                space_score=item.space_score,
                updated_at=item.updated_at,
            )
            for item in spaces
        ]
    )
