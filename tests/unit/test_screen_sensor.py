"""跨平台屏幕传感器单元测试。"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from steward.screen_sensor.base import BaseScreenSensor, FrontmostWindow
from steward.screen_sensor.cli import build_screen_sensor
from steward.screen_sensor.linux import LinuxScreenSensor
from steward.screen_sensor.macos import MacScreenSensor
from steward.screen_sensor.windows import WindowsScreenSensor


class DummySensor(BaseScreenSensor):
    """用于测试去重逻辑的假传感器。"""

    def __init__(self, snapshots: list[FrontmostWindow]) -> None:
        super().__init__(
            base_url="http://127.0.0.1:8000",
            interval_seconds=8.0,
            http_timeout_seconds=30.0,
            webhook_token="",
            actor="tester",
            platform_tag="dummy",
        )
        self._snapshots = list(snapshots)
        self.sent: list[FrontmostWindow] = []

    def _read_frontmost_window(self) -> FrontmostWindow:
        if not self._snapshots:
            return FrontmostWindow(app_name="", window_title="")
        return self._snapshots.pop(0)

    def _send_event(self, snapshot: FrontmostWindow) -> None:
        self.sent.append(snapshot)


def test_collect_once_deduplicates_same_window() -> None:
    """同一窗口签名连续出现时应只上报一次。"""
    sensor = DummySensor(
        snapshots=[
            FrontmostWindow(app_name="Code", window_title="README.md"),
            FrontmostWindow(app_name="Code", window_title="README.md"),
            FrontmostWindow(app_name="Code", window_title="agent.md"),
        ]
    )

    assert sensor.collect_once() is True
    assert sensor.collect_once() is False
    assert sensor.collect_once() is True
    assert len(sensor.sent) == 2


def test_build_screen_sensor_selects_platform_impl(monkeypatch: pytest.MonkeyPatch) -> None:
    """不同系统应构建对应传感器实现。"""
    monkeypatch.delenv("STEWARD_SCREEN_SENSOR_PLATFORM", raising=False)

    darwin_sensor = build_screen_sensor(system_name="Darwin")
    windows_sensor = build_screen_sensor(system_name="Windows")
    linux_sensor = build_screen_sensor(system_name="Linux")

    assert isinstance(darwin_sensor, MacScreenSensor)
    assert isinstance(windows_sensor, WindowsScreenSensor)
    assert isinstance(linux_sensor, LinuxScreenSensor)


def test_build_screen_sensor_with_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """环境变量应覆盖自动平台识别。"""
    monkeypatch.setenv("STEWARD_SCREEN_SENSOR_PLATFORM", "windows")
    sensor = build_screen_sensor(system_name="Darwin")
    assert isinstance(sensor, WindowsScreenSensor)


def test_build_screen_sensor_unsupported_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    """未知系统应明确报错。"""
    monkeypatch.delenv("STEWARD_SCREEN_SENSOR_PLATFORM", raising=False)
    with pytest.raises(RuntimeError, match="unsupported_platform"):
        build_screen_sensor(system_name="freebsd")


def test_linux_parse_xprop_detail() -> None:
    """Linux xprop 输出应正确提取应用名与标题。"""
    sensor = LinuxScreenSensor(
        base_url="http://127.0.0.1:8000",
        interval_seconds=8.0,
        http_timeout_seconds=30.0,
        webhook_token="",
        actor="tester",
    )
    app_name, title = sensor._parse_xprop_detail(
        "\n".join(
            [
                '_NET_WM_NAME(UTF8_STRING) = "README.md - Steward - Visual Studio Code"',
                'WM_CLASS(STRING) = "code", "Code"',
            ]
        )
    )
    assert app_name == "Code"
    assert title.startswith("README.md")


@respx.mock
def test_send_event_payload_contains_platform_tag() -> None:
    """上报 payload 应带平台标记，便于跨平台来源识别。"""
    route = respx.post("http://127.0.0.1:8000/api/v1/webhooks/screen").mock(
        return_value=httpx.Response(200)
    )
    sensor = MacScreenSensor(
        base_url="http://127.0.0.1:8000",
        interval_seconds=8.0,
        http_timeout_seconds=30.0,
        webhook_token="",
        actor="tester",
    )
    sensor._send_event(FrontmostWindow(app_name="Code", window_title="README.md"))

    assert route.called
    request = route.calls.last.request
    payload = json.loads(request.content.decode("utf-8"))
    assert payload["source_ref"].startswith("screen:macos:Code")
    assert "macos" in payload["entities"]
