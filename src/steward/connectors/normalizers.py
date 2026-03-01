"""Webhook 负载标准化工具。"""

from __future__ import annotations

from typing import Any

from steward.domain.enums import SourceType
from steward.domain.schemas import EventIngestRequest

SOURCE_ALIAS: dict[str, SourceType] = {
    "email": SourceType.EMAIL,
    "chat": SourceType.CHAT,
    "calendar": SourceType.CALENDAR,
    "screen": SourceType.SCREEN,
    "github": SourceType.GITHUB,
    "local": SourceType.LOCAL,
    "manual": SourceType.MANUAL,
    "custom": SourceType.CUSTOM,
}


def normalize_webhook_payload(
    channel: str,
    payload: dict[str, Any],
) -> EventIngestRequest:
    """将不同 webhook 结构归一为统一事件请求。"""
    source = SOURCE_ALIAS.get(channel, SourceType.MANUAL)

    summary = str(
        payload.get("summary")
        or payload.get("text")
        or payload.get("subject")
        or payload.get("title")
        or f"{channel} webhook event"
    )

    source_ref = str(
        payload.get("source_ref")
        or payload.get("thread_id")
        or payload.get("message_id")
        or payload.get("event_id")
        or payload.get("id")
        or f"{channel}:webhook"
    )

    actor = str(payload.get("actor") or payload.get("from") or payload.get("sender") or channel)

    confidence_raw = payload.get("confidence", 0.82)
    confidence = float(confidence_raw) if isinstance(confidence_raw, (int, float, str)) else 0.82

    entities_raw = payload.get("entities", [])
    entities = (
        [str(item) for item in entities_raw if isinstance(item, (str, int, float))]
        if isinstance(entities_raw, list)
        else []
    )

    if not entities:
        for key in ("repo", "issue", "channel", "calendar", "app", "window_title"):
            value = payload.get(key)
            if value:
                entities.append(str(value))

    raw_ref = str(payload.get("raw_ref", "")) or None

    return EventIngestRequest(
        source=source,
        source_ref=source_ref,
        actor=actor,
        summary=summary,
        confidence=max(0.0, min(1.0, confidence)),
        raw_ref=raw_ref,
        entities=entities,
    )
