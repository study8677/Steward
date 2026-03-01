"""Webhook 与 Dashboard UI 集成测试。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient


def test_email_webhook_ingest(client: TestClient) -> None:
    """邮件 webhook 应进入统一事件链路。"""
    response = client.post(
        "/api/v1/webhooks/email",
        json={
            "subject": "Re: Sprint review",
            "thread_id": "mail:thread:1",
            "sender": "alice@example.com",
            "entities": ["mail", "sprint"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["space_id"].startswith("SPACE_")


def test_dashboard_snapshot_and_page(client: TestClient) -> None:
    """Dashboard 快照接口与页面应可访问。"""
    snapshot = client.get("/api/v1/dashboard/snapshot")
    assert snapshot.status_code == 200
    body = snapshot.json()
    assert "overview" in body
    assert "connector_health" in body

    dashboard_page = client.get("/dashboard")
    assert dashboard_page.status_code == 200
    assert "Steward Brief Hub" in dashboard_page.text

    integration_page = client.get("/dashboard/integrations")
    assert integration_page.status_code == 200
    assert "信息源管理" in integration_page.text


def test_slack_provider_signature_and_dedup(client: TestClient) -> None:
    """Slack provider 路由应通过签名校验并做重复事件抑制。"""
    payload = {
        "type": "event_callback",
        "event_id": "Ev123",
        "event": {
            "type": "message",
            "channel": "C001",
            "user": "U001",
            "text": "请跟进这个 issue",
            "ts": "1710000000.000200",
        },
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    timestamp = str(int(datetime.now(UTC).timestamp()))
    base = f"v0:{timestamp}:{raw.decode('utf-8')}".encode()
    digest = hmac.new(b"slack-test-secret", base, hashlib.sha256).hexdigest()
    headers = {
        "content-type": "application/json",
        "x-slack-request-timestamp": timestamp,
        "x-slack-signature": f"v0={digest}",
    }

    first = client.post("/api/v1/webhooks/providers/slack", content=raw, headers=headers)
    assert first.status_code == 200

    duplicate = client.post("/api/v1/webhooks/providers/slack", content=raw, headers=headers)
    assert duplicate.status_code == 202


def test_gmail_provider_adapter(client: TestClient) -> None:
    """Gmail provider 路由应能解析 Pub/Sub 包装。"""
    data = base64.urlsafe_b64encode(
        json.dumps({"emailAddress": "alice@example.com", "historyId": "777"}).encode("utf-8")
    ).decode("utf-8")
    payload = {
        "message": {
            "messageId": "gmail-msg-1",
            "data": data,
        },
        "subscription": "projects/demo/subscriptions/steward",
    }
    response = client.post(
        "/api/v1/webhooks/providers/gmail",
        json=payload,
        headers={"authorization": "Bearer gmail-token"},
    )
    assert response.status_code == 200
    assert response.json()["space_id"].startswith("SPACE_")


def test_google_calendar_provider_adapter(client: TestClient) -> None:
    """Google Calendar provider 路由应校验 channel token。"""
    headers = {
        "x-goog-channel-token": "calendar-token",
        "x-goog-channel-id": "channel-1",
        "x-goog-resource-state": "exists",
        "x-goog-resource-id": "resource-1",
        "x-goog-message-number": "8",
    }
    response = client.post(
        "/api/v1/webhooks/providers/google-calendar",
        json={"summary": "明天会议发生更新"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["space_id"].startswith("SPACE_")


def test_integration_status_and_nl_apply(client: TestClient) -> None:
    """信息源配置应支持状态查询与自然语言应用。"""
    before = client.get("/api/v1/integrations")
    assert before.status_code == 200
    providers = before.json().get("providers", [])
    assert any(item.get("provider") == "slack" for item in providers)
    assert any(item.get("provider") == "screen" for item in providers)

    apply_response = client.post(
        "/api/v1/integrations/nl",
        json={
            "text": (
                "帮我接入 Slack signing secret=s-slack-123，"
                "Gmail verification token=gmail-123，"
                "topic=projects/demo/topics/steward-mail，"
                "Calendar channel token=cal-123，"
                "channel ids=channel-a,channel-b"
            )
        },
    )
    assert apply_response.status_code == 200
    body = apply_response.json()
    assert "slack_signing_secret" in body.get("applied_fields", [])

    after = client.get("/api/v1/integrations")
    assert after.status_code == 200
    after_items = after.json().get("providers", [])
    slack = next((item for item in after_items if item.get("provider") == "slack"), None)
    assert slack is not None
    assert bool(slack.get("configured")) is True


def test_custom_source_from_natural_language_and_webhook(client: TestClient) -> None:
    """用户应可通过自然语言新增自定义信息源并走真实 webhook。"""
    apply_response = client.post(
        "/api/v1/integrations/nl",
        json={
            "text": "新增信息源 Notion，source=chat，webhook secret=notion-secret",
        },
    )
    assert apply_response.status_code == 200

    providers = apply_response.json().get("providers", [])
    notion = next((item for item in providers if item.get("provider") == "notion"), None)
    assert notion is not None
    assert notion.get("provider_type") == "custom"
    assert notion.get("configured") is True
    assert str(notion.get("webhook_url", "")).endswith("/api/v1/webhooks/custom/notion")

    forbidden = client.post(
        "/api/v1/webhooks/custom/notion",
        json={"text": "无 token 请求"},
    )
    assert forbidden.status_code == 401

    accepted = client.post(
        "/api/v1/webhooks/custom/notion",
        headers={"x-steward-webhook-token": "notion-secret"},
        json={"text": "请跟进这条 Notion 变更", "thread_id": "notion-page-1"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["space_id"].startswith("SPACE_")


def test_provider_configure_and_test_api(client: TestClient) -> None:
    """信息源应支持单独配置并执行测试。"""
    configure = client.post(
        "/api/v1/integrations/screen/configure",
        json={"screen_webhook_secret": "screen-secret-1"},
    )
    assert configure.status_code == 200
    assert "screen_webhook_secret" in configure.json().get("applied_fields", [])

    test_result = client.post(
        "/api/v1/integrations/screen/test",
        json={"summary": "screen provider test"},
    )
    assert test_result.status_code == 200
    body = test_result.json()
    assert body["provider"] == "screen"
    assert body["status"] == "ok"
