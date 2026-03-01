"""真实冲突场景端到端测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_irreversible_conflict_escalates(client: TestClient) -> None:
    """不可逆冲突应升级为 escalate。"""
    first = client.post(
        "/api/v1/events/ingest",
        json={
            "source": "manual",
            "source_ref": "github:issue:42",
            "summary": "等待对方回复后再继续修复",
            "entities": ["issue:42", "frontend"],
            "confidence": 0.9,
        },
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/events/ingest",
        json={
            "source": "manual",
            "source_ref": "github:issue:42",
            "summary": "不可逆：对外承诺付款并立即发送",
            "entities": ["issue:42", "payment"],
            "confidence": 0.95,
        },
    )
    assert second.status_code == 200
    assert second.json()["gate_result"] == "confirm"

    snapshot = client.get("/api/v1/dashboard/snapshot")
    assert snapshot.status_code == 200
    conflicts = snapshot.json().get("open_conflicts", [])
    assert any(item.get("resolution") == "escalate" for item in conflicts)


def test_reversible_conflict_serialize(client: TestClient) -> None:
    """可逆冲突应优先给出 serialize。"""
    first = client.post(
        "/api/v1/events/ingest",
        json={
            "source": "manual",
            "source_ref": "calendar:event:demo",
            "summary": "等待审批后再安排会议",
            "entities": ["calendar:event:demo"],
            "confidence": 0.88,
        },
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/events/ingest",
        json={
            "source": "manual",
            "source_ref": "calendar:event:demo",
            "summary": "更新会议描述并跟进",
            "entities": ["calendar:event:demo"],
            "confidence": 0.9,
        },
    )
    assert second.status_code == 200

    snapshot = client.get("/api/v1/dashboard/snapshot")
    assert snapshot.status_code == 200
    conflicts = snapshot.json().get("open_conflicts", [])
    assert any(item.get("resolution") == "serialize" for item in conflicts)
