"""macOS Menu Bar 应用：展示待确认计划并支持一键确认/拒绝。"""

from __future__ import annotations

import os
import webbrowser
from typing import Any

import requests

try:
    import rumps
except ImportError:  # pragma: no cover - 仅在未安装 macOS 依赖时触发
    rumps = None


class StewardMenuBarApp:
    """托盘壳层，封装菜单刷新与动作执行。"""

    def __init__(self, base_url: str, refresh_seconds: int = 15) -> None:
        if rumps is None:
            raise RuntimeError("请先安装 macOS 依赖：uv sync --extra dev --extra macos")

        self._base_url = base_url.rstrip("/")
        self._refresh_seconds = max(5, refresh_seconds)

        self._app = rumps.App("Steward", quit_button=None)
        self._pending_menu = rumps.MenuItem("待确认计划")
        self._status_menu = rumps.MenuItem("状态：初始化")
        # 记录上次快照，用于仅在“新增待确认/新增冲突”时弹系统通知，避免重复打扰。
        self._last_pending_ids: set[str] = set()
        self._last_conflict_ids: set[str] = set()
        self._first_snapshot = True
        self._last_fetch_ok = False

        self._app.menu = [
            self._status_menu,
            self._pending_menu,
            None,
            rumps.MenuItem("刷新", callback=self._on_refresh_click),
            rumps.MenuItem("打开 Dashboard", callback=self._on_open_dashboard),
            rumps.MenuItem("退出", callback=self._on_quit),
        ]

        self._timer = rumps.Timer(self._on_timer, self._refresh_seconds)

    def run(self) -> None:
        """启动托盘应用。"""
        self._refresh_snapshot()
        self._timer.start()
        self._app.run()

    def _on_timer(self, _sender: Any) -> None:
        """定时刷新回调。"""
        self._refresh_snapshot()

    def _on_refresh_click(self, _sender: Any) -> None:
        """手动刷新回调。"""
        self._refresh_snapshot()

    def _on_open_dashboard(self, _sender: Any) -> None:
        """打开 Dashboard 页面。"""
        webbrowser.open(f"{self._base_url}/dashboard")

    def _on_quit(self, _sender: Any) -> None:
        """退出应用。"""
        if rumps is None:
            return
        rumps.quit_application()

    def _refresh_snapshot(self) -> None:
        """拉取快照并刷新菜单。"""
        try:
            response = requests.get(f"{self._base_url}/api/v1/dashboard/snapshot", timeout=4)
            response.raise_for_status()
            snapshot = response.json()
            if not self._last_fetch_ok:
                self._notify("Steward 已连接", "后端恢复可用")
            self._last_fetch_ok = True
        except Exception as exc:  # noqa: BLE001
            self._status_menu.title = f"状态：连接失败 ({type(exc).__name__})"
            self._pending_menu.clear()
            self._pending_menu.add(rumps.MenuItem("无法拉取待确认计划"))
            self._app.title = "Steward !"
            if self._last_fetch_ok:
                self._notify("Steward 连接中断", "请检查后端服务是否运行")
            self._last_fetch_ok = False
            return

        pending = snapshot.get("pending_confirmations", [])
        if not isinstance(pending, list):
            pending = []

        open_conflicts = snapshot.get("open_conflicts", [])
        conflict_count = len(open_conflicts) if isinstance(open_conflicts, list) else 0
        self._status_menu.title = f"状态：待确认 {len(pending)} / 冲突 {conflict_count}"

        self._app.title = f"Steward ({len(pending)})" if pending else "Steward"
        self._render_pending_menu(pending)
        self._notify_for_changes(
            pending, open_conflicts if isinstance(open_conflicts, list) else []
        )

    def _render_pending_menu(self, pending: list[dict[str, Any]]) -> None:
        """渲染待确认计划菜单。"""
        self._pending_menu.clear()
        if not pending:
            self._pending_menu.add(rumps.MenuItem("暂无待确认计划"))
            return

        max_items = 6
        for item in pending[:max_items]:
            plan_id = str(item.get("plan_id", ""))
            risk_level = str(item.get("risk_level", "low"))
            state = str(item.get("state", "GATED"))
            human_summary = str(item.get("human_summary", ""))
            short_plan = plan_id[:8] if plan_id else "unknown"

            self._pending_menu.add(rumps.MenuItem(f"{short_plan} | {risk_level} | {state}"))
            if human_summary:
                self._pending_menu.add(rumps.MenuItem(f"  {human_summary[:44]}"))
            self._pending_menu.add(
                rumps.MenuItem(
                    f"  ✓ 确认 {short_plan}",
                    callback=self._build_plan_callback(plan_id, "confirm"),
                )
            )
            self._pending_menu.add(
                rumps.MenuItem(
                    f"  ✕ 拒绝 {short_plan}",
                    callback=self._build_plan_callback(plan_id, "reject"),
                )
            )

        if len(pending) > max_items:
            self._pending_menu.add(
                rumps.MenuItem(f"... 其余 {len(pending) - max_items} 条请在 Dashboard 查看")
            )

    def _build_plan_callback(self, plan_id: str, action: str):
        """构建确认/拒绝回调。"""

        def _callback(_sender: Any) -> None:
            self._perform_plan_action(plan_id, action)

        return _callback

    def _perform_plan_action(self, plan_id: str, action: str) -> None:
        """执行计划确认或拒绝。"""
        if action not in {"confirm", "reject"}:
            return

        try:
            response = requests.post(
                f"{self._base_url}/api/v1/plans/{plan_id}/{action}",
                timeout=4,
            )
            response.raise_for_status()
            result = response.json()
            state = str(result.get("state", "unknown"))
            self._status_menu.title = f"状态：{action} 成功 -> {state}"
            self._notify("Steward 已处理计划", f"{action} {plan_id[:8]} -> {state}")
        except Exception as exc:  # noqa: BLE001
            self._status_menu.title = f"状态：{action} 失败 ({type(exc).__name__})"
            self._notify(
                "Steward 计划处理失败", f"{action} {plan_id[:8]} 失败: {type(exc).__name__}"
            )

        self._refresh_snapshot()

    def _notify_for_changes(
        self,
        pending: list[dict[str, Any]],
        open_conflicts: list[dict[str, Any]],
    ) -> None:
        """在关键变化时触发系统通知。"""
        pending_ids = {str(item.get("plan_id", "")) for item in pending if item.get("plan_id")}
        conflict_ids = {
            str(item.get("conflict_id", "")) for item in open_conflicts if item.get("conflict_id")
        }

        if self._first_snapshot:
            self._last_pending_ids = pending_ids
            self._last_conflict_ids = conflict_ids
            self._first_snapshot = False
            return

        new_pending = pending_ids - self._last_pending_ids
        new_conflicts = conflict_ids - self._last_conflict_ids

        if new_pending:
            self._notify(
                "Steward 有新待确认计划",
                f"新增 {len(new_pending)} 条，请在菜单栏或 Dashboard 处理",
            )
        if new_conflicts:
            self._notify(
                "Steward 检测到新冲突",
                f"新增 {len(new_conflicts)} 条冲突，请尽快确认策略",
            )

        self._last_pending_ids = pending_ids
        self._last_conflict_ids = conflict_ids

    def _notify(self, title: str, message: str) -> None:
        """发送 macOS 系统通知。"""
        if rumps is None:
            return
        try:
            rumps.notification(title=title, subtitle="Steward", message=message)
        except Exception:  # noqa: BLE001
            # 通知失败不影响主流程。
            return


def main() -> None:
    """命令行入口。"""
    base_url = os.getenv("STEWARD_MENUBAR_BASE_URL", "http://127.0.0.1:8000")
    refresh_seconds_raw = os.getenv("STEWARD_MENUBAR_REFRESH_SECONDS", "15")
    try:
        refresh_seconds = int(refresh_seconds_raw)
    except ValueError:
        refresh_seconds = 15

    app = StewardMenuBarApp(base_url=base_url, refresh_seconds=refresh_seconds)
    app.run()
