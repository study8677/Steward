"""模型网关路由单元测试。"""

from __future__ import annotations

import pytest

from steward.core.config import Settings
from steward.services.model_gateway import ModelGateway, SpaceCandidate


@pytest.mark.asyncio()
async def test_route_with_heuristic_match() -> None:
    """事件实体重叠时应命中已有空间。"""
    gateway = ModelGateway(Settings(model_api_key=""))
    candidates = [
        SpaceCandidate(space_id="SPACE_A", focus_ref="repo-x", entities=["repo-x", "issue-42"]),
        SpaceCandidate(space_id="SPACE_B", focus_ref="repo-y", entities=["repo-y"]),
    ]

    decision = await gateway.route_space(
        event_summary="请跟进 repo-x 的 issue",
        event_entities=["repo-x", "issue-42"],
        candidates=candidates,
    )

    assert decision.target == "SPACE_A"
    assert decision.confidence >= 0.35


@pytest.mark.asyncio()
async def test_route_with_heuristic_new() -> None:
    """无重叠时应新建空间。"""
    gateway = ModelGateway(Settings(model_api_key=""))
    candidates = [SpaceCandidate(space_id="SPACE_A", focus_ref="foo", entities=["foo"])]

    decision = await gateway.route_space(
        event_summary="全新话题",
        event_entities=["bar"],
        candidates=candidates,
    )

    assert decision.target == "NEW"


@pytest.mark.asyncio()
async def test_summarize_pending_plan_without_model_key() -> None:
    """未配置模型时应返回可读回退摘要。"""
    gateway = ModelGateway(Settings(model_api_key=""))
    summary = await gateway.summarize_pending_plan(
        plan_id="plan-1",
        intent="follow_up",
        risk_level="high",
        priority="P1",
        reversibility="irreversible",
        steps=[
            {
                "connector": "manual",
                "action_type": "record_note",
                "payload": {"summary": "对外承诺并付款"},
            }
        ],
    )
    assert "对外承诺并付款" in summary
    assert "高风险" in summary
