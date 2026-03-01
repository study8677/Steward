"""macOS 屏幕传感器实现。"""

from __future__ import annotations

import subprocess

from steward.screen_sensor.base import BaseScreenSensor, FrontmostWindow


class MacScreenSensor(BaseScreenSensor):
    """通过 AppleScript 采集前台窗口并回传 Steward Webhook。"""

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
            platform_tag="macos",
        )

    def _read_frontmost_window(self) -> FrontmostWindow:
        """读取当前前台应用与窗口标题。"""
        script = """
        tell application "System Events"
          set frontApp to name of first application process whose frontmost is true
          set windowTitle to ""
          tell process frontApp
            try
              set windowTitle to name of front window
            end try
          end tell
        end tell
        return frontApp & "||" & windowTitle
        """
        result = subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or "osascript_failed"
            raise RuntimeError(message)

        raw = result.stdout.strip()
        if "||" in raw:
            app_name, window_title = raw.split("||", maxsplit=1)
        else:
            app_name, window_title = raw, ""
        return FrontmostWindow(app_name=app_name.strip(), window_title=window_title.strip())
