"""模型路由 Prompt 与 JSON 解析测试。"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from steward.core.config import Settings
from steward.services.model_gateway import ModelGateway, SpaceCandidate


@pytest.mark.asyncio()
@respx.mock
async def test_route_with_model_json_output() -> None:
    """模型返回 JSON 时应按约束解析。"""
    respx.post("https://model.example/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"target":"SPACE_A","confidence":0.91,"reason":"实体重叠"}'
                        }
                    }
                ]
            },
        )
    )

    gateway = ModelGateway(
        Settings(
            model_api_key="token",
            model_base_url="https://model.example",
            model_router_min_confidence=0.7,
        )
    )
    decision = await gateway.route_space(
        event_summary="请继续跟进 issue-42",
        event_entities=["issue-42"],
        candidates=[SpaceCandidate(space_id="SPACE_A", focus_ref="repo", entities=["issue-42"])],
    )

    assert decision.target == "SPACE_A"
    assert decision.confidence == pytest.approx(0.91, rel=0.01)


@pytest.mark.asyncio()
@respx.mock
async def test_route_with_model_low_confidence_fallback_to_new() -> None:
    """低置信输出应自动降级到 NEW。"""
    respx.post("https://model.example/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"target":"SPACE_A","confidence":0.42,"reason":"证据不足"}'
                        }
                    }
                ]
            },
        )
    )

    gateway = ModelGateway(
        Settings(
            model_api_key="token",
            model_base_url="https://model.example",
            model_router_min_confidence=0.7,
        )
    )
    decision = await gateway.route_space(
        event_summary="新话题",
        event_entities=["none"],
        candidates=[SpaceCandidate(space_id="SPACE_A", focus_ref="repo", entities=["issue-42"])],
    )

    assert decision.target == "NEW"
    assert decision.reason == "model_low_confidence_fallback_to_new"


@pytest.mark.asyncio()
@respx.mock
async def test_summarize_pending_plan_with_model() -> None:
    """模型可用时应返回模型摘要内容。"""
    respx.post("https://model.example/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "将发送对外承诺信息，涉及高风险不可逆操作，请确认。"}}
                ]
            },
        )
    )
    gateway = ModelGateway(
        Settings(
            model_api_key="token",
            model_base_url="https://model.example",
            model_default="test-model",
        )
    )
    summary = await gateway.summarize_pending_plan(
        plan_id="plan-2",
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
    assert "高风险" in summary


@pytest.mark.asyncio()
@respx.mock
async def test_summarize_executed_plan_prompt_changes_with_level() -> None:
    """执行简报 Prompt 应根据内容层级变化。"""
    route = respx.post("https://model.example/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "已完成跟进并同步结果。"}}]},
        )
    )
    gateway = ModelGateway(
        Settings(
            model_api_key="token",
            model_base_url="https://model.example",
            model_default="test-model",
        )
    )

    await gateway.summarize_executed_plan(
        plan_id="plan-rich",
        intent="follow_up",
        steps=[{"connector": "chat", "action_type": "reply_thread", "payload": {"text": "ok"}}],
        outcome="succeeded",
        reason="none",
        content_level="rich",
    )
    rich_payload = json.loads(route.calls[-1].request.content.decode("utf-8"))
    rich_prompt = str(rich_payload["messages"][1]["content"])
    assert "输出 1-2 句" in rich_prompt

    await gateway.summarize_executed_plan(
        plan_id="plan-simple",
        intent="follow_up",
        steps=[{"connector": "chat", "action_type": "reply_thread", "payload": {"text": "ok"}}],
        outcome="succeeded",
        reason="none",
        content_level="simple",
    )
    simple_payload = json.loads(route.calls[-1].request.content.decode("utf-8"))
    simple_prompt = str(simple_payload["messages"][1]["content"])
    assert "12-28 字" in simple_prompt
