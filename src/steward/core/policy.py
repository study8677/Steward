"""策略配置加载模块。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class PolicyLoader:
    """按需加载 YAML 策略配置。"""

    def __init__(self, policy_path: Path) -> None:
        self._policy_path = policy_path
        self._cache: dict[str, Any] | None = None

    def load(self) -> dict[str, Any]:
        """读取并缓存策略配置。"""
        if self._cache is not None:
            return self._cache

        if not self._policy_path.exists():
            self._cache = {}
            return self._cache

        self._cache = yaml.safe_load(self._policy_path.read_text(encoding="utf-8")) or {}
        return self._cache

    def get(self, section: str, default: Any = None) -> Any:
        """按 section 读取配置。"""
        return self.load().get(section, default)
