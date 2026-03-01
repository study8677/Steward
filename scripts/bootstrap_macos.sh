#!/usr/bin/env bash
# 该脚本用于在 macOS 上初始化 Steward 的独立开发环境。
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PATH="$PROJECT_ROOT/.venv"
MODEL_CONFIG_PATH="$PROJECT_ROOT/config/model.yaml"
MODEL_CONFIG_EXAMPLE="$PROJECT_ROOT/config/model.example.yaml"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "[bootstrap] 当前系统不是 macOS，脚本仅保证 macOS 路径完整。"
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[bootstrap] 未找到 python3，请先安装 Python 3.14。"
  exit 1
fi

if [[ ! -d "$VENV_PATH" ]]; then
  echo "[bootstrap] 创建独立虚拟环境: $VENV_PATH"
  python3 -m venv "$VENV_PATH"
else
  echo "[bootstrap] 复用已存在虚拟环境: $VENV_PATH"
fi

source "$VENV_PATH/bin/activate"

echo "[bootstrap] 升级 pip"
pip install --upgrade pip

echo "[bootstrap] 安装 uv（仅安装到项目虚拟环境）"
pip install "uv==0.8.15"

echo "[bootstrap] 同步依赖"
uv sync --extra dev --extra macos

echo "[bootstrap] 安装 pre-commit hooks"
uv run pre-commit install

if command -v docker >/dev/null 2>&1; then
  echo "[bootstrap] 检测到 Docker: $(docker --version)"
else
  echo "[bootstrap] 未检测到 Docker Desktop。"
  echo "[bootstrap] 如需本地 Postgres，请先安装 Docker Desktop: https://www.docker.com/products/docker-desktop/"
fi

if [[ ! -f "$MODEL_CONFIG_PATH" ]]; then
  if [[ -f "$MODEL_CONFIG_EXAMPLE" ]]; then
    cp "$MODEL_CONFIG_EXAMPLE" "$MODEL_CONFIG_PATH"
    echo "[bootstrap] 已生成模型配置文件: $MODEL_CONFIG_PATH"
    echo "[bootstrap] 请先填写真实模型配置（至少 API Key），再启动服务。"
  else
    echo "[bootstrap] 警告：未找到模板文件 $MODEL_CONFIG_EXAMPLE"
  fi
else
  echo "[bootstrap] 复用已存在模型配置文件: $MODEL_CONFIG_PATH"
fi

echo "[bootstrap] 完成。可执行: make doctor && make test && make lint"
