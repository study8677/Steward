"""模型配置文件加载与强制校验测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from steward.core.model_config import load_model_runtime_config


def test_load_model_runtime_config_missing_file(tmp_path: Path) -> None:
    """缺少配置文件时应抛出可读错误。"""
    missing = tmp_path / "missing-model.yaml"
    with pytest.raises(RuntimeError, match="模型配置文件不存在"):
        load_model_runtime_config(missing)


def test_load_model_runtime_config_rejects_placeholder_key(tmp_path: Path) -> None:
    """占位符 API Key 应被拒绝。"""
    config = tmp_path / "model.yaml"
    config.write_text(
        "\n".join(
            [
                "model:",
                '  base_url: "https://api.openai.com/v1"',
                '  api_key: "<your_api_key>"',
                '  router: "router"',
                '  default: "default"',
                '  fallback: "fallback"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="占位符"):
        load_model_runtime_config(config)


def test_load_model_runtime_config_supports_api_key_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """支持通过环境变量名引用 API Key。"""
    config = tmp_path / "model.yaml"
    config.write_text(
        "\n".join(
            [
                "model:",
                '  base_url: "https://api.openai.com/v1"',
                '  api_key: ""',
                '  api_key_env: "TEST_MODEL_API_KEY"',
                '  router: "router"',
                '  default: "default"',
                '  fallback: "fallback"',
                "  timeout_ms: 2000",
                "  max_retries: 1",
                "  router_min_confidence: 0.75",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TEST_MODEL_API_KEY", "sk-test")

    runtime = load_model_runtime_config(config)
    assert runtime.api_key == "sk-test"
    assert runtime.timeout_ms == 2000
    assert runtime.max_retries == 1
    assert runtime.router_min_confidence == pytest.approx(0.75, rel=0.01)
