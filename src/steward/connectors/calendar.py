"""日历连接器，处理事件同步与日程动作。"""

from __future__ import annotations

from typing import Any

from steward.connectors.base import ConnectorHealth, ExecutionResult


class CalendarConnector:
    """Calendar 连接器。"""

    name = "calendar"

    async def capabilities(self) -> list[str]:
        """返回可执行动作。"""
        return ["create_event", "update_event", "cancel_event"]

    async def required_scopes(self) -> list[str]:
        """返回建议授权范围。"""
        return ["calendar:read", "calendar:write"]

    async def pull(self, cursor: str | None) -> list[dict[str, object]]:
        """首版由 webhook 触发，不做主动拉取。"""
        _ = cursor
        return []

    async def execute(self, action: dict[str, object]) -> ExecutionResult:
        """执行日历动作。"""
        action_type = str(action.get("action_type", "create_event"))
        payload: Any = action.get("payload", {})
        if not isinstance(payload, dict):
            return ExecutionResult(success=False, reversible=True, detail="payload_invalid")

        if action_type not in {"create_event", "update_event", "cancel_event"}:
            return ExecutionResult(success=False, reversible=True, detail="unsupported_action")

        reversible = action_type in {"update_event", "cancel_event"}
        return ExecutionResult(
            success=True, reversible=reversible, detail=f"calendar:{action_type}"
        )

    async def health(self) -> ConnectorHealth:
        """返回健康状态。"""
        return ConnectorHealth(healthy=True)
