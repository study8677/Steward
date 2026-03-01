"""macOS 前台窗口传感器：周期采集并上报屏幕上下文事件。"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass

import httpx


@dataclass(slots=True)
class FrontmostWindow:
    """前台窗口快照。"""

    app_name: str
    window_title: str


class MacScreenSensor:
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
        self._base_url = base_url.rstrip("/")
        self._interval_seconds = max(2.0, interval_seconds)
        self._http_timeout_seconds = max(5.0, http_timeout_seconds)
        self._webhook_token = webhook_token.strip()
        self._actor = actor.strip() or "macos-screen-sensor"
        self._last_signature = ""

    def run_forever(self) -> None:
        """持续采集并上报。"""
        print(
            f"[screen-sensor] started, interval={self._interval_seconds}s, "
            f"target={self._base_url}/api/v1/webhooks/screen"
        )
        while True:
            try:
                snapshot = self._read_frontmost_window()
                signature = f"{snapshot.app_name}::{snapshot.window_title}"
                if signature and signature != self._last_signature:
                    self._send_event(snapshot)
                    self._last_signature = signature
            except KeyboardInterrupt:
                print("\n[screen-sensor] stopped by user")
                return
            except Exception as error:  # noqa: BLE001
                print(f"[screen-sensor] warn: {type(error).__name__}: {error}")

            time.sleep(self._interval_seconds)

    def _read_frontmost_window(self) -> FrontmostWindow:
        """读取当前前台应用与窗口标题。"""
        # 通过 System Events 读取前台进程，若无窗口标题则返回空字符串。
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

    def _send_event(self, snapshot: FrontmostWindow) -> None:
        """将屏幕信号写入 Steward 事件链。"""
        title = snapshot.window_title[:120]
        summary = f"前台窗口变化: app={snapshot.app_name}, title={title or '-'}"
        payload = {
            "source_ref": f"screen:{snapshot.app_name}:{title[:48]}",
            "summary": summary,
            "actor": self._actor,
            "entities": [snapshot.app_name, title] if title else [snapshot.app_name],
            "confidence": 0.62,
        }
        headers = {"Content-Type": "application/json"}
        if self._webhook_token:
            headers["x-steward-webhook-token"] = self._webhook_token

        try:
            with httpx.Client(timeout=self._http_timeout_seconds, trust_env=False) as client:
                response = client.post(
                    f"{self._base_url}/api/v1/webhooks/screen",
                    content=json.dumps(payload),
                    headers=headers,
                )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise RuntimeError(f"webhook_http_{error.response.status_code}") from error
        except httpx.TimeoutException as error:
            raise RuntimeError("webhook_timeout") from error
        except httpx.HTTPError as error:
            raise RuntimeError("webhook_unreachable") from error

        print(f"[screen-sensor] ingested: {snapshot.app_name} | {title or '-'}")


def main() -> None:
    """命令行入口。"""
    base_url = os.getenv("STEWARD_SCREEN_SENSOR_BASE_URL", "http://127.0.0.1:8000")
    interval_raw = os.getenv("STEWARD_SCREEN_SENSOR_INTERVAL_SECONDS", "8")
    http_timeout_raw = os.getenv("STEWARD_SCREEN_SENSOR_HTTP_TIMEOUT_SECONDS", "35")
    webhook_token = os.getenv("STEWARD_SCREEN_WEBHOOK_TOKEN", "")
    actor = os.getenv("STEWARD_SCREEN_SENSOR_ACTOR", os.getenv("USER", "macos"))

    try:
        interval_seconds = float(interval_raw)
    except ValueError:
        interval_seconds = 8.0
    try:
        http_timeout_seconds = float(http_timeout_raw)
    except ValueError:
        http_timeout_seconds = 35.0

    sensor = MacScreenSensor(
        base_url=base_url,
        interval_seconds=interval_seconds,
        http_timeout_seconds=http_timeout_seconds,
        webhook_token=webhook_token,
        actor=actor,
    )
    sensor.run_forever()


if __name__ == "__main__":
    main()
