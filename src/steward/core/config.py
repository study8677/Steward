"""应用配置模块，统一管理环境变量与默认值。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Steward 运行参数。"""

    model_config = SettingsConfigDict(
        env_prefix="STEWARD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Steward"
    env: str = "dev"
    timezone: str = "Asia/Shanghai"
    log_level: str = "INFO"

    database_url: str = "sqlite+aiosqlite:///steward.db"

    model_config_file: str = "config/model.yaml"
    model_base_url: str = "https://api.openai.com/v1"
    model_api_key: str = ""
    model_router: str = "top-reasoning-model"
    model_default: str = "balanced-general-model"
    model_fallback: str = "fast-fallback-model"
    model_timeout_ms: int = 12000
    model_max_retries: int = 2
    model_router_min_confidence: float = 0.70

    github_token: str = ""
    github_webhook_secret: str = ""
    slack_signing_secret: str = ""
    gmail_pubsub_verification_token: str = ""
    gmail_pubsub_topic: str = ""
    google_calendar_channel_token: str = ""
    google_calendar_channel_ids: str = ""
    email_webhook_secret: str = ""
    chat_webhook_secret: str = ""
    calendar_webhook_secret: str = ""
    screen_webhook_secret: str = ""
    webhook_shared_secret: str = ""

    email_outbound_enabled: bool = False
    chat_outbound_enabled: bool = False

    mcp_gateway_base_url: str = ""
    mcp_gateway_api_key: str = ""

    brief_window_hours: int = 4
    fallback_polling_minutes: int = 5
    interruption_budget_per_day: int = 10
    waiting_timeout_scan_seconds: int = 60
    enable_scheduler: bool = True
    webhook_backpressure_max_inflight: int = 12
    webhook_backpressure_max_events_per_window: int = 120
    webhook_backpressure_window_seconds: int = 10
    webhook_backpressure_dedup_ttl_seconds: int = 120

    policy_file: str = Field(default="config/policy.yaml")
    integration_runtime_file: str = Field(default="config/integrations.runtime.json")

    @property
    def policy_path(self) -> Path:
        """返回策略配置路径。"""
        return Path(self.policy_file)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回缓存后的配置对象。"""
    return Settings()
