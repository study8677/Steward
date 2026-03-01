"""Connector 注册表，用于统一查找与健康检查。"""

from __future__ import annotations

from steward.connectors.base import Connector, ConnectorHealth
from steward.connectors.calendar import CalendarConnector
from steward.connectors.chat import ChatConnector
from steward.connectors.email import EmailConnector
from steward.connectors.github import GitHubConnector
from steward.connectors.local import LocalConnector
from steward.connectors.manual import ManualConnector
from steward.connectors.mcp import MCPConnector
from steward.connectors.screen import ScreenConnector
from steward.core.config import Settings


class ConnectorRegistry:
    """连接器注册与路由。"""

    def __init__(self, settings: Settings) -> None:
        self._connectors: dict[str, Connector] = {
            "manual": ManualConnector(),
            "local": LocalConnector(),
            "github": GitHubConnector(token=settings.github_token),
            "email": EmailConnector(outbound_enabled=settings.email_outbound_enabled),
            "chat": ChatConnector(outbound_enabled=settings.chat_outbound_enabled),
            "calendar": CalendarConnector(),
            "screen": ScreenConnector(),
            "mcp": MCPConnector(
                gateway_base_url=settings.mcp_gateway_base_url,
                api_key=settings.mcp_gateway_api_key,
            ),
        }

    def get(self, name: str) -> Connector:
        """按名称获取连接器。"""
        if name not in self._connectors:
            raise KeyError(f"Unknown connector: {name}")
        return self._connectors[name]

    def names(self) -> list[str]:
        """返回已注册连接器名。"""
        return sorted(self._connectors.keys())

    async def health(self) -> dict[str, ConnectorHealth]:
        """返回所有连接器健康状态。"""
        health_map: dict[str, ConnectorHealth] = {}
        for name, connector in self._connectors.items():
            health_map[name] = await connector.health()
        return health_map
