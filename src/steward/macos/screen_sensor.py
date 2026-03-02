"""兼容模块：macOS 屏幕传感器已迁移到跨平台实现。"""

from steward.screen_sensor.base import FrontmostWindow
from steward.screen_sensor.cli import main
from steward.screen_sensor.macos import MacScreenSensor

__all__ = ["FrontmostWindow", "MacScreenSensor", "main"]
