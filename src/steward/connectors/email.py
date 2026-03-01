"""邮件连接器，处理邮件类动作与健康检查。"""

from __future__ import annotations

from typing import Any

from steward.connectors.base import ConnectorHealth, ExecutionResult


class EmailConnector:
    """Email 连接器。"""

    name = "email"

    def __init__(self, outbound_enabled: bool = False) -> None:
        self._outbound_enabled = outbound_enabled

    async def capabilities(self) -> list[str]:
        """返回可执行动作。"""
        return ["create_draft", "send_email", "tag_thread"]

    async def required_scopes(self) -> list[str]:
        """返回建议授权范围。"""
        return ["email:read", "email:write"]

    async def pull(self, cursor: str | None) -> list[dict[str, object]]:
        """首版走 webhook 驱动，不做主动拉取。"""
        _ = cursor
        return []

    async def execute(self, action: dict[str, object]) -> ExecutionResult:
        """执行邮件相关动作。"""
        action_type = str(action.get("action_type", "create_draft"))
        payload: Any = action.get("payload", {})
        if not isinstance(payload, dict):
            return ExecutionResult(success=False, reversible=True, detail="payload_invalid")

        if action_type not in {"create_draft", "send_email", "tag_thread"}:
            return ExecutionResult(success=False, reversible=True, detail="unsupported_action")

        # 首版保留真实发送开关，默认仅写草稿式动作，避免误发。
        if action_type == "send_email" and not self._outbound_enabled:
            return ExecutionResult(success=False, reversible=True, detail="outbound_disabled")

        return ExecutionResult(
            success=True, reversible=True, detail=f"email:{action_type}", data=payload
        )

    async def health(self) -> ConnectorHealth:
        """返回连接器健康状态。"""
        return ConnectorHealth(healthy=True)
