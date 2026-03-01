"""手动输入连接器，用于本地注入事件或执行占位动作。"""

from __future__ import annotations

from steward.connectors.base import ConnectorHealth, ExecutionResult


class ManualConnector:
    """手动连接器实现。"""

    name = "manual"

    async def capabilities(self) -> list[str]:
        """返回支持能力。"""
        return ["record_note", "noop"]

    async def required_scopes(self) -> list[str]:
        """手动连接器不需要额外授权。"""
        return []

    async def pull(self, cursor: str | None) -> list[dict[str, object]]:
        """手动连接器不主动拉取。"""
        _ = cursor
        return []

    async def execute(self, action: dict[str, object]) -> ExecutionResult:
        """执行占位动作并直接成功。"""
        action_type = str(action.get("action_type", "noop"))
        return ExecutionResult(success=True, reversible=True, detail=f"manual:{action_type}")

    async def health(self) -> ConnectorHealth:
        """返回健康状态。"""
        return ConnectorHealth(healthy=True)
