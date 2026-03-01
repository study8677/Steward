"""MCP 通用连接器，用于桥接外部 MCP 能力。"""

from __future__ import annotations

from typing import Any

import httpx

from steward.connectors.base import ConnectorHealth, ExecutionResult


class MCPConnector:
    """通过 HTTP 网关调用 MCP 的连接器。"""

    name = "mcp"

    def __init__(self, gateway_base_url: str, api_key: str = "") -> None:
        self._gateway_base_url = gateway_base_url.rstrip("/")
        self._api_key = api_key

    async def capabilities(self) -> list[str]:
        """返回支持能力。"""
        return ["mcp_execute", "mcp_pull"]

    async def required_scopes(self) -> list[str]:
        """返回建议授权范围。"""
        return ["mcp:execute"]

    async def pull(self, cursor: str | None) -> list[dict[str, object]]:
        """从 MCP 网关拉取事件（可选）。"""
        if not self._gateway_base_url:
            return []

        params = {"cursor": cursor} if cursor else None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self._gateway_base_url}/events",
                    params=params,
                    headers=self._headers,
                )
        except httpx.HTTPError:
            return []

        if response.status_code >= 400:
            return []

        data = response.json()
        events = data.get("events", [])
        return [item for item in events if isinstance(item, dict)]

    async def execute(self, action: dict[str, object]) -> ExecutionResult:
        """执行 MCP 动作。"""
        if not self._gateway_base_url:
            return ExecutionResult(
                success=False, reversible=True, detail="mcp_gateway_not_configured"
            )

        payload: dict[str, Any] = {
            "server": action.get("server", "default"),
            "action_type": action.get("action_type", "mcp_execute"),
            "payload": action.get("payload", {}),
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{self._gateway_base_url}/execute",
                    json=payload,
                    headers=self._headers,
                )
        except httpx.HTTPError:
            return ExecutionResult(success=False, reversible=True, detail="mcp_gateway_unreachable")

        if response.status_code >= 400:
            return ExecutionResult(
                success=False,
                reversible=True,
                detail=f"mcp_http_{response.status_code}",
            )

        result_payload = response.json() if response.content else {}
        return ExecutionResult(
            success=bool(result_payload.get("success", True)),
            reversible=bool(result_payload.get("reversible", True)),
            detail=str(result_payload.get("detail", "mcp_executed")),
            data=result_payload if isinstance(result_payload, dict) else {},
        )

    async def health(self) -> ConnectorHealth:
        """检测 MCP 网关可达性。"""
        if not self._gateway_base_url:
            return ConnectorHealth(
                healthy=False, code="missing_gateway", message="MCP gateway not configured"
            )

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self._gateway_base_url}/health", headers=self._headers
                )
        except httpx.HTTPError:
            return ConnectorHealth(
                healthy=False, code="unreachable", message="MCP gateway unreachable"
            )

        if response.status_code >= 400:
            return ConnectorHealth(
                healthy=False, code=f"http_{response.status_code}", message=response.text
            )
        return ConnectorHealth(healthy=True)

    @property
    def _headers(self) -> dict[str, str]:
        """构建请求头。"""
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers
