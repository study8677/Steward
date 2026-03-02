"""聊天连接器，处理 IM/协作平台消息动作。"""

from __future__ import annotations

from typing import Any

from steward.connectors.base import ConnectorHealth, ExecutionResult


class ChatConnector:
    """Chat 连接器。"""

    name = "chat"

    def __init__(self, outbound_enabled: bool = False) -> None:
        self._outbound_enabled = outbound_enabled

    async def capabilities(self) -> list[str]:
        """返回可执行动作。"""
        return ["post_message", "reply_thread", "add_reaction"]

    async def required_scopes(self) -> list[str]:
        """返回建议授权范围。"""
        return ["chat:read", "chat:write"]

    async def pull(self, cursor: str | None) -> list[dict[str, object]]:
        """当前走 webhook 驱动。"""
        _ = cursor
        return []

    async def execute(self, action: dict[str, object]) -> ExecutionResult:
        """执行聊天动作。"""
        action_type = str(action.get("action_type", "post_message"))
        payload: Any = action.get("payload", {})
        if not isinstance(payload, dict):
            return ExecutionResult(success=False, reversible=True, detail="payload_invalid")

        if action_type not in {"post_message", "reply_thread", "add_reaction"}:
            return ExecutionResult(success=False, reversible=True, detail="unsupported_action")

        if action_type in {"post_message", "reply_thread"} and not self._outbound_enabled:
            return ExecutionResult(success=False, reversible=True, detail="outbound_disabled")

        return ExecutionResult(
            success=True, reversible=True, detail=f"chat:{action_type}", data=payload
        )

    async def health(self) -> ConnectorHealth:
        """返回健康状态。"""
        return ConnectorHealth(healthy=True)
