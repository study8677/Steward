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


@pytest.mark.asyncio()
async def test_summarize_runtime_decisions_without_model_key() -> None:
    """未配置模型时，运行日志摘要应回退为人话而非 reason code。"""
    gateway = ModelGateway(Settings(model_api_key=""))
    summaries = await gateway.summarize_runtime_decisions(
        decisions=[
            {
                "decision_id": "d1",
                "intent": "follow_up",
                "gate_result": "auto",
                "state_from": "GATED",
                "state_to": "GATED",
                "reason": "auto_execution_dispatched:60bf571c-1f3b-41da-b9fc-f8571d31e029",
                "outcome": "succeeded",
                "steps": [
                    {
                        "connector": "manual",
                        "action_type": "record_note",
                        "payload": {"summary": "记录验证笔记"},
                    }
                ],
            }
        ]
    )

    assert "d1" in summaries
    assert "执行队列" in summaries["d1"]
    assert "auto_execution_dispatched" not in summaries["d1"]


@pytest.mark.asyncio()
async def test_plan_event_execution_without_model_key() -> None:
    """未配置模型时，计划生成应返回结构化回退结果。"""
    gateway = ModelGateway(Settings(model_api_key=""))
    planned = await gateway.plan_event_execution(
        event_summary="请跟进这个问题",
        source="manual",
        source_ref="manual:1",
        entities=["issue"],
        default_intent="follow_up",
        default_risk_level="low",
        default_priority="P2",
        default_reversibility="reversible",
        default_requires_confirmation=False,
        candidate_steps=[
            {
                "connector": "manual",
                "action_type": "record_note",
                "payload": {"summary": "请跟进这个问题"},
            }
        ],
    )
    assert planned["intent"] == "follow_up"
    assert planned["risk_level"] == "low"
    assert planned["steps"][0]["connector"] == "manual"


@pytest.mark.asyncio()
async def test_reflect_execution_step_without_model_key() -> None:
    """未配置模型时，执行反思应回退到 continue。"""
    gateway = ModelGateway(Settings(model_api_key=""))
    reflection = await gateway.reflect_execution_step(
        plan_id="p1",
        intent="follow_up",
        step_index=0,
        step={"connector": "manual", "action_type": "record_note", "payload": {}},
        step_success=True,
        step_detail="ok",
        remaining_steps=1,
    )
    assert reflection["decision"] == "continue"
    assert isinstance(reflection["summary"], str)
