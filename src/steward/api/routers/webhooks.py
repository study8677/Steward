"""Webhook 接入路由，覆盖通用渠道与真实 Provider 适配器。"""

from __future__ import annotations

import json
from typing import Any, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from steward.api.deps import get_services, get_session
from steward.connectors.normalizers import normalize_webhook_payload
from steward.connectors.provider_adapters import (
    GitHubWebhookAdapter,
    GmailWebhookAdapter,
    GoogleCalendarWebhookAdapter,
    SlackWebhookAdapter,
)
from steward.domain.schemas import EventIngestResponse
from steward.services.container import ServiceContainer
from steward.services.webhook_backpressure import WebhookBackpressureService

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


def _assert_webhook_secret(
    services: ServiceContainer,
    channel: str,
    webhook_token: str | None,
) -> None:
    """校验渠道 webhook 密钥。"""
    per_channel_secret = {
        "email": services.settings.email_webhook_secret,
        "chat": services.settings.chat_webhook_secret,
        "calendar": services.settings.calendar_webhook_secret,
        "screen": services.settings.screen_webhook_secret,
        "mcp": services.settings.webhook_shared_secret,
    }.get(channel, "")
    expected = per_channel_secret or services.settings.webhook_shared_secret
    if expected and webhook_token != expected:
        raise HTTPException(status_code=401, detail=f"invalid_{channel}_webhook_secret")


def _headers_to_lower_dict(request: Request) -> dict[str, str]:
    """将请求头转成小写键。"""
    return {key.lower(): value for key, value in request.headers.items()}


def _get_backpressure(request: Request) -> WebhookBackpressureService:
    """读取应用级反压服务。"""
    return cast(WebhookBackpressureService, request.app.state.webhook_backpressure)


async def _ingest_with_backpressure(
    *,
    request: Request,
    session: AsyncSession,
    services: ServiceContainer,
    provider: str,
    event_request,
    dedup_key: str | None,
) -> EventIngestResponse:
    """统一反压控制并执行事件入链。"""
    backpressure = _get_backpressure(request)
    admission = await backpressure.admit(provider, dedup_key)
    if admission.duplicate:
        raise HTTPException(status_code=202, detail="duplicate_event")
    if not admission.accepted:
        raise HTTPException(status_code=429, detail=f"webhook_backpressure:{admission.reason}")

    try:
        return await services.event_ingest_service.ingest_manual_event(session, event_request)
    finally:
        await backpressure.release(provider)


@router.post("/email", response_model=EventIngestResponse)
async def email_webhook(
    payload: dict[str, Any],
    request: Request,
    webhook_token: str | None = Header(default=None, alias="x-steward-webhook-token"),
    session: AsyncSession = Depends(get_session),
    services: ServiceContainer = Depends(get_services),
) -> EventIngestResponse:
    """接收邮件 webhook。"""
    _assert_webhook_secret(services, "email", webhook_token)
    return await services.event_ingest_service.ingest_channel_webhook(session, "email", payload)


@router.post("/chat", response_model=EventIngestResponse)
async def chat_webhook(
    payload: dict[str, Any],
    request: Request,
    webhook_token: str | None = Header(default=None, alias="x-steward-webhook-token"),
    session: AsyncSession = Depends(get_session),
    services: ServiceContainer = Depends(get_services),
) -> EventIngestResponse:
    """接收聊天 webhook。"""
    _ = request
    _assert_webhook_secret(services, "chat", webhook_token)
    return await services.event_ingest_service.ingest_channel_webhook(session, "chat", payload)


@router.post("/calendar", response_model=EventIngestResponse)
async def calendar_webhook(
    payload: dict[str, Any],
    request: Request,
    webhook_token: str | None = Header(default=None, alias="x-steward-webhook-token"),
    session: AsyncSession = Depends(get_session),
    services: ServiceContainer = Depends(get_services),
) -> EventIngestResponse:
    """接收日历 webhook。"""
    _ = request
    _assert_webhook_secret(services, "calendar", webhook_token)
    return await services.event_ingest_service.ingest_channel_webhook(session, "calendar", payload)


@router.post("/screen", response_model=EventIngestResponse)
async def screen_webhook(
    payload: dict[str, Any],
    request: Request,
    webhook_token: str | None = Header(default=None, alias="x-steward-webhook-token"),
    session: AsyncSession = Depends(get_session),
    services: ServiceContainer = Depends(get_services),
) -> EventIngestResponse:
    """接收屏幕传感器 webhook。"""
    _ = request
    _assert_webhook_secret(services, "screen", webhook_token)
    return await services.event_ingest_service.ingest_channel_webhook(session, "screen", payload)


@router.post("/mcp/{server}", response_model=EventIngestResponse)
async def mcp_webhook(
    server: str,
    payload: dict[str, Any],
    request: Request,
    webhook_token: str | None = Header(default=None, alias="x-steward-webhook-token"),
    session: AsyncSession = Depends(get_session),
    services: ServiceContainer = Depends(get_services),
) -> EventIngestResponse:
    """接收 MCP 桥接 webhook。"""
    _ = request
    _assert_webhook_secret(services, "mcp", webhook_token)
    decorated_payload = dict(payload)
    entities = decorated_payload.get("entities", [])
    if isinstance(entities, list):
        entities.append(f"mcp:{server}")
        decorated_payload["entities"] = entities
    decorated_payload["source_ref"] = str(decorated_payload.get("source_ref", f"mcp:{server}"))
    decorated_payload["actor"] = str(decorated_payload.get("actor", f"mcp:{server}"))
    return await services.event_ingest_service.ingest_channel_webhook(
        session, "chat", decorated_payload
    )


