"""Webhook 反压服务单元测试。"""

from __future__ import annotations

import pytest

from steward.services.webhook_backpressure import WebhookBackpressureService


@pytest.mark.asyncio()
async def test_backpressure_inflight_limit() -> None:
    """超过并发上限应被拒绝。"""
    service = WebhookBackpressureService(max_inflight_per_provider=1, max_events_per_window=10)

    first = await service.admit("slack", "a")
    assert first.accepted

    second = await service.admit("slack", "b")
    assert not second.accepted
    assert second.reason == "inflight_limited"

    await service.release("slack")
    third = await service.admit("slack", "c")
    assert third.accepted


@pytest.mark.asyncio()
async def test_backpressure_duplicate_detection() -> None:
    """重复 dedup_key 应被识别。"""
    service = WebhookBackpressureService(max_inflight_per_provider=2, max_events_per_window=10)

    first = await service.admit("gmail", "same-id")
    assert first.accepted

    duplicate = await service.admit("gmail", "same-id")
    assert duplicate.duplicate
    assert not duplicate.accepted
