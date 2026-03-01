"""模型配置文件加载与强制校验模块。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from steward.core.config import Settings


@dataclass(slots=True)
class ModelRuntimeConfig:
    """模型运行配置。"""

    base_url: str
    api_key: str
    router: str
    default: str
    fallback: str
    timeout_ms: int
    max_retries: int
    router_min_confidence: float


def enforce_model_config(settings: Settings) -> None:
    """强制加载模型配置文件，并写回到运行时 Settings。

    当 config/model.yaml 不存在但环境变量 STEWARD_MODEL_API_KEY 已设置时，
    跳过文件加载，直接使用环境变量中的配置。
    """
    config_path = Path(settings.model_config_file)

    if config_path.exists():
        runtime_config = load_model_runtime_config(config_path)
        settings.model_base_url = runtime_config.base_url
        settings.model_api_key = runtime_config.api_key
        settings.model_router = runtime_config.router
        settings.model_default = runtime_config.default
        settings.model_fallback = runtime_config.fallback
        settings.model_timeout_ms = runtime_config.timeout_ms
        settings.model_max_retries = runtime_config.max_retries
        settings.model_router_min_confidence = runtime_config.router_min_confidence
        return

    # model.yaml 不存在时，尝试从环境变量读取
    if settings.model_api_key:
        # 环境变量 STEWARD_MODEL_API_KEY 已设置，跳过文件加载
        return

    raise RuntimeError(
        "模型配置缺失。请选择以下任一方式配置：\n"
        "  方式 A：复制 config/model.example.yaml 为 config/model.yaml 并填写 api_key\n"
        "  方式 B：设置环境变量 STEWARD_MODEL_API_KEY=<你的 API Key>\n"
        "未配置模型时 Steward 无法启动。"
    )


def load_model_runtime_config(config_path: Path) -> ModelRuntimeConfig:
    """从 YAML 文件读取模型配置并进行严格校验。"""
    if not config_path.exists():
        raise RuntimeError(
            f"模型配置文件不存在: {config_path}。"
            "请复制 config/model.example.yaml 为 config/model.yaml 并完成配置后再启动。"
        )

    try:
        raw_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise RuntimeError(f"模型配置文件 YAML 解析失败: {config_path}") from error

    if not isinstance(raw_data, dict):
        raise RuntimeError(f"模型配置文件格式错误: {config_path} 顶层必须是对象。")

    model_block = raw_data.get("model")
    if not isinstance(model_block, dict):
        raise RuntimeError(f"模型配置文件缺少 `model` 对象: {config_path}")

    base_url = _require_non_empty(model_block, "base_url", config_path)
    router = _require_non_empty(model_block, "router", config_path)
    default = _require_non_empty(model_block, "default", config_path)
    fallback = _require_non_empty(model_block, "fallback", config_path)

    api_key_raw = str(model_block.get("api_key", "")).strip()
    api_key_env = str(model_block.get("api_key_env", "")).strip()
    api_key = _resolve_api_key(api_key_raw, api_key_env, config_path)

    timeout_ms = _safe_int(model_block.get("timeout_ms", 12000), "timeout_ms", config_path)
    max_retries = _safe_int(model_block.get("max_retries", 2), "max_retries", config_path)
    router_min_confidence = _safe_float(
        model_block.get("router_min_confidence", 0.70),
        "router_min_confidence",
        config_path,
    )
    if not 0.0 <= router_min_confidence <= 1.0:
        raise RuntimeError(f"模型配置项 `router_min_confidence` 必须在 [0,1] 区间: {config_path}")

    return ModelRuntimeConfig(
        base_url=base_url,
        api_key=api_key,
        router=router,
        default=default,
        fallback=fallback,
        timeout_ms=timeout_ms,
        max_retries=max_retries,
        router_min_confidence=router_min_confidence,
    )


def _require_non_empty(model_block: dict[str, Any], field_name: str, config_path: Path) -> str:
    """读取并校验非空字符串字段。"""
    value = str(model_block.get(field_name, "")).strip()
    if not value:
        raise RuntimeError(f"模型配置项 `{field_name}` 不能为空: {config_path}")
    return value


def _resolve_api_key(api_key_raw: str, api_key_env: str, config_path: Path) -> str:
    """解析 API Key（支持直接值或环境变量引用）。"""
    if api_key_raw:
        api_key = api_key_raw
    elif api_key_env:
        api_key = os.getenv(api_key_env, "").strip()
        if not api_key:
            raise RuntimeError(f"模型配置要求从环境变量 `{api_key_env}` 读取 API Key，但当前为空。")
    else:
        raise RuntimeError(
            f"模型配置缺少 API Key: {config_path}，请设置 `model.api_key` 或 `model.api_key_env`。"
        )

    invalid_tokens = {
        "<your_api_key>",
        "your_api_key",
        "replace_me",
        "changeme",
        "todo",
    }
    if api_key.strip().lower() in invalid_tokens:
        raise RuntimeError("模型 API Key 仍是占位符，请填写真实值后再启动。")
    return api_key


def _safe_int(raw: Any, field_name: str, config_path: Path) -> int:
    """安全解析整数字段。"""
    try:
        value = int(raw)
    except (TypeError, ValueError) as error:
        raise RuntimeError(f"模型配置项 `{field_name}` 需要整数: {config_path}") from error
    if value < 0:
        raise RuntimeError(f"模型配置项 `{field_name}` 不能为负数: {config_path}")
    return value


def _safe_float(raw: Any, field_name: str, config_path: Path) -> float:
    """安全解析浮点数字段。"""
    try:
        return float(raw)
    except (TypeError, ValueError) as error:
        raise RuntimeError(f"模型配置项 `{field_name}` 需要浮点数: {config_path}") from error
