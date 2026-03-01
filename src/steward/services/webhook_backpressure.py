"""Webhook 反压控制服务。"""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(slots=True)
class BackpressureAdmission:
    """反压准入结果。"""

    accepted: bool
    duplicate: bool
    reason: str


class WebhookBackpressureService:
    """提供并发、速率与去重三层反压保护。"""

    def __init__(
        self,
        *,
        max_inflight_per_provider: int = 12,
        max_events_per_window: int = 120,
        window_seconds: int = 10,
        dedup_ttl_seconds: int = 120,
    ) -> None:
        self._max_inflight_per_provider = max_inflight_per_provider
        self._max_events_per_window = max_events_per_window
        self._window = timedelta(seconds=window_seconds)
        self._dedup_ttl = timedelta(seconds=dedup_ttl_seconds)

        self._lock = asyncio.Lock()
        self._inflight: dict[str, int] = defaultdict(int)
        self._recent_events: dict[str, deque[datetime]] = defaultdict(deque)
        self._dedup_cache: dict[tuple[str, str], datetime] = {}

    async def admit(self, provider: str, dedup_key: str | None) -> BackpressureAdmission:
        """尝试接纳请求。"""
        now = datetime.now(UTC)
        async with self._lock:
            self._cleanup(now)

            if dedup_key:
                dedup_token = (provider, dedup_key)
                if dedup_token in self._dedup_cache:
                    return BackpressureAdmission(
                        accepted=False,
                        duplicate=True,
                        reason="duplicate_event",
                    )

            events = self._recent_events[provider]
            if len(events) >= self._max_events_per_window:
                return BackpressureAdmission(
                    accepted=False,
                    duplicate=False,
                    reason="rate_limited",
                )

            if self._inflight[provider] >= self._max_inflight_per_provider:
                return BackpressureAdmission(
                    accepted=False,
                    duplicate=False,
                    reason="inflight_limited",
                )

            self._inflight[provider] += 1
            events.append(now)
            if dedup_key:
                self._dedup_cache[(provider, dedup_key)] = now + self._dedup_ttl

            return BackpressureAdmission(accepted=True, duplicate=False, reason="admitted")

    async def release(self, provider: str) -> None:
        """释放 in-flight 计数。"""
        async with self._lock:
            current = self._inflight.get(provider, 0)
            self._inflight[provider] = max(0, current - 1)

    def _cleanup(self, now: datetime) -> None:
        """清理窗口和去重缓存。"""
        for _provider, events in self._recent_events.items():
            while events and now - events[0] > self._window:
                events.popleft()

        expired = [key for key, expiry in self._dedup_cache.items() if expiry <= now]
        for key in expired:
            self._dedup_cache.pop(key, None)
