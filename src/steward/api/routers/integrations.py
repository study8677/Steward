"""信息源接入路由：支持自然语言配置与接入状态查询。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from steward.api.deps import get_services, get_session
from steward.connectors.normalizers import normalize_webhook_payload
from steward.domain.schemas import (
    IntegrationApplyResponse,
    IntegrationNlRequest,
    IntegrationProviderResponse,
)
from steward.services.container import ServiceContainer

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


def _base_url_from_request(request: Request) -> str:
    """从请求推断回调地址 base URL。"""
    scheme = request.url.scheme
    host = request.headers.get("host", "127.0.0.1:8000")
    return f"{scheme}://{host}"


@router.get("", response_model=IntegrationProviderResponse)
async def list_integrations(
    request: Request,
    services: ServiceContainer = Depends(get_services),
) -> IntegrationProviderResponse:
    """返回当前信息源接入状态。"""
    providers = services.integration_config_service.provider_status(
        base_url=_base_url_from_request(request),
    )
    return IntegrationProviderResponse(providers=providers)


@router.post("/nl", response_model=IntegrationApplyResponse)
async def apply_integrations_from_nl(
    payload: IntegrationNlRequest,
    request: Request,
    services: ServiceContainer = Depends(get_services),
) -> IntegrationApplyResponse:
    """通过自然语言应用信息源配置。"""
    result = await services.integration_config_service.apply_from_natural_language(
        payload.text,
        base_url=_base_url_from_request(request),
    )
    return IntegrationApplyResponse(
        applied_fields=[str(item) for item in result.get("applied_fields", [])],
        message=str(result.get("message", "已处理")),
        providers=list(result.get("providers", [])),
        raw_parse_reason=str(result.get("raw_parse_reason", "")),
    )


@router.post("/{provider}/join", response_model=IntegrationProviderResponse)
async def join_integration_provider(
    provider: str,
    request: Request,
    services: ServiceContainer = Depends(get_services),
) -> IntegrationProviderResponse:
    """点击“加入”按钮后返回最新状态与接入说明。"""
    if not services.integration_config_service.has_provider(provider):
        raise HTTPException(status_code=404, detail="unknown_provider")
    _ = services.integration_config_service.join_instructions(
        provider=provider,
        base_url=_base_url_from_request(request),
    )
    providers = services.integration_config_service.provider_status(
        base_url=_base_url_from_request(request),
    )
    return IntegrationProviderResponse(providers=providers)


@router.post("/{provider}/configure", response_model=IntegrationApplyResponse)
async def configure_integration_provider(
    provider: str,
    payload: dict[str, Any],
    request: Request,
    services: ServiceContainer = Depends(get_services),
) -> IntegrationApplyResponse:
    """按 provider 写入结构化配置。"""
    result = services.integration_config_service.configure_provider(
        provider=provider, payload=payload
    )
    configured_provider = str(result.get("provider", ""))
    if not configured_provider:
        raise HTTPException(status_code=400, detail="invalid_provider")

    created_custom = bool(result.get("created_custom", False))
    action = "已创建" if created_custom else "已更新"
    message = f"{action}信息源 {configured_provider}"
    providers = services.integration_config_service.provider_status(
        base_url=_base_url_from_request(request),
    )
    return IntegrationApplyResponse(
        applied_fields=[str(item) for item in result.get("applied_fields", [])],
        message=message,
        providers=providers,
        raw_parse_reason="configure_api",
    )


@router.post("/{provider}/test")
async def test_integration_provider(
    provider: str,
    payload: dict[str, Any],
    request: Request,
    session: AsyncSession = Depends(get_session),
    services: ServiceContainer = Depends(get_services),
) -> dict[str, Any]:
    """执行 provider 连通性测试，验证接入链路可用。"""
    status = services.integration_config_service.provider_status_item(
        provider=provider,
        base_url=_base_url_from_request(request),
    )
    if status is None:
        raise HTTPException(status_code=404, detail="unknown_provider")
    if not bool(status.get("configured")):
        raise HTTPException(status_code=409, detail="provider_not_configured")

    source = services.integration_config_service.provider_source(provider) or "custom"
    summary = str(payload.get("summary") or f"信息源测试：{provider}").strip()
    source_ref = str(
        payload.get("source_ref")
        or f"integration-test:{provider}:{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    ).strip()
    event_request = normalize_webhook_payload(
        source,
        {
            "summary": summary,
            "source_ref": source_ref,
            "actor": "integration-tester",
            "entities": [provider, "integration-test"],
            "confidence": 0.92,
        },
    )
    response = await services.event_ingest_service.ingest_manual_event(session, event_request)
    return {
        "provider": provider,
        "status": "ok",
        "event_id": response.event_id,
        "plan_id": response.plan_id,
        "gate_result": response.gate_result.value,
    }


@router.get("/{provider}")
async def integration_provider_detail(
    provider: str,
    request: Request,
    services: ServiceContainer = Depends(get_services),
) -> dict[str, Any]:
    """读取单个信息源接入状态。"""
    status = services.integration_config_service.provider_status_item(
        provider=provider,
        base_url=_base_url_from_request(request),
    )
    if status is None:
        raise HTTPException(status_code=404, detail="unknown_provider")
    return status
