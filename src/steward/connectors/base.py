"""Connector 抽象接口定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(slots=True)
class ConnectorHealth:
    """连接器健康状态。"""

    healthy: bool
    code: str = "ok"
    message: str = ""


@dataclass(slots=True)
class ExecutionResult:
    """连接器动作执行结果。"""

    success: bool
    reversible: bool
    detail: str = ""
    data: dict[str, object] = field(default_factory=dict)


class Connector(Protocol):
    """统一连接器协议。"""

    name: str

    async def capabilities(self) -> list[str]:
        """返回该连接器支持的动作。"""

    async def required_scopes(self) -> list[str]:
        """返回最小授权范围。"""

    async def pull(self, cursor: str | None) -> list[dict[str, object]]:
        """增量拉取外部事件。"""

    async def execute(self, action: dict[str, object]) -> ExecutionResult:
        """执行动作并返回结果。"""

    async def health(self) -> ConnectorHealth:
        """返回健康状态。"""
