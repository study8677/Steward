"""手动输入连接器，用于本地注入事件并记录真实笔记。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from steward.connectors.base import ConnectorHealth, ExecutionResult


class ManualConnector:
    """手动连接器实现。"""

    name = "manual"

    def __init__(self, brain_dir: str = "~/.steward_brain") -> None:
        self._brain_dir = Path(brain_dir).expanduser().resolve()

    async def capabilities(self) -> list[str]:
        """返回支持能力。"""
        return ["record_note"]

    async def required_scopes(self) -> list[str]:
        """手动连接器不需要额外授权。"""
        return []

    async def pull(self, cursor: str | None) -> list[dict[str, object]]:
        """手动连接器不主动拉取。"""
        _ = cursor
        return []

    async def execute(self, action: dict[str, object]) -> ExecutionResult:
        """执行真实记录动作。"""
        action_type = str(action.get("action_type", "record_note"))
        if action_type != "record_note":
            return ExecutionResult(
                success=False,
                reversible=True,
                detail=f"manual_action_not_supported:{action_type}",
            )

        payload = action.get("payload", {})
        if not isinstance(payload, dict):
            return ExecutionResult(success=False, reversible=True, detail="payload_invalid")
        summary = str(payload.get("summary", "")).strip()
        if not summary:
            return ExecutionResult(success=False, reversible=True, detail="summary_required")

        today = datetime.now(UTC).strftime("%Y%m%d")
        timestamp = datetime.now(UTC).strftime("%H:%M:%S")
        journal_path = self._brain_dir / "journal" / f"{today}.md"
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        content = f"\n### {timestamp}\n\n{summary}\n"
        if journal_path.exists():
            journal_path.write_text(
                journal_path.read_text(encoding="utf-8") + content,
                encoding="utf-8",
            )
        else:
            journal_path.write_text(f"# Journal {today}\n{content}", encoding="utf-8")

        return ExecutionResult(
            success=True,
            reversible=True,
            detail=f"manual:record_note:{journal_path.name}",
            data={"path": str(journal_path)},
        )

    async def health(self) -> ConnectorHealth:
        """返回健康状态。"""
        return ConnectorHealth(healthy=True)
