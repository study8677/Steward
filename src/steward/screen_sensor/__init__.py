"""跨平台屏幕传感器模块。"""

from steward.screen_sensor.base import BaseScreenSensor, FrontmostWindow
from steward.screen_sensor.cli import build_screen_sensor, main

__all__ = [
    "BaseScreenSensor",
    "FrontmostWindow",
    "build_screen_sensor",
    "main",
]
