"""OpenTelemetry 初始化占位模块。"""

from __future__ import annotations

from steward.core.logging import get_logger

logger = get_logger(component="tracing")


def configure_tracing() -> None:
    """初始化 tracing（首版先保留扩展点）。"""
    logger.info("tracing_initialized", mode="placeholder")
