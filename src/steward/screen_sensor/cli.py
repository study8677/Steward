"""跨平台屏幕传感器命令行入口。"""

from __future__ import annotations

import getpass
import os
import platform

from steward.screen_sensor.base import BaseScreenSensor
from steward.screen_sensor.linux import LinuxScreenSensor
from steward.screen_sensor.macos import MacScreenSensor
from steward.screen_sensor.windows import WindowsScreenSensor


def _parse_positive_float(raw: str, default: float) -> float:
    """解析浮点环境变量并回退到默认值。"""
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def build_screen_sensor(system_name: str | None = None) -> BaseScreenSensor:
    """根据当前系统构建对应的屏幕传感器。"""
    base_url = os.getenv("STEWARD_SCREEN_SENSOR_BASE_URL", "http://127.0.0.1:8000")
    interval_seconds = _parse_positive_float(
        os.getenv("STEWARD_SCREEN_SENSOR_INTERVAL_SECONDS", "8"),
        8.0,
    )
    http_timeout_seconds = _parse_positive_float(
        os.getenv("STEWARD_SCREEN_SENSOR_HTTP_TIMEOUT_SECONDS", "35"),
        35.0,
    )
    webhook_token = os.getenv("STEWARD_SCREEN_WEBHOOK_TOKEN", "")

    resolved_system = (
        os.getenv("STEWARD_SCREEN_SENSOR_PLATFORM") or system_name or platform.system()
    ).strip()
    normalized_system = resolved_system.lower()
    default_actor = getpass.getuser().strip() or normalized_system or "screen-sensor"
    actor = os.getenv("STEWARD_SCREEN_SENSOR_ACTOR", default_actor)

    sensor_kwargs = {
        "base_url": base_url,
        "interval_seconds": interval_seconds,
        "http_timeout_seconds": http_timeout_seconds,
        "webhook_token": webhook_token,
        "actor": actor,
    }
    if normalized_system in {"darwin", "mac", "macos"}:
        return MacScreenSensor(**sensor_kwargs)
    if normalized_system in {"windows", "win32"}:
        return WindowsScreenSensor(**sensor_kwargs)
    if normalized_system == "linux":
        return LinuxScreenSensor(**sensor_kwargs)
    raise RuntimeError(f"unsupported_platform:{resolved_system or 'unknown'}")


def main() -> None:
    """命令行入口。"""
    sensor = build_screen_sensor()
    sensor.run_forever()


if __name__ == "__main__":
    main()
