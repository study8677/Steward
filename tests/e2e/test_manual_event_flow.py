"""端到端流程测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_manual_event_to_brief_and_confirm(client: TestClient) -> None:
    """验证手动事件->计划->简报->确认执行闭环。"""
    low_payload = {
        "summary": "跟进团队文档同步",
        "source": "manual",
        "source_ref": "doc:sync",
        "entities": ["docs", "sync"],
        "confidence": 0.88,
    }
    low_result = client.post("/api/v1/events/ingest", json=low_payload)
    assert low_result.status_code == 200
    assert low_result.json()["gate_result"] in {"auto", "brief", "confirm"}

    high_payload = {
        "summary": "对外承诺并付款，属于不可逆动作",
        "source": "manual",
        "source_ref": "finance:commitment",
        "entities": ["payment", "contract"],
        "confidence": 0.95,
    }
    high_result = client.post("/api/v1/events/ingest", json=high_payload)
    assert high_result.status_code == 200
    assert high_result.json()["gate_result"] == "confirm"

    plan_id = high_result.json()["plan_id"]
    confirm_result = client.post(f"/api/v1/plans/{plan_id}/confirm")
    assert confirm_result.status_code == 200
    assert confirm_result.json()["state"] in {"RUNNING", "SUCCEEDED", "WAITING", "FAILED", "GATED"}

    brief_result = client.get("/api/v1/briefs/latest")
    assert brief_result.status_code == 200
    body = brief_result.json()
    assert "Steward Brief" in body["markdown"]
    assert len(body["sections"]) >= 4

    feedback_result = client.post(
        "/api/v1/feedback",
        json={"plan_id": plan_id, "feedback_type": "approve", "note": "looks good"},
    )
    assert feedback_result.status_code == 200
    assert feedback_result.json()["plan_id"] == plan_id
