"""屏幕信号连接器，接收屏幕传感器事件并提供只读能力。"""

from __future__ import annotations

from steward.connectors.base import ConnectorHealth, ExecutionResult


class ScreenConnector:
    """Screen 连接器。"""

    name = "screen"

    async def capabilities(self) -> list[str]:
        """返回支持能力。"""
        return ["collect_screen_signal"]

    async def required_scopes(self) -> list[str]:
        """返回建议授权范围。"""
        return ["screen:read"]

    async def pull(self, cursor: str | None) -> list[dict[str, object]]:
        """依赖外部上报，不主动拉取。"""
        _ = cursor
        return []

    async def execute(self, action: dict[str, object]) -> ExecutionResult:
        """屏幕连接器默认只读，不执行写动作。"""
        action_type = str(action.get("action_type", "collect_screen_signal"))
        if action_type != "collect_screen_signal":
            return ExecutionResult(success=False, reversible=True, detail="screen_read_only")
        return ExecutionResult(success=True, reversible=True, detail="screen:signal_collected")

    async def health(self) -> ConnectorHealth:
        """返回健康状态。"""
        return ConnectorHealth(healthy=True)
