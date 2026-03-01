"""本地环境连接器，当前提供只读信号和白名单动作占位。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from steward.connectors.base import ConnectorHealth, ExecutionResult


class LocalConnector:
    """本地连接器实现。"""

    name = "local"

    async def capabilities(self) -> list[str]:
        """返回支持能力。"""
        return ["collect_file_changes", "run_whitelisted_command"]

    async def required_scopes(self) -> list[str]:
        """本地连接器依赖本地文件访问权限。"""
        return ["local:read"]

    async def pull(self, cursor: str | None) -> list[dict[str, object]]:
        """拉取当前目录下最近文件变化线索。"""
        _ = cursor
        files = [str(path) for path in Path.cwd().glob("*.md")][:20]
        if not files:
            return []
        return [
            {
                "source": "local",
                "summary": f"检测到本地文档文件 {len(files)} 个。",
                "entities": files,
            }
        ]

    async def execute(self, action: dict[str, object]) -> ExecutionResult:
        """执行白名单动作占位逻辑。"""
        action_type = str(action.get("action_type", "noop"))
        if action_type != "run_whitelisted_command":
            return ExecutionResult(success=True, reversible=True, detail=f"local:{action_type}")

        payload: Any = action.get("payload", {})
        if not isinstance(payload, dict):
            return ExecutionResult(success=False, reversible=True, detail="payload_invalid")

        command = str(payload.get("command", ""))
        if command not in {"echo", "true"}:
            return ExecutionResult(success=False, reversible=True, detail="command_not_allowed")
        return ExecutionResult(success=True, reversible=True, detail=f"command:{command}")

    async def health(self) -> ConnectorHealth:
        """返回健康状态。"""
        return ConnectorHealth(healthy=True)
