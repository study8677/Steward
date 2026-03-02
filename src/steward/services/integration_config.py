"""信息源接入配置服务：支持内置 Provider + MCP + Skill 管理。"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from steward.core.config import Settings
from steward.services.model_gateway import ModelGateway


class IntegrationConfigService:
    """管理运行时接入配置（legacy provider + MCP + skills）。"""

    _builtin_provider_fields = {
        "github": ["github_webhook_secret"],
        "slack": ["slack_signing_secret"],
        "gmail": ["gmail_pubsub_verification_token", "gmail_pubsub_topic"],
        "google-calendar": ["google_calendar_channel_token", "google_calendar_channel_ids"],
        "screen": ["screen_webhook_secret"],
    }
    _builtin_provider_source = {
        "github": "github",
        "slack": "chat",
        "gmail": "email",
        "google-calendar": "calendar",
        "screen": "screen",
    }
    _builtin_provider_webhook_path = {
        "github": "/api/v1/webhooks/providers/github",
        "slack": "/api/v1/webhooks/providers/slack",
        "gmail": "/api/v1/webhooks/providers/gmail",
        "google-calendar": "/api/v1/webhooks/providers/google-calendar",
        "screen": "/api/v1/webhooks/screen",
    }

    _default_mcp_catalog: dict[str, dict[str, str]] = {
        "github": {
            "display_name": "GitHub MCP",
            "transport": "stdio",
            "command": "npx -y @modelcontextprotocol/server-github",
            "description": "接入 GitHub 仓库、Issue、PR 与自动化操作能力。",
            "source_url": "https://github.com/modelcontextprotocol/servers",
        },
        "playwright": {
            "display_name": "Playwright MCP",
            "transport": "stdio",
            "command": "npx -y @playwright/mcp@latest",
            "description": "浏览器自动化执行、页面抓取、UI 回归与 E2E 辅助。",
            "source_url": "https://github.com/microsoft/playwright-mcp",
        },
        "filesystem": {
            "display_name": "Filesystem MCP",
            "transport": "stdio",
            "command": "npx -y @modelcontextprotocol/server-filesystem /path/to/workspace",
            "description": "安全范围内的文件读取与写入能力。",
            "source_url": "https://github.com/modelcontextprotocol/servers",
        },
        "fetch": {
            "display_name": "Fetch MCP",
            "transport": "stdio",
            "command": "npx -y @modelcontextprotocol/server-fetch",
            "description": "受控网页抓取能力，可作为信息获取兜底。",
            "source_url": "https://github.com/modelcontextprotocol/servers",
        },
    }

    _default_skill_catalog: dict[str, dict[str, str]] = {
        "gh-address-comments": {
            "display_name": "GH Address Comments",
            "description": "处理 PR review comments 并回填修复。",
            "source": "local",
        },
        "gh-fix-ci": {
            "display_name": "GH Fix CI",
            "description": "排查并修复 GitHub Actions 失败项。",
            "source": "local",
        },
        "playwright": {
            "display_name": "Playwright Skill",
            "description": "在终端驱动真实浏览器完成 UI 自动化任务。",
            "source": "local",
        },
        "openai-docs": {
            "display_name": "OpenAI Docs Skill",
            "description": "基于官方文档输出产品/API集成建议。",
            "source": "local",
        },
        "pdf": {
            "display_name": "PDF Skill",
            "description": "PDF 读取、生成、渲染与检查。",
            "source": "local",
        },
        "doc": {
            "display_name": "DOCX Skill",
            "description": "Word 文档读写与排版保真处理。",
            "source": "local",
        },
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
        self._mcp_servers: dict[str, dict[str, Any]] = {}
        self._skills: dict[str, dict[str, Any]] = {}
        self._builtin_mcp_catalog: dict[str, dict[str, str]] = dict(self._default_mcp_catalog)
        self._builtin_skill_catalog: dict[str, dict[str, str]] = dict(self._default_skill_catalog)
        self._load_builtin_capability_catalog()

    def _load_builtin_capability_catalog(self) -> None:
        """从 config/skills_catalog.yaml 读取能力目录并合并。"""
        catalog_path = self._project_root() / "config" / "skills_catalog.yaml"
        if not catalog_path.exists():
            return

        try:
            raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
        except yaml.YAMLError, OSError:
            return
        if not isinstance(raw, dict):
            return

        items = raw.get("skills", [])
        if not isinstance(items, list):
            return

        for item in items:
            if not isinstance(item, dict):
                continue
            raw_id = str(item.get("id", "")).strip()
            if not raw_id:
                continue

            skill_type = str(item.get("type", "builtin")).strip().lower()
            display_name = str(item.get("name", raw_id)).strip() or raw_id
            description = str(item.get("description", "")).strip()

            if skill_type == "mcp":
                server = self._skill_id_to_mcp_server(raw_id)
                install_command = str(item.get("install_command", "")).strip()
                mcp_config = item.get("mcp_config", {})
                transport = (
                    str(mcp_config.get("transport", "stdio")).strip().lower()
                    if isinstance(mcp_config, dict)
                    else "stdio"
                )
                if transport not in {"stdio", "http"}:
                    transport = "stdio"
                self._builtin_mcp_catalog.setdefault(
                    server,
                    {
                        "display_name": display_name,
                        "transport": transport,
                        "command": install_command,
                        "description": description,
                        "source_url": "",
                    },
                )
                continue

            normalized_skill = self._normalize_provider_name(raw_id)
            if not normalized_skill:
                continue
            self._builtin_skill_catalog.setdefault(
                normalized_skill,
                {
                    "display_name": display_name,
                    "description": description,
                    "source": "catalog",
                },
            )

    def _project_root(self) -> Path:
        """定位项目根目录。"""
        return Path(__file__).resolve().parents[3]

    def _skill_id_to_mcp_server(self, raw_id: str) -> str:
        """将 skills_catalog id 映射为 mcp server id。"""
        normalized = self._normalize_provider_name(raw_id)
        if normalized.startswith("mcp-"):
            return normalized[4:]
        return normalized

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

        mcp_raw = raw.get("mcp_servers", [])
        filtered_mcp = self._filter_mcp_servers(mcp_raw if isinstance(mcp_raw, list) else [])
        self._mcp_servers = {item["server"]: item for item in filtered_mcp}

        skill_raw = raw.get("skills", [])
        filtered_skills = self._filter_skills(skill_raw if isinstance(skill_raw, list) else [])
        self._skills = {item["skill"]: item for item in filtered_skills}

    async def apply_from_natural_language(self, text: str, *, base_url: str) -> dict[str, Any]:
        """将自然语言配置解析并应用。"""
        normalized_text = text.strip()
        if not normalized_text:
            return {
                "applied_fields": [],
                "message": "输入为空，未应用任何配置。",
                "providers": self.provider_status(base_url=base_url),
                "mcp_servers": self.mcp_server_status(),
                "skills": self.skill_status(),
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

        enable_capability, mcp_ids, skill_ids = self._extract_capability_targets(normalized_text)

        self._apply_updates_to_settings(updates)
        upserted_custom = self._upsert_custom_providers(custom_candidates)
        changed_mcp = self._set_mcp_servers_enabled(mcp_ids, enable_capability)
        changed_skills = self._set_skills_enabled(skill_ids, enable_capability)
        self._persist_runtime_config()

        applied_fields = sorted(updates.keys())
        message = self._build_apply_message(
            applied_fields=applied_fields,
            upserted_custom=upserted_custom,
            changed_mcp=changed_mcp,
            changed_skills=changed_skills,
            capability_enabled=enable_capability,
        )

        return {
            "applied_fields": applied_fields,
            "message": message,
            "providers": self.provider_status(base_url=base_url),
            "mcp_servers": self.mcp_server_status(),
            "skills": self.skill_status(),
            "raw_parse_reason": str(parsed.get("reason", "")),
        }

    # -------------------------------------------------------------------------
    # Legacy Provider（兼容原 webhook 配置）
    # -------------------------------------------------------------------------

    def provider_status(self, *, base_url: str) -> list[dict[str, Any]]:
        """返回 legacy provider 的配置状态。"""
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
        """返回 legacy provider 的接入说明。"""
        normalized_provider = self._normalize_provider_name(provider)
        if normalized_provider in self._builtin_provider_fields:
            webhook_url = self._webhook_url(
                provider=normalized_provider, base_url=base_url, custom=False
            )
            if normalized_provider == "github":
                return (
                    f"GitHub Webhook 回调地址填写 {webhook_url}，"
                    "事件勾选 issues、issue_comment、pull_request；"
                    "并在自然语言配置里提供 github webhook secret。"
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
        """判断 legacy provider 是否存在（内置或自定义）。"""
        normalized = self._normalize_provider_name(provider)
        return normalized in self._builtin_provider_fields or normalized in self._custom_providers

    def provider_status_item(self, *, provider: str, base_url: str) -> dict[str, Any] | None:
        """返回单个 legacy provider 状态。"""
        normalized = self._normalize_provider_name(provider)
        for item in self.provider_status(base_url=base_url):
            if str(item.get("provider")) == normalized:
                return item
        return None

    def provider_source(self, provider: str) -> str | None:
        """返回 legacy provider 对应 source。"""
        normalized = self._normalize_provider_name(provider)
        if normalized in self._builtin_provider_source:
            return self._builtin_provider_source[normalized]
        custom = self._custom_providers.get(normalized)
        if custom is None:
            return None
        return custom.get("source", "custom")

    def configure_provider(self, *, provider: str, payload: dict[str, Any]) -> dict[str, Any]:
        """按 legacy provider 配置字段。"""
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
        return {
            "provider": normalized,
            "applied_fields": ["source", "webhook_secret", "description", "display_name"],
            "created_custom": not existed_before,
        }

    # -------------------------------------------------------------------------
    # MCP / Skill 管理（新主路径）
    # -------------------------------------------------------------------------

    def mcp_server_status(self) -> list[dict[str, Any]]:
        """返回 MCP server 管理状态。"""
        ids = sorted(set(self._builtin_mcp_catalog) | set(self._mcp_servers))
        items: list[dict[str, Any]] = []
        for server in ids:
            item = self._mcp_status_item(server)
            if item is not None:
                items.append(item)
        return items

    def skill_status(self) -> list[dict[str, Any]]:
        """返回 skill 管理状态。"""
        ids = sorted(set(self._builtin_skill_catalog) | set(self._skills))
        items: list[dict[str, Any]] = []
        for skill in ids:
            item = self._skill_status_item(skill)
            # 只展示本机真实已安装的 skill，避免出现“伪能力”。
            if item is not None and bool(item.get("installed")):
                items.append(item)
        return items

    def has_mcp_server(self, server: str) -> bool:
        """判断 MCP server 是否存在（内置或已配置）。"""
        normalized = self._normalize_provider_name(server)
        return normalized in self._builtin_mcp_catalog or normalized in self._mcp_servers

    def has_skill(self, skill: str) -> bool:
        """判断 skill 是否存在（内置或已配置）。"""
        normalized = self._normalize_provider_name(skill)
        # skill 必须真实安装在本机才可管理。
        return self._skill_installed(normalized)

    def mcp_server_status_item(self, server: str) -> dict[str, Any] | None:
        """返回单个 MCP server 状态。"""
        normalized = self._normalize_provider_name(server)
        return self._mcp_status_item(normalized)

    def skill_status_item(self, skill: str) -> dict[str, Any] | None:
        """返回单个 skill 状态。"""
        normalized = self._normalize_provider_name(skill)
        return self._skill_status_item(normalized)

    def configure_mcp_server(self, *, server: str, payload: dict[str, Any]) -> dict[str, Any]:
        """创建或更新 MCP server 配置。"""
        normalized = self._normalize_provider_name(server)
        if not normalized:
            return {"server": "", "applied_fields": [], "created_custom": False}

        default_item = self._builtin_mcp_catalog.get(normalized, {})
        existed_before = normalized in self._mcp_servers
        existing = self._mcp_servers.get(normalized, {})

        transport = (
            str(
                payload.get("transport")
                or existing.get("transport")
                or default_item.get("transport")
                or "stdio"
            )
            .strip()
            .lower()
        )
        if transport not in {"stdio", "http"}:
            transport = "stdio"

        command = str(
            payload.get("command") or existing.get("command") or default_item.get("command") or ""
        ).strip()
        endpoint = str(
            payload.get("endpoint")
            or payload.get("url")
            or existing.get("endpoint")
            or default_item.get("endpoint")
            or ""
        ).strip()
        if transport == "http" and not endpoint and command.startswith("http"):
            endpoint = command
            command = ""
        if transport == "stdio" and not command and endpoint and not endpoint.startswith("http"):
            command = endpoint
            endpoint = ""

        display_name = str(
            payload.get("display_name")
            or payload.get("name")
            or existing.get("display_name")
            or default_item.get("display_name")
            or normalized
        ).strip()
        description = str(
            payload.get("description")
            or existing.get("description")
            or default_item.get("description")
            or ""
        ).strip()
        source_url = str(
            payload.get("source_url")
            or existing.get("source_url")
            or default_item.get("source_url")
            or ""
        ).strip()
        auth_env = str(payload.get("auth_env") or existing.get("auth_env") or "").strip()
        enabled = self._parse_bool(
            payload.get("enabled"),
            default=self._parse_bool(existing.get("enabled"), default=False),
        )

        self._mcp_servers[normalized] = {
            "server": normalized,
            "display_name": display_name[:80],
            "transport": transport,
            "command": command,
            "endpoint": endpoint,
            "description": description,
            "source_url": source_url,
            "auth_env": auth_env,
            "enabled": enabled,
        }
        self._persist_runtime_config()
        return {
            "server": normalized,
            "applied_fields": [
                "display_name",
                "transport",
                "command",
                "endpoint",
                "description",
                "source_url",
                "auth_env",
                "enabled",
            ],
            "created_custom": (normalized not in self._builtin_mcp_catalog)
            and (not existed_before),
        }

    def configure_skill(self, *, skill: str, payload: dict[str, Any]) -> dict[str, Any]:
        """创建或更新 skill 配置。"""
        normalized = self._normalize_provider_name(skill)
        if not normalized:
            return {"skill": "", "applied_fields": [], "created_custom": False}
        if not self._skill_installed(normalized):
            return {"skill": "", "applied_fields": [], "created_custom": False}

        default_item = self._builtin_skill_catalog.get(normalized, {})
        existed_before = normalized in self._skills
        existing = self._skills.get(normalized, {})

        display_name = str(
            payload.get("display_name")
            or payload.get("name")
            or existing.get("display_name")
            or default_item.get("display_name")
            or normalized
        ).strip()
        source = str(
            payload.get("source") or existing.get("source") or default_item.get("source") or ""
        ).strip()
        description = str(
            payload.get("description")
            or existing.get("description")
            or default_item.get("description")
            or ""
        ).strip()
        enabled = self._parse_bool(
            payload.get("enabled"),
            default=self._parse_bool(existing.get("enabled"), default=False),
        )
        config_values = self._sanitize_config_values(
            payload.get("config_values"),
            default=existing.get("config_values", {}),
        )

        self._skills[normalized] = {
            "skill": normalized,
            "display_name": display_name[:80],
            "source": source[:200],
            "description": description,
            "enabled": enabled,
            "config_values": config_values,
        }
        self._persist_runtime_config()
        return {
            "skill": normalized,
            "applied_fields": [
                "display_name",
                "source",
                "description",
                "enabled",
                "config_values",
            ],
            "created_custom": (normalized not in self._builtin_skill_catalog)
            and (not existed_before),
        }

    def set_mcp_server_enabled(self, server: str, enabled: bool) -> dict[str, Any] | None:
        """启用/停用单个 MCP server。"""
        normalized = self._normalize_provider_name(server)
        if not normalized:
            return None

        if normalized not in self._mcp_servers:
            seed = self._builtin_mcp_catalog.get(normalized, {})
            self._mcp_servers[normalized] = {
                "server": normalized,
                "display_name": str(seed.get("display_name", normalized)),
                "transport": str(seed.get("transport", "stdio")),
                "command": str(seed.get("command", "")),
                "endpoint": str(seed.get("endpoint", "")),
                "description": str(seed.get("description", "")),
                "source_url": str(seed.get("source_url", "")),
                "auth_env": "",
                "enabled": enabled,
            }
        else:
            self._mcp_servers[normalized]["enabled"] = enabled

        self._persist_runtime_config()
        return self._mcp_status_item(normalized)

    def set_skill_enabled(self, skill: str, enabled: bool) -> dict[str, Any] | None:
        """启用/停用单个 skill。"""
        normalized = self._normalize_provider_name(skill)
        if not normalized:
            return None
        if not self._skill_installed(normalized):
            return None

        if normalized not in self._skills:
            seed = self._builtin_skill_catalog.get(normalized, {})
            self._skills[normalized] = {
                "skill": normalized,
                "display_name": str(seed.get("display_name", normalized)),
                "source": str(seed.get("source", "")),
                "description": str(seed.get("description", "")),
                "enabled": enabled,
                "config_values": {},
            }
        else:
            self._skills[normalized]["enabled"] = enabled

        self._persist_runtime_config()
        return self._skill_status_item(normalized)

    # -------------------------------------------------------------------------
    # 内部工具
    # -------------------------------------------------------------------------

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
        """过滤 legacy 可写字段并标准化。"""
        allowed_fields = {
            "github_webhook_secret",
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
        """从结构化 payload 中提取内置 provider 字段。"""
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

        if provider == "github":
            secret = str(
                values.get("github_webhook_secret")
                or values.get("webhook_secret")
                or values.get("secret")
                or values.get("token")
                or ""
            ).strip()
            if secret:
                updates["github_webhook_secret"] = secret
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

    def _filter_mcp_servers(self, raw_items: list[Any]) -> list[dict[str, Any]]:
        """过滤并标准化 MCP server 配置。"""
        servers: list[dict[str, Any]] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue

            raw_name = str(
                raw_item.get("server") or raw_item.get("provider") or raw_item.get("name") or ""
            ).strip()
            server = self._normalize_provider_name(raw_name)
            if not server:
                continue

            transport = str(raw_item.get("transport", "stdio")).strip().lower()
            if transport not in {"stdio", "http"}:
                transport = "stdio"

            command = str(raw_item.get("command", "")).strip()
            endpoint = str(raw_item.get("endpoint") or raw_item.get("url") or "").strip()
            if transport == "http" and not endpoint and command.startswith("http"):
                endpoint = command
                command = ""
            if (
                transport == "stdio"
                and not command
                and endpoint
                and not endpoint.startswith("http")
            ):
                command = endpoint
                endpoint = ""

            display_name = str(raw_item.get("display_name") or raw_name or server).strip()[:80]
            description = str(raw_item.get("description", "")).strip()
            source_url = str(raw_item.get("source_url", "")).strip()
            auth_env = str(raw_item.get("auth_env", "")).strip()
            enabled = self._parse_bool(raw_item.get("enabled"), default=False)

            servers.append(
                {
                    "server": server,
                    "display_name": display_name,
                    "transport": transport,
                    "command": command,
                    "endpoint": endpoint,
                    "description": description,
                    "source_url": source_url,
                    "auth_env": auth_env,
                    "enabled": enabled,
                }
            )
        return servers

    def _filter_skills(self, raw_items: list[Any]) -> list[dict[str, Any]]:
        """过滤并标准化 skill 配置。"""
        skills: list[dict[str, Any]] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue

            raw_name = str(raw_item.get("skill") or raw_item.get("name") or "").strip()
            skill = self._normalize_provider_name(raw_name)
            if not skill:
                continue
            if not self._skill_installed(skill):
                continue

            display_name = str(raw_item.get("display_name") or raw_name or skill).strip()[:80]
            source = str(raw_item.get("source", "")).strip()[:200]
            description = str(raw_item.get("description", "")).strip()
            enabled = self._parse_bool(raw_item.get("enabled"), default=False)
            config_values = self._sanitize_config_values(raw_item.get("config_values"), default={})

            skills.append(
                {
                    "skill": skill,
                    "display_name": display_name,
                    "source": source,
                    "description": description,
                    "enabled": enabled,
                    "config_values": config_values,
                }
            )
        return skills

    def _upsert_custom_providers(self, items: list[dict[str, str]]) -> list[str]:
        """写入或更新自定义信息源。"""
        updated: list[str] = []
        for item in items:
            provider_name = item["provider"]
            self._custom_providers[provider_name] = item
            updated.append(provider_name)
        return sorted(updated)

    def _set_mcp_servers_enabled(self, server_ids: list[str], enabled: bool) -> list[str]:
        """批量设置 MCP server 开关。"""
        changed: list[str] = []
        for server_id in server_ids:
            result = self.set_mcp_server_enabled(server_id, enabled)
            if result is not None:
                changed.append(str(result.get("server", server_id)))
        return sorted(set(changed))

    def _set_skills_enabled(self, skill_ids: list[str], enabled: bool) -> list[str]:
        """批量设置 skill 开关。"""
        changed: list[str] = []
        for skill_id in skill_ids:
            result = self.set_skill_enabled(skill_id, enabled)
            if result is not None:
                changed.append(str(result.get("skill", skill_id)))
        return sorted(set(changed))

    def _extract_capability_targets(self, text: str) -> tuple[bool, list[str], list[str]]:
        """从自然语言中提取 MCP/Skill 启停目标。"""
        lowered = text.lower()
        disable_markers = {"禁用", "关闭", "停用", "disable", "turn off", "off "}
        enable = not any(marker in lowered for marker in disable_markers)

        mention_mcp = any(token in lowered for token in {"mcp", "server", "能力源"})
        mention_skill = any(token in lowered for token in {"skill", "技能"})

        mcp_targets: list[str] = []
        for server, meta in self._builtin_mcp_catalog.items():
            aliases = {
                server,
                str(meta.get("display_name", ""))
                .strip()
                .lower()
                .replace(" mcp", "")
                .replace(" server", ""),
            }
            if any(alias and alias in lowered for alias in aliases) and (
                mention_mcp or "mcp" in lowered
            ):
                mcp_targets.append(server)

        skill_targets: list[str] = []
        for skill, meta in self._builtin_skill_catalog.items():
            aliases = {
                skill,
                str(meta.get("display_name", "")).strip().lower(),
            }
            if any(alias and alias in lowered for alias in aliases) and (
                mention_skill or "skill" in lowered
            ):
                skill_targets.append(skill)

        # 当句子明确提到 mcp 但仅给出常见名称时，按内置目录兜底匹配。
        if mention_mcp:
            for alias, canonical in {"github": "github", "playwright": "playwright"}.items():
                if alias in lowered and canonical not in mcp_targets:
                    mcp_targets.append(canonical)

        return enable, sorted(set(mcp_targets)), sorted(set(skill_targets))

    def _apply_updates_to_settings(self, updates: dict[str, str]) -> None:
        """将 legacy 更新写入运行时配置对象。"""
        for field_name, value in updates.items():
            setattr(self._settings, field_name, value)

    def _persist_runtime_config(self) -> None:
        """将当前配置写入本地持久化文件。"""
        self._runtime_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(UTC).isoformat(),
            "config": {
                "github_webhook_secret": self._settings.github_webhook_secret,
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
            "mcp_servers": [self._mcp_servers[key] for key in sorted(self._mcp_servers)],
            "skills": [self._skills[key] for key in sorted(self._skills)],
        }
        self._runtime_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _build_apply_message(
        self,
        *,
        applied_fields: list[str],
        upserted_custom: list[str],
        changed_mcp: list[str],
        changed_skills: list[str],
        capability_enabled: bool,
    ) -> str:
        """构建自然语言应用结果消息。"""
        parts: list[str] = []
        if applied_fields:
            parts.append(f"已应用 webhook 配置字段：{', '.join(applied_fields)}")
        if upserted_custom:
            parts.append(f"已更新自定义信息源：{', '.join(upserted_custom)}")
        if changed_mcp:
            action = "启用" if capability_enabled else "停用"
            parts.append(f"已{action} MCP：{', '.join(changed_mcp)}")
        if changed_skills:
            action = "启用" if capability_enabled else "停用"
            parts.append(f"已{action} Skill：{', '.join(changed_skills)}")
        if not parts:
            return (
                "未识别到可写入字段。可输入："
                "启用 github mcp 和 playwright mcp；启用 gh-fix-ci skill。"
            )
        return "；".join(parts)

    def _extract_updates_with_regex(self, text: str) -> dict[str, str]:
        """模型解析失败时，使用正则做 legacy 兜底提取。"""
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

        github_secret_match = re.search(
            r"(?:github[^\n]{0,40}(?:webhook)?[^\n]{0,10}(?:secret|token|密钥|令牌)[^\n]{0,12}[:=： ]\s*)([A-Za-z0-9._\-]+)",
            text,
            flags=re.IGNORECASE,
        )
        if github_secret_match:
            updates["github_webhook_secret"] = github_secret_match.group(1).strip()

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

    def _mcp_status_item(self, server: str) -> dict[str, Any] | None:
        """构建单个 MCP server 状态。"""
        built_in = self._builtin_mcp_catalog.get(server, {})
        runtime = self._mcp_servers.get(server, {})
        if not built_in and not runtime:
            return None

        transport = str(runtime.get("transport") or built_in.get("transport") or "stdio")
        command = str(runtime.get("command") or built_in.get("command") or "")
        endpoint = str(runtime.get("endpoint") or "")
        enabled = self._parse_bool(runtime.get("enabled"), default=False)
        configured = bool(endpoint) if transport == "http" else bool(command)

        return {
            "server": server,
            "provider_type": "builtin" if server in self._builtin_mcp_catalog else "custom",
            "display_name": str(
                runtime.get("display_name") or built_in.get("display_name") or server
            ),
            "transport": transport,
            "command": command,
            "endpoint": endpoint,
            "enabled": enabled,
            "configured": configured,
            "description": str(runtime.get("description") or built_in.get("description") or ""),
            "source_url": str(runtime.get("source_url") or built_in.get("source_url") or ""),
            "auth_env": str(runtime.get("auth_env") or ""),
            "instructions": (
                "建议先启用后再补齐 command/endpoint 与鉴权字段。"
                if not configured
                else "已配置，可用于 MCP 能力调用。"
            ),
        }

    def _skill_status_item(self, skill: str) -> dict[str, Any] | None:
        """构建单个 skill 状态。"""
        built_in = self._builtin_skill_catalog.get(skill, {})
        runtime = self._skills.get(skill, {})
        if not built_in and not runtime:
            return None

        return {
            "skill": skill,
            "provider_type": "builtin" if skill in self._builtin_skill_catalog else "custom",
            "display_name": str(
                runtime.get("display_name") or built_in.get("display_name") or skill
            ),
            "source": str(runtime.get("source") or built_in.get("source") or ""),
            "enabled": self._parse_bool(runtime.get("enabled"), default=False),
            "installed": self._skill_installed(skill),
            "description": str(runtime.get("description") or built_in.get("description") or ""),
            "config_values": self._sanitize_config_values(runtime.get("config_values"), default={}),
        }

    def _skill_installed(self, skill: str) -> bool:
        """检查 skill 是否已在本机安装。"""
        codex_home = os.getenv("CODEX_HOME", "").strip()
        candidates: list[Path] = []
        if codex_home:
            candidates.append(Path(codex_home) / "skills" / skill)
        candidates.append(Path.home() / ".codex" / "skills" / skill)
        return any(path.exists() for path in candidates)

    def _normalize_provider_name(self, raw: str) -> str:
        """标准化 provider/server/skill 名称。"""
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

    def _parse_bool(self, raw: Any, default: bool) -> bool:
        """解析布尔值。"""
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, (int, float)):
            return bool(raw)
        if isinstance(raw, str):
            normalized = raw.strip().lower()
            if normalized in {"1", "true", "yes", "on", "enabled"}:
                return True
            if normalized in {"0", "false", "no", "off", "disabled"}:
                return False
        return default

    def _sanitize_config_values(
        self,
        raw: Any,
        *,
        default: dict[str, Any],
    ) -> dict[str, str]:
        """标准化技能配置键值对。"""
        if raw is None:
            raw = default
        if not isinstance(raw, dict):
            return {}

        sanitized: dict[str, str] = {}
        for key, value in raw.items():
            key_text = str(key).strip()
            if not key_text:
                continue
            value_text = str(value).strip()
            if not value_text:
                continue
            sanitized[key_text[:80]] = value_text[:500]
        return sanitized
