"""简报偏好配置服务。"""

from __future__ import annotations

import json
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from steward.core.config import Settings
from steward.domain.schemas import BriefSettingsResponse


class BriefPreferenceService:
    """管理简报频率与内容层级偏好。"""

    _allowed_levels = {"simple", "medium", "rich"}

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._runtime_path = Path(settings.brief_runtime_file)

    def load_runtime_overrides(self) -> None:
        """从本地持久化文件加载简报偏好。"""
        if not self._runtime_path.exists():
            self._normalize_settings()
            return

        try:
            payload = json.loads(self._runtime_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError, OSError:
            self._normalize_settings()
            return
        if not isinstance(payload, dict):
            self._normalize_settings()
            return

        self._apply_from_payload(payload)
        self._normalize_settings()

    def get_settings(self) -> BriefSettingsResponse:
        """返回当前简报偏好。"""
        self._normalize_settings()
        return BriefSettingsResponse(
            frequency_hours=int(self._settings.brief_window_hours),
            content_level=str(self._settings.brief_content_level),
        )

    def update_settings(
        self,
        *,
        frequency_hours: int | None = None,
        content_level: str | None = None,
    ) -> BriefSettingsResponse:
        """更新简报偏好并持久化。"""
        if frequency_hours is not None:
            self._settings.brief_window_hours = max(1, min(24, int(frequency_hours)))

        if content_level is not None:
            normalized_level = str(content_level).strip().lower()
            if normalized_level in self._allowed_levels:
                self._settings.brief_content_level = normalized_level

        self._normalize_settings()
        self._persist_runtime()
        return self.get_settings()

    def _apply_from_payload(self, payload: dict[str, Any]) -> None:
        """应用存储文件中的字段。"""
        frequency_raw = payload.get("frequency_hours")
        if isinstance(frequency_raw, int):
            self._settings.brief_window_hours = frequency_raw
        elif isinstance(frequency_raw, str):
            with suppress(ValueError):
                self._settings.brief_window_hours = int(frequency_raw)

        level_raw = payload.get("content_level")
        if isinstance(level_raw, str):
            self._settings.brief_content_level = level_raw.strip().lower()

    def _normalize_settings(self) -> None:
        """纠正越界或非法设置，确保运行时可用。"""
        self._settings.brief_window_hours = max(1, min(24, int(self._settings.brief_window_hours)))
        current_level = str(self._settings.brief_content_level).strip().lower()
        if current_level not in self._allowed_levels:
            current_level = "medium"
        self._settings.brief_content_level = current_level

    def _persist_runtime(self) -> None:
        """写入简报偏好到本地文件。"""
        self._runtime_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(UTC).isoformat(),
            "frequency_hours": int(self._settings.brief_window_hours),
            "content_level": str(self._settings.brief_content_level),
        }
        self._runtime_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
