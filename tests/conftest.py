"""测试公共夹具。"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from steward.core.config import get_settings
from steward.main import app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient]:
    """返回绑定 sqlite 测试数据库的客户端。"""
    db_path = tmp_path / "steward-test.db"
    model_config_path = tmp_path / "model.yaml"
    integration_runtime_path = tmp_path / "integrations.runtime.json"
    brief_runtime_path = tmp_path / "brief.runtime.json"
    model_config_path.write_text(
        "\n".join(
            [
                "model:",
                '  base_url: "http://127.0.0.1:9"',
                '  api_key: "test-key"',
                '  api_key_env: ""',
                '  router: "test-router"',
                '  default: "test-default"',
                '  fallback: "test-fallback"',
                "  timeout_ms: 50",
                "  max_retries: 0",
                "  router_min_confidence: 0.70",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("STEWARD_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("STEWARD_ENABLE_SCHEDULER", "false")
    monkeypatch.setenv("STEWARD_MODEL_CONFIG_FILE", str(model_config_path))
    monkeypatch.setenv("STEWARD_INTEGRATION_RUNTIME_FILE", str(integration_runtime_path))
    monkeypatch.setenv("STEWARD_BRIEF_RUNTIME_FILE", str(brief_runtime_path))
    monkeypatch.setenv("STEWARD_GITHUB_TOKEN", "")
    monkeypatch.setenv("STEWARD_SLACK_SIGNING_SECRET", "slack-test-secret")
    monkeypatch.setenv("STEWARD_GMAIL_PUBSUB_VERIFICATION_TOKEN", "gmail-token")
    monkeypatch.setenv("STEWARD_GOOGLE_CALENDAR_CHANNEL_TOKEN", "calendar-token")

    get_settings.cache_clear()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()
