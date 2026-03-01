"""事件接入路由。"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from steward.api.deps import get_services, get_session
from steward.domain.enums import SourceType
from steward.domain.schemas import (
    EventIngestRequest,
    EventIngestResponse,
    NaturalLanguageEventRequest,
)
from steward.services.container import ServiceContainer

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.post("/ingest", response_model=EventIngestResponse)
async def ingest_event(
    request: EventIngestRequest,
    session: AsyncSession = Depends(get_session),
    services: ServiceContainer = Depends(get_services),
) -> EventIngestResponse:
    """写入手动事件并触发闭环执行。"""
    return await services.event_ingest_service.ingest_manual_event(session, request)


@router.post("/webhook", response_model=EventIngestResponse)
async def ingest_webhook(
    payload: dict[str, object],
    session: AsyncSession = Depends(get_session),
    services: ServiceContainer = Depends(get_services),
) -> EventIngestResponse:
    """接收 webhook 事件。"""
    return await services.event_ingest_service.ingest_webhook_event(session, payload)


@router.post("/ingest-nl", response_model=EventIngestResponse)
async def ingest_event_natural_language(
    request: NaturalLanguageEventRequest,
    session: AsyncSession = Depends(get_session),
    services: ServiceContainer = Depends(get_services),
) -> EventIngestResponse:
    """接收自然语言并自动结构化为事件。"""
    parsed = await services.model_gateway.parse_natural_language_event_text(request.text)

    source_value = str(parsed.get("source", request.source_hint.value))
    try:
        source = SourceType(source_value)
    except ValueError:
        source = request.source_hint

    confidence_raw = parsed.get("confidence", 0.88)
    try:
        confidence = float(confidence_raw)
    except TypeError, ValueError:
        confidence = 0.88
    confidence = max(0.0, min(1.0, confidence))

    entities_raw = parsed.get("entities", [])
    entities = (
        [str(item).strip() for item in entities_raw] if isinstance(entities_raw, list) else []
    )
    entities = [item for item in entities if item][:12]

    summary = str(parsed.get("summary", request.text)).strip() or request.text
    source_ref = str(parsed.get("source_ref", "")).strip()
    if not source_ref:
        source_ref = f"manual:nl:{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

    normalized = EventIngestRequest(
        source=source,
        source_ref=source_ref[:255],
        actor="user",
        summary=summary[:240],
        confidence=confidence,
        entities=entities,
    )
    return await services.event_ingest_service.ingest_manual_event(session, normalized)
