"""Linux 屏幕传感器实现。"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from steward.screen_sensor.base import BaseScreenSensor, FrontmostWindow

_WINDOW_ID_PATTERN = re.compile(r"0x[0-9a-fA-F]+")
_QUOTED_VALUE_PATTERN = re.compile(r'"([^"]*)"')


class LinuxScreenSensor(BaseScreenSensor):
    """通过 X11 工具读取前台窗口并回传 Steward Webhook。"""

    def __init__(
        self,
        *,
        base_url: str,
        interval_seconds: float,
        http_timeout_seconds: float,
        webhook_token: str,
        actor: str,
    ) -> None:
        super().__init__(
            base_url=base_url,
            interval_seconds=interval_seconds,
            http_timeout_seconds=http_timeout_seconds,
            webhook_token=webhook_token,
            actor=actor,
            platform_tag="linux",
        )

    def _read_frontmost_window(self) -> FrontmostWindow:
        """读取当前前台应用与窗口标题。"""
        xprop_error: RuntimeError | None = None
        if self._is_x11_env() and shutil.which("xprop"):
            try:
                return self._read_with_xprop()
            except RuntimeError as error:
                xprop_error = error
        if self._is_x11_env() and shutil.which("xdotool"):
            try:
                return self._read_with_xdotool()
            except RuntimeError:
                pass

        if xprop_error is not None:
            raise xprop_error
        if os.getenv("WAYLAND_DISPLAY") and not self._is_x11_env():
            raise RuntimeError("wayland_no_x11_bridge")
        raise RuntimeError("linux_window_tools_missing")

    def _read_with_xprop(self) -> FrontmostWindow:
        """通过 xprop 读取前台窗口。"""
        active_result = subprocess.run(
            ["xprop", "-root", "_NET_ACTIVE_WINDOW"],
            check=False,
            capture_output=True,
            text=True,
        )
        if active_result.returncode != 0:
            message = active_result.stderr.strip() or "xprop_active_window_failed"
            raise RuntimeError(message)
        match = _WINDOW_ID_PATTERN.search(active_result.stdout)
        if match is None or match.group(0).lower() == "0x0":
            raise RuntimeError("active_window_unavailable")
        window_id = match.group(0)

        detail_result = subprocess.run(
            ["xprop", "-id", window_id, "_NET_WM_NAME", "WM_NAME", "WM_CLASS"],
            check=False,
            capture_output=True,
            text=True,
        )
        if detail_result.returncode != 0:
            message = detail_result.stderr.strip() or "xprop_window_detail_failed"
            raise RuntimeError(message)

        app_name, title = self._parse_xprop_detail(detail_result.stdout)
        if not app_name and not title:
            raise RuntimeError("window_metadata_unavailable")
        return FrontmostWindow(app_name=app_name or "unknown-app", window_title=title)

    def _read_with_xdotool(self) -> FrontmostWindow:
        """通过 xdotool 读取前台窗口。"""
        window_result = subprocess.run(
            ["xdotool", "getactivewindow"],
            check=False,
            capture_output=True,
            text=True,
        )
        if window_result.returncode != 0:
            message = window_result.stderr.strip() or "xdotool_active_window_failed"
            raise RuntimeError(message)
        window_id = window_result.stdout.strip()
        if not window_id:
            raise RuntimeError("active_window_unavailable")

        title_result = subprocess.run(
            ["xdotool", "getwindowname", window_id],
            check=False,
            capture_output=True,
            text=True,
        )
        if title_result.returncode != 0:
            message = title_result.stderr.strip() or "xdotool_window_name_failed"
            raise RuntimeError(message)
        title = title_result.stdout.strip()

        class_result = subprocess.run(
            ["xdotool", "getwindowclassname", window_id],
            check=False,
            capture_output=True,
            text=True,
        )
        app_name = class_result.stdout.strip() if class_result.returncode == 0 else ""
        if not app_name:
            app_name = self._resolve_process_name(window_id)

        if not app_name and not title:
            raise RuntimeError("window_metadata_unavailable")
        return FrontmostWindow(app_name=app_name or "unknown-app", window_title=title)

    def _resolve_process_name(self, window_id: str) -> str:
        """通过窗口 pid 回退获取进程名。"""
        pid_result = subprocess.run(
            ["xdotool", "getwindowpid", window_id],
            check=False,
            capture_output=True,
            text=True,
        )
        if pid_result.returncode != 0:
            return ""
        pid = pid_result.stdout.strip()
        if not pid:
            return ""

        process_result = subprocess.run(
            ["ps", "-p", pid, "-o", "comm="],
            check=False,
            capture_output=True,
            text=True,
        )
        if process_result.returncode != 0:
            return ""
        return Path(process_result.stdout.strip()).name

    def _parse_xprop_detail(self, output: str) -> tuple[str, str]:
        """解析 xprop 输出并提取 app 与 title。"""
        title = ""
        app_name = ""
        for line in output.splitlines():
            normalized = line.strip()
            if not normalized:
                continue
            if normalized.startswith("_NET_WM_NAME") and not title:
                title = self._parse_xprop_string(normalized)
                continue
            if normalized.startswith("WM_NAME") and not title:
                title = self._parse_xprop_string(normalized)
                continue
            if normalized.startswith("WM_CLASS"):
                classes = _QUOTED_VALUE_PATTERN.findall(normalized)
                if classes:
                    app_name = classes[-1].strip() or classes[0].strip()
        return app_name, title

    def _parse_xprop_string(self, line: str) -> str:
        """解析 xprop 字符串字段。"""
        quoted = _QUOTED_VALUE_PATTERN.findall(line)
        if quoted:
            return quoted[0].strip()
        if "=" not in line:
            return ""
        return line.split("=", maxsplit=1)[-1].strip().strip('"')

    def _is_x11_env(self) -> bool:
        """判断是否可访问 X11 display。"""
        return bool(os.getenv("DISPLAY"))
