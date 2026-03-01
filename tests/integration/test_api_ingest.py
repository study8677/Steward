"""API 集成测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_ingest_event_and_list_spaces(client: TestClient) -> None:
    """写入事件后应能查询空间。"""
    payload = {
        "summary": "请跟进 README 的改造计划",
        "source": "manual",
        "source_ref": "workspace:readme",
        "entities": ["README.md", "steward"],
        "confidence": 0.91,
    }

    response = client.post("/api/v1/events/ingest", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["event_id"]
    assert data["space_id"].startswith("SPACE_")
    assert data["task_id"]
    assert data["plan_id"]

    spaces_response = client.get("/api/v1/spaces")
    assert spaces_response.status_code == 200
    spaces = spaces_response.json()["items"]
    assert len(spaces) >= 1


def test_health_and_metrics(client: TestClient) -> None:
    """健康检查与指标接口应可访问。"""
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200
    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200
    assert "steward_event_ingested_total" in metrics_response.text
    dashboard_response = client.get("/api/v1/dashboard/overview")
    assert dashboard_response.status_code == 200


def test_ingest_event_with_natural_language(client: TestClient) -> None:
    """自然语言事件接口应可直接入链。"""
    response = client.post(
        "/api/v1/events/ingest-nl",
        json={
            "text": "客户在 Slack 催本周交付，请帮我先整理回复草稿。",
            "source_hint": "manual",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["plan_id"]
    assert body["gate_result"] in {"auto", "brief", "confirm", "blocked"}


def test_dashboard_logs_endpoint(client: TestClient) -> None:
    """运行日志接口应返回可展示条目。"""
    client.post(
        "/api/v1/events/ingest",
        json={
            "summary": "写一条日志用于 dashboard 展示",
            "source": "manual",
            "source_ref": "manual:log-test",
            "entities": ["log"],
            "confidence": 0.9,
        },
    )
    response = client.get("/api/v1/dashboard/logs")
    assert response.status_code == 200
    items = response.json().get("items", [])
    assert isinstance(items, list)
