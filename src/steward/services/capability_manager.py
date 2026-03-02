"""Capability lifecycle service backed by real integration state and connector health."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from steward.connectors.registry import ConnectorRegistry
from steward.services.integration_config import IntegrationConfigService


@dataclass(slots=True)
class CapabilityProposal:
    """能力安装建议。"""

    name: str
    reason: str
    source: str
    requires_confirmation: bool = True


class CapabilityManagerService:
    """管理外部能力的提议与生命周期。"""

    def __init__(
        self,
        integration_config_service: IntegrationConfigService,
        connectors: ConnectorRegistry,
    ) -> None:
        self._integration_config_service = integration_config_service
        self._connectors = connectors

    async def health_snapshot(self) -> dict[str, Any]:
        """返回当前能力健康快照。"""
        connector_health = await self._connectors.health()
        return {
            "connectors": {
                name: {
                    "healthy": status.healthy,
                    "code": status.code,
                    "message": status.message,
                }
                for name, status in connector_health.items()
            },
            "mcp_servers": self._integration_config_service.mcp_server_status(),
            "skills": self._integration_config_service.skill_status(),
        }

    def propose_missing_capabilities(self, context: list[str]) -> list[CapabilityProposal]:
        """根据上下文和已启用能力返回安装建议。"""
        proposals: list[CapabilityProposal] = []
        normalized = " ".join(context).lower()

        mcp_servers = {
            item["server"]: item for item in self._integration_config_service.mcp_server_status()
        }
        skills = {item["skill"]: item for item in self._integration_config_service.skill_status()}

        if "jira" in normalized and "jira" not in mcp_servers:
            proposals.append(
                CapabilityProposal(
                    name="jira",
                    reason="检测到 Jira 任务关键词，但当前没有 Jira MCP 配置",
                    source="mcp_catalog",
                )
            )

        if "ci" in normalized and "gh-fix-ci" not in skills:
            proposals.append(
                CapabilityProposal(
                    name="gh-fix-ci",
                    reason="检测到 CI 相关问题，但 gh-fix-ci skill 未安装或未启用",
                    source="skills_catalog",
                )
            )

        return proposals
