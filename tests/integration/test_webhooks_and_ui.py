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
    assert "立即查看简报" in dashboard_page.text

    integration_page = client.get("/dashboard/integrations")
    assert integration_page.status_code == 200
    assert "信息源管理" in integration_page.text

    executions_api = client.get("/api/v1/dashboard/executions")
    assert executions_api.status_code == 200
    executions_body = executions_api.json()
    assert "items" in executions_body
    assert "count" in executions_body

    executions_api_en = client.get("/api/v1/dashboard/executions?lang=en")
    assert executions_api_en.status_code == 200

    executions_page = client.get("/dashboard/executions")
    assert executions_page.status_code == 200
    assert "执行结果中心" in executions_page.text

    invalid_record = client.get("/api/v1/dashboard/records/../../etc/passwd")
    assert invalid_record.status_code == 404


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


def test_mcp_and_skill_management_api(client: TestClient) -> None:
    """MCP 与 Skill 应支持列表、配置与启停。"""
    snapshot = client.get("/api/v1/integrations")
    assert snapshot.status_code == 200
    body = snapshot.json()

    mcp_servers = body.get("mcp_servers", [])
    skills = body.get("skills", [])
    assert any(item.get("server") == "github" for item in mcp_servers)
    assert any(item.get("server") == "playwright" for item in mcp_servers)
    assert any(item.get("skill") == "gh-fix-ci" for item in skills)

    enable_mcp = client.post("/api/v1/integrations/mcp/github/enable")
    assert enable_mcp.status_code == 200
    github_status = next(
        (
            item
            for item in enable_mcp.json().get("mcp_servers", [])
            if item.get("server") == "github"
        ),
        None,
    )
    assert github_status is not None
    assert github_status.get("enabled") is True

    configure_mcp = client.post(
        "/api/v1/integrations/mcp/github/configure",
        json={"transport": "stdio", "command": "npx -y @modelcontextprotocol/server-github"},
    )
    assert configure_mcp.status_code == 200
    assert "command" in configure_mcp.json().get("applied_fields", [])

    enable_skill = client.post("/api/v1/integrations/skills/gh-fix-ci/enable")
    assert enable_skill.status_code == 200
    skill_status = next(
        (
            item
            for item in enable_skill.json().get("skills", [])
            if item.get("skill") == "gh-fix-ci"
        ),
        None,
    )
    assert skill_status is not None
    assert skill_status.get("enabled") is True

    nl_apply = client.post(
        "/api/v1/integrations/nl",
        json={"text": "启用 github mcp 和 playwright mcp，并启用 gh-fix-ci skill"},
    )
    assert nl_apply.status_code == 200
    assert "mcp_servers" in nl_apply.json()
    assert "skills" in nl_apply.json()


def test_legacy_skill_api_is_backed_by_integrations(client: TestClient) -> None:
    """旧 /skills 接口应复用 integrations 的统一技能状态。"""
    catalog = client.get("/api/v1/skills/catalog")
    assert catalog.status_code == 200
    assert any(item.get("id") == "gh-fix-ci" for item in catalog.json().get("skills", []))

    install = client.post(
        "/api/v1/skills/install",
        json={
            "skill_id": "gh-fix-ci",
            "config_values": {"GH_REPO_SCOPE": "owner/repo"},
            "run_install_command": True,
        },
    )
    assert install.status_code == 200
    assert install.json().get("status") == "ok"

    integrations = client.get("/api/v1/integrations")
    assert integrations.status_code == 200
    skill = next(
        (
            item
            for item in integrations.json().get("skills", [])
            if item.get("skill") == "gh-fix-ci"
        ),
        None,
    )
    assert skill is not None
    assert skill.get("enabled") is True
    assert skill.get("config_values", {}).get("GH_REPO_SCOPE") == "owner/repo"

    installed = client.get("/api/v1/skills/installed")
    assert installed.status_code == 200
    installed_items = installed.json().get("installed", [])
    assert any(
        item.get("skill_id") == "gh-fix-ci" and item.get("enabled") for item in installed_items
    )

    toggle = client.post(
        "/api/v1/skills/toggle",
        json={"skill_id": "gh-fix-ci", "enabled": False},
    )
    assert toggle.status_code == 200
    assert toggle.json().get("status") == "ok"

    after_toggle = client.get("/api/v1/integrations")
    assert after_toggle.status_code == 200
    skill_after = next(
        (
            item
            for item in after_toggle.json().get("skills", [])
            if item.get("skill") == "gh-fix-ci"
        ),
        None,
    )
    assert skill_after is not None
    assert skill_after.get("enabled") is False

    uninstall = client.post("/api/v1/skills/uninstall", json={"skill_id": "gh-fix-ci"})
    assert uninstall.status_code == 200
    assert uninstall.json().get("status") == "ok"


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