@router.post("/providers/slack", response_model=EventIngestResponse)
async def slack_provider_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
    services: ServiceContainer = Depends(get_services),
) -> EventIngestResponse | dict[str, str]:
    """接收并验证 Slack 官方事件回调。"""
    raw_body = await request.body()
    headers = _headers_to_lower_dict(request)

    adapter = SlackWebhookAdapter(services.settings)
    verified = adapter.verify(raw_body, headers)
    if not verified.ok:
        raise HTTPException(status_code=401, detail=verified.reason)

    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid_json") from exc

    if payload.get("type") == "url_verification":
        challenge = str(payload.get("challenge", ""))
        if not challenge:
            raise HTTPException(status_code=400, detail="missing_challenge")
        return {"challenge": challenge}

    event_request = adapter.normalize(payload)
    dedup_key = str(payload.get("event_id", "")) or None
    return await _ingest_with_backpressure(
        request=request,
        session=session,
        services=services,
        provider="slack",
        event_request=event_request,
        dedup_key=dedup_key,
    )


@router.post("/providers/github", response_model=EventIngestResponse)
async def github_provider_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
    services: ServiceContainer = Depends(get_services),
) -> EventIngestResponse | dict[str, str]:
    """接收并验证 GitHub webhook（issues / issue_comment / pull_request）。"""
    raw_body = await request.body()
    headers = _headers_to_lower_dict(request)

    adapter = GitHubWebhookAdapter(services.settings)
    verified = adapter.verify(raw_body, headers)
    if not verified.ok:
        raise HTTPException(status_code=401, detail=verified.reason)

    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid_json") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid_payload")

    event_type = str(headers.get("x-github-event", "")).strip().lower()
    if event_type in {"ping"}:
        return {"status": "ok"}

    event_request = adapter.normalize(payload, event_type=event_type or "event")
    return await _ingest_with_backpressure(
        request=request,
        session=session,
        services=services,
        provider="github",
        event_request=event_request,
        dedup_key=verified.dedup_key,
    )


@router.post("/providers/gmail", response_model=EventIngestResponse)
async def gmail_provider_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
    services: ServiceContainer = Depends(get_services),
) -> EventIngestResponse:
    """接收并验证 Gmail Pub/Sub 推送。"""
    headers = _headers_to_lower_dict(request)
    adapter = GmailWebhookAdapter(services.settings)
    verified = adapter.verify(headers)
    if not verified.ok:
        raise HTTPException(status_code=401, detail=verified.reason)

    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid_payload")

    event_request, dedup_key = adapter.normalize(payload)
    return await _ingest_with_backpressure(
        request=request,
        session=session,
        services=services,
        provider="gmail",
        event_request=event_request,
        dedup_key=dedup_key,
    )


@router.post("/providers/google-calendar", response_model=EventIngestResponse)
async def google_calendar_provider_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
    services: ServiceContainer = Depends(get_services),
) -> EventIngestResponse:
    """接收并验证 Google Calendar 推送。"""
    headers = _headers_to_lower_dict(request)
    adapter = GoogleCalendarWebhookAdapter(services.settings)
    verified = adapter.verify(headers)
    if not verified.ok:
        raise HTTPException(status_code=401, detail=verified.reason)

    payload: dict[str, Any] = {}
    if request.headers.get("content-type", "").startswith("application/json"):
        maybe_payload = await request.json()
        if isinstance(maybe_payload, dict):
            payload = maybe_payload

    event_request = adapter.normalize(headers, payload)
    return await _ingest_with_backpressure(
        request=request,
        session=session,
        services=services,
        provider="google-calendar",
        event_request=event_request,
        dedup_key=verified.dedup_key,
    )


@router.post("/custom/{provider}", response_model=EventIngestResponse)
async def custom_provider_webhook(
    provider: str,
    payload: dict[str, Any],
    request: Request,
    webhook_token: str | None = Header(default=None, alias="x-steward-webhook-token"),
    session: AsyncSession = Depends(get_session),
    services: ServiceContainer = Depends(get_services),
) -> EventIngestResponse:
    """接收用户自定义信息源 webhook。"""
    custom = services.integration_config_service.custom_provider(provider)
    if custom is None:
        raise HTTPException(status_code=404, detail="unknown_custom_provider")

    expected_secret = custom.get("webhook_secret", "").strip()
    if expected_secret and webhook_token != expected_secret:
        raise HTTPException(status_code=401, detail="invalid_custom_webhook_secret")

    channel = custom.get("source", "custom")
    event_request = normalize_webhook_payload(channel, payload)

    normalized_provider = str(custom.get("provider", provider)).strip().lower()
    if normalized_provider and not event_request.source_ref.startswith(f"{normalized_provider}:"):
        event_request.source_ref = f"{normalized_provider}:{event_request.source_ref}"
    if event_request.actor in {channel, "custom"}:
        event_request.actor = normalized_provider or event_request.actor
    if normalized_provider and normalized_provider not in event_request.entities:
        event_request.entities.append(normalized_provider)

    dedup_key = (
        str(payload.get("event_id", ""))
        or str(payload.get("id", ""))
        or str(payload.get("message_id", ""))
        or None
    )

    return await _ingest_with_backpressure(
        request=request,
        session=session,
        services=services,
        provider=f"custom:{normalized_provider or provider}",
        event_request=event_request,
        dedup_key=dedup_key,
    )
