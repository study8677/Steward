"""本地环境连接器（执行路径已下线）。"""

from __future__ import annotations

from steward.connectors.base import ConnectorHealth, ExecutionResult


class LocalConnector:
    """本地连接器实现。"""

    name = "local"

    async def capabilities(self) -> list[str]:
        """返回支持能力。"""
        return []

    async def required_scopes(self) -> list[str]:
        """本地连接器依赖本地文件访问权限。"""
        return ["local:read"]

    async def pull(self, cursor: str | None) -> list[dict[str, object]]:
        """本地连接器不再拉取。"""
        _ = cursor
        return []

    async def execute(self, action: dict[str, object]) -> ExecutionResult:
        """本地执行能力明确禁用。"""
        action_type = str(action.get("action_type", ""))
        return ExecutionResult(
            success=False,
            reversible=True,
            detail=f"local_execution_disabled:{action_type}",
        )

    async def health(self) -> ConnectorHealth:
        """返回健康状态。"""
        return ConnectorHealth(
            healthy=False,
            code="disabled",
            message="local connector execution is disabled by policy",
        )
