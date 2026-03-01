"""信息源接入配置服务：支持内置 Provider 与自定义信息源。"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from steward.core.config import Settings
from steward.services.model_gateway import ModelGateway


class IntegrationConfigService:
    """管理运行时信息源接入配置。"""

    _builtin_provider_fields = {
        "slack": ["slack_signing_secret"],
        "gmail": ["gmail_pubsub_verification_token", "gmail_pubsub_topic"],
        "google-calendar": ["google_calendar_channel_token", "google_calendar_channel_ids"],
        "screen": ["screen_webhook_secret"],
    }
    _builtin_provider_source = {
        "slack": "chat",
        "gmail": "email",
        "google-calendar": "calendar",
        "screen": "screen",
    }
    _builtin_provider_webhook_path = {
        "slack": "/api/v1/webhooks/providers/slack",
        "gmail": "/api/v1/webhooks/providers/gmail",
        "google-calendar": "/api/v1/webhooks/providers/google-calendar",
        "screen": "/api/v1/webhooks/screen",
    }
    _supported_custom_sources = {
        "manual",
        "email",
        "chat",
        "calendar",
        "github",
        "screen",
        "local",
        "custom",
    }

    def __init__(self, settings: Settings, model_gateway: ModelGateway) -> None:
        self._settings = settings
        self._model_gateway = model_gateway
        self._runtime_path = Path(settings.integration_runtime_file)
        self._custom_providers: dict[str, dict[str, str]] = {}

    def load_runtime_overrides(self) -> None:
        """加载并应用本地持久化配置。"""
        if not self._runtime_path.exists():
            return

        try:
            raw = json.loads(self._runtime_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError, OSError:
            return
        if not isinstance(raw, dict):
            return

        config = raw.get("config", {})
        if isinstance(config, dict):
            updates = self._filter_updates(config)
            self._apply_updates_to_settings(updates)

        custom_raw = raw.get("custom_providers", [])
        filtered_custom = self._filter_custom_providers(
            custom_raw if isinstance(custom_raw, list) else []
        )
        self._custom_providers = {item["provider"]: item for item in filtered_custom}

    async def apply_from_natural_language(self, text: str, *, base_url: str) -> dict[str, Any]:
        """将自然语言配置解析为接入配置并应用。"""
        normalized_text = text.strip()
        if not normalized_text:
            return {
                "applied_fields": [],
                "message": "输入为空，未应用任何配置。",
                "providers": self.provider_status(base_url=base_url),
            }

        parsed = await self._model_gateway.parse_integration_config_text(normalized_text)
        model_updates = parsed.get("updates", {})
        updates = self._filter_updates(model_updates if isinstance(model_updates, dict) else {})
        if not updates:
            updates = self._extract_updates_with_regex(normalized_text)

        model_custom = parsed.get("custom_providers", [])
        custom_candidates = self._filter_custom_providers(
            model_custom if isinstance(model_custom, list) else []
        )
        if not custom_candidates:
            custom_candidates = self._extract_custom_providers_with_regex(normalized_text)

        self._apply_updates_to_settings(updates)
        upserted_custom = self._upsert_custom_providers(custom_candidates)
        self._persist_runtime_config()

        applied_fields = sorted(updates.keys())
        message = self._build_apply_message(
            applied_fields=applied_fields, upserted_custom=upserted_custom
        )

        return {
            "applied_fields": applied_fields,
            "message": message,
            "providers": self.provider_status(base_url=base_url),
            "raw_parse_reason": str(parsed.get("reason", "")),
        }

    def provider_status(self, *, base_url: str) -> list[dict[str, Any]]:
        """返回所有 Provider 的配置状态。"""
        statuses: list[dict[str, Any]] = []
        for provider, fields in self._builtin_provider_fields.items():
            missing = [
                field for field in fields if not str(getattr(self._settings, field, "")).strip()
            ]
            statuses.append(
                {
                    "provider": provider,
                    "provider_type": "builtin",
                    "source": self._builtin_provider_source.get(provider, "manual"),
                    "configured": len(missing) == 0,
                    "missing_fields": missing,
                    "webhook_url": self._webhook_url(
                        provider=provider, base_url=base_url, custom=False
                    ),
                    "instructions": self.join_instructions(provider=provider, base_url=base_url),
                }
            )

        for provider_name in sorted(self._custom_providers):
            item = self._custom_providers[provider_name]
            missing_fields = []
            if not item.get("webhook_secret", "").strip():
                missing_fields.append("webhook_secret")
            statuses.append(
                {
                    "provider": provider_name,
                    "provider_type": "custom",
                    "source": item.get("source", "custom"),
                    "configured": len(missing_fields) == 0,
                    "missing_fields": missing_fields,
                    "webhook_url": self._webhook_url(
                        provider=provider_name, base_url=base_url, custom=True
                    ),
                    "instructions": self.join_instructions(
                        provider=provider_name, base_url=base_url
                    ),
                    "description": item.get("description", ""),
                    "display_name": item.get("display_name", provider_name),
                }
            )
        return statuses

    def join_instructions(self, *, provider: str, base_url: str) -> str:
        """返回 provider 对应接入说明。"""
        normalized_provider = self._normalize_provider_name(provider)
        if normalized_provider in self._builtin_provider_fields:
            webhook_url = self._webhook_url(
                provider=normalized_provider, base_url=base_url, custom=False
            )
            if normalized_provider == "slack":
                return (
                    f"Slack Event Subscriptions 回调地址填写 {webhook_url}，"
                    "并在自然语言配置里提供 signing secret。"
                )
            if normalized_provider == "gmail":
                return (
                    f"Gmail Pub/Sub push 地址填写 {webhook_url}，"
                    "并提供 verification token 与 topic。"
                )
            if normalized_provider == "google-calendar":
                return (
                    f"Google Calendar Channel 回调地址填写 {webhook_url}，"
                    "并提供 channel token 与 channel ids。"
                )
            if normalized_provider == "screen":
                return (
                    f"屏幕传感器 webhook 地址填写 {webhook_url}，"
                    "并在自然语言配置里提供 screen_webhook_secret。"
                )

        custom_provider = self._custom_providers.get(normalized_provider)
        if custom_provider is None:
            return f"未知 Provider: {provider}"

        webhook_url = self._webhook_url(
            provider=normalized_provider, base_url=base_url, custom=True
        )
        source = custom_provider.get("source", "custom")
        display_name = custom_provider.get("display_name", normalized_provider)
        return (
            f"自定义信息源 {display_name}（id={normalized_provider}, source={source}）回调地址：{webhook_url}。"
            "请求头请携带 x-steward-webhook-token，并保持与 webhook_secret 一致。"
        )

    def custom_provider(self, provider: str) -> dict[str, str] | None:
        """返回指定自定义信息源配置。"""
        normalized = self._normalize_provider_name(provider)
        item = self._custom_providers.get(normalized)
        return dict(item) if item is not None else None

    def has_provider(self, provider: str) -> bool:
        """判断 provider 是否存在（内置或自定义）。"""
        normalized = self._normalize_provider_name(provider)
        return normalized in self._builtin_provider_fields or normalized in self._custom_providers

    def provider_status_item(self, *, provider: str, base_url: str) -> dict[str, Any] | None:
        """返回单个 provider 的状态。"""
        normalized = self._normalize_provider_name(provider)
        for item in self.provider_status(base_url=base_url):
            if str(item.get("provider")) == normalized:
                return item
        return None

    def provider_source(self, provider: str) -> str | None:
        """返回 provider 对应的事件 source。"""
        normalized = self._normalize_provider_name(provider)
        if normalized in self._builtin_provider_source:
            return self._builtin_provider_source[normalized]
        custom = self._custom_providers.get(normalized)
        if custom is None:
            return None
        return custom.get("source", "custom")

    def configure_provider(self, *, provider: str, payload: dict[str, Any]) -> dict[str, Any]:
        """按 provider 配置字段，并持久化。"""
        normalized = self._normalize_provider_name(provider)
        if not normalized:
            return {"provider": "", "applied_fields": [], "created_custom": False}

        if normalized in self._builtin_provider_fields:
            updates = self._extract_builtin_updates(provider=normalized, payload=payload)
            self._apply_updates_to_settings(updates)
            self._persist_runtime_config()
            return {
                "provider": normalized,
                "applied_fields": sorted(updates),
                "created_custom": False,
            }

        existed_before = normalized in self._custom_providers
        existing = self._custom_providers.get(normalized, {})
        source = self._normalize_source(
            str(payload.get("source", existing.get("source", "custom")))
        )
        if source not in self._supported_custom_sources:
            source = "custom"
        webhook_secret = str(
            payload.get("webhook_secret")
            or payload.get("secret")
            or existing.get("webhook_secret", "")
        ).strip()
        description = str(payload.get("description", existing.get("description", ""))).strip()
        display_name = str(
            payload.get("display_name")
            or payload.get("name")
            or existing.get("display_name")
            or normalized
        ).strip()

        self._custom_providers[normalized] = {
            "provider": normalized,
            "source": source,
            "webhook_secret": webhook_secret,
            "description": description,
            "display_name": display_name[:80],
        }
        self._persist_runtime_config()
        applied_fields = ["source", "webhook_secret", "description", "display_name"]
        return {
            "provider": normalized,
            "applied_fields": applied_fields,
            "created_custom": not existed_before,
        }

    def _webhook_url(self, *, provider: str, base_url: str, custom: bool) -> str:
        """根据 provider 生成 webhook 地址。"""
        base = base_url.rstrip("/")
        if custom:
            return f"{base}/api/v1/webhooks/custom/{provider}"
        path = self._builtin_provider_webhook_path.get(provider)
        if path:
            return f"{base}{path}"
        return f"{base}/api/v1/webhooks/providers/{provider}"

    def _filter_updates(self, raw_updates: dict[str, Any]) -> dict[str, str]:
        """过滤可写字段并标准化值。"""
        allowed_fields = {
            "slack_signing_secret",
            "gmail_pubsub_verification_token",
            "gmail_pubsub_topic",
            "google_calendar_channel_token",
            "google_calendar_channel_ids",
            "screen_webhook_secret",
        }
        updates: dict[str, str] = {}
        for field_name, value in raw_updates.items():
            if field_name not in allowed_fields:
                continue
            text = str(value).strip()
            if text:
                updates[field_name] = text
        return updates

    def _extract_builtin_updates(self, *, provider: str, payload: dict[str, Any]) -> dict[str, str]:
        """从结构化 payload 中提取内置 provider 更新字段。"""
        values = {str(key): value for key, value in payload.items()}
        updates: dict[str, str] = {}
        if provider == "slack":
            secret = str(
                values.get("slack_signing_secret")
                or values.get("signing_secret")
                or values.get("webhook_secret")
                or values.get("secret")
                or ""
            ).strip()
            if secret:
                updates["slack_signing_secret"] = secret
            return updates

        if provider == "gmail":
            token = str(
                values.get("gmail_pubsub_verification_token")
                or values.get("verification_token")
                or values.get("token")
                or ""
            ).strip()
            topic = str(values.get("gmail_pubsub_topic") or values.get("topic") or "").strip()
            if token:
                updates["gmail_pubsub_verification_token"] = token
            if topic:
                updates["gmail_pubsub_topic"] = topic
            return updates

        if provider == "google-calendar":
            token = str(
                values.get("google_calendar_channel_token")
                or values.get("channel_token")
                or values.get("token")
                or ""
            ).strip()
            channel_ids = str(
                values.get("google_calendar_channel_ids")
                or values.get("channel_ids")
                or values.get("ids")
                or ""
            ).strip()
            if token:
                updates["google_calendar_channel_token"] = token
            if channel_ids:
                updates["google_calendar_channel_ids"] = channel_ids
            return updates

        if provider == "screen":
            secret = str(
                values.get("screen_webhook_secret")
                or values.get("webhook_secret")
                or values.get("secret")
                or values.get("token")
                or ""
            ).strip()
            if secret:
                updates["screen_webhook_secret"] = secret
            return updates

        return updates

    def _filter_custom_providers(self, raw_items: list[Any]) -> list[dict[str, str]]:
        """过滤并标准化自定义信息源。"""
        providers: list[dict[str, str]] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            raw_name = str(raw_item.get("provider") or raw_item.get("name") or "").strip()
            provider_name = self._normalize_provider_name(raw_name)
            if not provider_name:
                continue
            if provider_name in self._builtin_provider_fields:
                continue

            source_raw = str(raw_item.get("source", "custom")).strip()
            source = self._normalize_source(source_raw)
            if source not in self._supported_custom_sources:
                source = "custom"

            secret = str(
                raw_item.get("webhook_secret")
                or raw_item.get("secret")
                or raw_item.get("token")
                or ""
            ).strip()
            description = str(raw_item.get("description", "")).strip()
            display_name = str(raw_item.get("display_name") or raw_name or provider_name).strip()

            providers.append(
                {
                    "provider": provider_name,
                    "source": source,
                    "webhook_secret": secret,
                    "description": description,
                    "display_name": display_name[:80],
                }
            )
        return providers

    def _upsert_custom_providers(self, items: list[dict[str, str]]) -> list[str]:
        """写入或更新自定义信息源。"""
        updated: list[str] = []
        for item in items:
            provider_name = item["provider"]
            self._custom_providers[provider_name] = item
            updated.append(provider_name)
        return sorted(updated)

    def _apply_updates_to_settings(self, updates: dict[str, str]) -> None:
        """将更新写入内存配置对象。"""
        for field_name, value in updates.items():
            setattr(self._settings, field_name, value)

    def _persist_runtime_config(self) -> None:
        """将当前配置写入本地持久化文件。"""
        self._runtime_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(UTC).isoformat(),
            "config": {
                "slack_signing_secret": self._settings.slack_signing_secret,
                "gmail_pubsub_verification_token": self._settings.gmail_pubsub_verification_token,
                "gmail_pubsub_topic": self._settings.gmail_pubsub_topic,
                "google_calendar_channel_token": self._settings.google_calendar_channel_token,
                "google_calendar_channel_ids": self._settings.google_calendar_channel_ids,
                "screen_webhook_secret": self._settings.screen_webhook_secret,
            },
            "custom_providers": [
                self._custom_providers[key] for key in sorted(self._custom_providers)
            ],
        }
        self._runtime_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _build_apply_message(self, *, applied_fields: list[str], upserted_custom: list[str]) -> str:
        """构建自然语言应用结果消息。"""
        parts: list[str] = []
        if applied_fields:
            parts.append(f"已应用配置字段：{', '.join(applied_fields)}")
        if upserted_custom:
            parts.append(f"已更新自定义信息源：{', '.join(upserted_custom)}")
        if not parts:
            return (
                "未识别到可写入字段。可直接输入："
                "新增信息源 notion，source=chat，webhook secret=xxx。"
            )
        return "；".join(parts)

    def _extract_updates_with_regex(self, text: str) -> dict[str, str]:
        """模型解析失败时，使用正则做兜底提取。"""
        updates: dict[str, str] = {}

        slack_match = re.search(
            r"(?:slack[^\n]{0,40}(?:secret|签名|signing)[^\n]{0,12}[:=： ]\s*)([A-Za-z0-9._\-]+)",
            text,
            flags=re.IGNORECASE,
        )
        if slack_match:
            updates["slack_signing_secret"] = slack_match.group(1).strip()

        gmail_token_match = re.search(
            r"(?:gmail[^\n]{0,40}(?:token|验证|verification)[^\n]{0,12}[:=： ]\s*)([A-Za-z0-9._\-]+)",
            text,
            flags=re.IGNORECASE,
        )
        if gmail_token_match:
            updates["gmail_pubsub_verification_token"] = gmail_token_match.group(1).strip()

        topic_match = re.search(
            r"(projects/[A-Za-z0-9_\\-]+/topics/[A-Za-z0-9_\\-]+)", text, flags=re.IGNORECASE
        )
        if topic_match:
            updates["gmail_pubsub_topic"] = topic_match.group(1).strip()

        gcal_token_match = re.search(
            r"(?:calendar[^\n]{0,40}(?:token|channel token|令牌)[^\n]{0,12}[:=： ]\s*)([A-Za-z0-9._\-]+)",
            text,
            flags=re.IGNORECASE,
        )
        if gcal_token_match:
            updates["google_calendar_channel_token"] = gcal_token_match.group(1).strip()

        channel_ids_match = re.search(
            r"(?:channel\s*ids?|频道\s*id)[^:=\n]{0,12}[:=： ]\s*([A-Za-z0-9,，._\-\s]+)",
            text,
            flags=re.IGNORECASE,
        )
        if channel_ids_match:
            ids = ",".join(
                [
                    item.strip()
                    for item in channel_ids_match.group(1).replace("，", ",").split(",")
                    if item.strip()
                ]
            )
            if ids:
                updates["google_calendar_channel_ids"] = ids

        screen_secret_match = re.search(
            r"(?:screen|屏幕)[^\n]{0,40}(?:secret|token|密钥|令牌)[^\n]{0,12}[:=： ]\s*([A-Za-z0-9._\-]+)",
            text,
            flags=re.IGNORECASE,
        )
        if screen_secret_match:
            updates["screen_webhook_secret"] = screen_secret_match.group(1).strip()

        return updates

    def _extract_custom_providers_with_regex(self, text: str) -> list[dict[str, str]]:
        """模型不可用时，提取自定义信息源。"""
        name_match = re.search(
            r"(?:新增|添加|接入|加入)\s*(?:信息源|source|provider)?\s*[\"“]?([A-Za-z\u4e00-\u9fa5][A-Za-z0-9\u4e00-\u9fa5 _\-]{1,63})[\"”]?",
            text,
            flags=re.IGNORECASE,
        )
        if name_match is None:
            return []

        provider_name = self._normalize_provider_name(name_match.group(1))
        if not provider_name or provider_name in self._builtin_provider_fields:
            return []

        source_match = re.search(
            r"(?:source|类型|来源)\s*[:=：]\s*([A-Za-z\u4e00-\u9fa5_-]+)",
            text,
            flags=re.IGNORECASE,
        )
        secret_match = re.search(
            r"(?:webhook\s*secret|secret|token|密钥|令牌)\s*[:=：]\s*([A-Za-z0-9._\-]+)",
            text,
            flags=re.IGNORECASE,
        )
        source = self._normalize_source(source_match.group(1) if source_match else "custom")
        secret = secret_match.group(1).strip() if secret_match else ""
        return [
            {
                "provider": provider_name,
                "source": source,
                "webhook_secret": secret,
                "description": "",
                "display_name": name_match.group(1).strip()[:80],
            }
        ]

    def _normalize_provider_name(self, raw: str) -> str:
        """标准化 provider 名称。"""
        original = raw.strip()
        lowered = original.lower()
        lowered = lowered.replace("_", "-")
        lowered = re.sub(r"\s+", "-", lowered)
        lowered = re.sub(r"[^a-z0-9-]", "", lowered)
        lowered = re.sub(r"-{2,}", "-", lowered).strip("-")
        if lowered:
            return lowered[:64]
        if not original:
            return ""
        digest = hashlib.sha1(original.encode("utf-8")).hexdigest()[:10]
        return f"custom-{digest}"

    def _normalize_source(self, raw: str) -> str:
        """标准化 source 枚举值。"""
        lowered = raw.strip().lower()
        alias = {
            "邮件": "email",
            "邮箱": "email",
            "聊天": "chat",
            "会话": "chat",
            "日历": "calendar",
            "屏幕": "screen",
            "屏幕监听": "screen",
            "屏幕等待": "screen",
            "本地": "local",
            "手动": "manual",
            "自定义": "custom",
        }
        return alias.get(lowered, lowered)
