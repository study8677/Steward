#!/usr/bin/env bash
# Steward 一键启动脚本。
# 用法：make start  或  bash scripts/quickstart.sh
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PATH="$PROJECT_ROOT/.venv"
MODEL_CONFIG="$PROJECT_ROOT/config/model.yaml"
MODEL_EXAMPLE="$PROJECT_ROOT/config/model.example.yaml"

# ─── 彩色输出 ───
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${CYAN}[steward]${NC} $1"; }
ok()    { echo -e "${GREEN}✅${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠️${NC}  $1"; }
fail()  { echo -e "${RED}❌${NC} $1"; exit 1; }

echo ""
echo -e "${BOLD}╔══════════════════════════════════════╗${NC}"
echo -e "${BOLD}║     🤖  Steward 一键启动向导        ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════╝${NC}"
echo ""

# ─── 1. 检查 Python ───
info "检查 Python..."
if ! command -v python3 >/dev/null 2>&1; then
  fail "未找到 python3。请先安装 Python 3.14：https://www.python.org/downloads/"
fi
PY_VERSION=$(python3 --version 2>&1)
ok "Python: $PY_VERSION"

# ─── 2. 创建虚拟环境 + 安装依赖 ───
if [[ ! -d "$VENV_PATH" ]]; then
  info "创建虚拟环境..."
  python3 -m venv "$VENV_PATH"
  ok "虚拟环境已创建"
fi

source "$VENV_PATH/bin/activate"

if ! command -v uv >/dev/null 2>&1; then
  info "安装 uv 包管理器..."
  pip install --quiet --upgrade pip
  pip install --quiet "uv==0.8.15"
  ok "uv 已安装"
fi

info "同步项目依赖（首次运行可能需要 1-2 分钟）..."
uv sync --extra dev --extra macos --quiet 2>/dev/null || uv sync --extra dev --quiet
ok "依赖安装完成"

# ─── 3. 模型配置（交互式） ───
echo ""
if [[ -f "$MODEL_CONFIG" ]]; then
  ok "检测到已有模型配置: config/model.yaml"
else
  echo -e "${BOLD}📋 配置大模型 API（必填项）${NC}"
  echo ""
  echo "  Steward 需要一个 OpenAI 兼容的大模型 API 来驱动智能决策。"
  echo "  支持 OpenAI / DeepSeek / 智谱 / Moonshot / NVIDIA 等任意兼容服务。"
  echo ""

  # 选择供应商
  echo -e "${BOLD}请选择大模型供应商：${NC}"
  echo "  1) OpenAI        (https://api.openai.com/v1)"
  echo "  2) DeepSeek      (https://api.deepseek.com/v1)"
  echo "  3) NVIDIA NIM    (https://integrate.api.nvidia.com/v1)"
  echo "  4) 智谱 GLM      (https://open.bigmodel.cn/api/paas/v4)"
  echo "  5) Moonshot Kimi (https://api.moonshot.cn/v1)"
  echo "  6) 自定义 URL"
  echo ""
  read -rp "  请输入序号 [1-6] (默认 1): " PROVIDER_CHOICE
  PROVIDER_CHOICE="${PROVIDER_CHOICE:-1}"

  case "$PROVIDER_CHOICE" in
    1) BASE_URL="https://api.openai.com/v1"; DEFAULT_MODEL="gpt-4o-mini" ;;
    2) BASE_URL="https://api.deepseek.com/v1"; DEFAULT_MODEL="deepseek-chat" ;;
    3) BASE_URL="https://integrate.api.nvidia.com/v1"; DEFAULT_MODEL="meta/llama-3.1-70b-instruct" ;;
    4) BASE_URL="https://open.bigmodel.cn/api/paas/v4"; DEFAULT_MODEL="glm-4-flash" ;;
    5) BASE_URL="https://api.moonshot.cn/v1"; DEFAULT_MODEL="moonshot-v1-8k" ;;
    6)
      read -rp "  请输入 API Base URL: " BASE_URL
      read -rp "  请输入默认模型名称: " DEFAULT_MODEL
      ;;
    *) BASE_URL="https://api.openai.com/v1"; DEFAULT_MODEL="gpt-4o-mini" ;;
  esac
  echo ""

  # 输入 API Key
  read -rp "  请输入 API Key: " API_KEY
  if [[ -z "$API_KEY" ]]; then
    fail "API Key 不能为空，Steward 必须配置大模型才能运行。"
  fi
  echo ""

  # 选择模型（可选）
  read -rp "  使用的模型名称 (直接回车使用默认: $DEFAULT_MODEL): " MODEL_NAME
  MODEL_NAME="${MODEL_NAME:-$DEFAULT_MODEL}"

  # 写入 config/model.yaml
  mkdir -p "$PROJECT_ROOT/config"
  cat > "$MODEL_CONFIG" <<EOF
# Steward 模型配置（由 quickstart 自动生成）
model:
  base_url: "$BASE_URL"
  api_key: "$API_KEY"
  api_key_env: ""
  router: "$MODEL_NAME"
  default: "$MODEL_NAME"
  fallback: "$MODEL_NAME"
  timeout_ms: 30000
  max_retries: 2
  router_min_confidence: 0.70
EOF

  echo ""
  ok "模型配置已写入 config/model.yaml"
fi

# ─── 4. 数据库（SQLite 默认，无需配置） ───
echo ""
info "数据库：使用 SQLite（零配置，数据存储在 steward.db）"
info "如需切换到 Postgres，请设置环境变量 STEWARD_DATABASE_URL"
ok "数据库准备就绪"

# ─── 5. 可选能力包（MCP + Skills） ───
echo ""
echo -e "${BOLD}🧩 可选：启用 GitHub Agent 能力包${NC}"
echo "  包含：GitHub MCP、gh-address-comments、gh-fix-ci、playwright、gog、self-improving-agent、github-api-gateway（已安装项将自动启用）"
read -rp "  是否现在启用？[Y/n]: " ENABLE_GH_BUNDLE
ENABLE_GH_BUNDLE="${ENABLE_GH_BUNDLE:-Y}"

if [[ "$ENABLE_GH_BUNDLE" =~ ^[Yy]$ ]]; then
  info "启用 GitHub 能力包..."
  BUNDLE_JSON="$(python scripts/quickstart_capabilities.py --bundle github || true)"
  if [[ -n "$BUNDLE_JSON" ]]; then
    SUMMARY_LINE="$(python - "$BUNDLE_JSON" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
enabled_mcp = ", ".join(data.get("enabled_mcp", []))
enabled_skills = ", ".join(data.get("enabled_skills", []))
missing_skills = ", ".join(data.get("missing_skills", []))
print(f"{enabled_mcp}|{enabled_skills}|{missing_skills}")
PY
)"
    IFS='|' read -r ENABLED_MCP ENABLED_SKILLS MISSING_SKILLS <<< "$SUMMARY_LINE"
    [[ -n "$ENABLED_MCP" ]] && ok "已启用 MCP: $ENABLED_MCP"
    [[ -n "$ENABLED_SKILLS" ]] && ok "已启用 Skills: $ENABLED_SKILLS"
    if [[ -n "$MISSING_SKILLS" ]]; then
      warn "以下 Skills 未在本机检测到，暂未启用: $MISSING_SKILLS"
      warn "可在 Codex skills 目录安装后，到 Dashboard /integrations 再启用。"
    fi
  else
    warn "能力包启用返回为空，已跳过。"
  fi
fi

# ─── 6. 启动服务 ───
echo ""
echo -e "${BOLD}════════════════════════════════════════${NC}"
echo -e "${GREEN}🚀 一切就绪！正在启动 Steward...${NC}"
echo -e "${BOLD}════════════════════════════════════════${NC}"
echo ""
echo -e "  Dashboard:  ${CYAN}http://127.0.0.1:8000/dashboard${NC}"
echo -e "  API:        ${CYAN}http://127.0.0.1:8000/docs${NC}"
echo ""
echo -e "  按 ${BOLD}Ctrl+C${NC} 停止服务"
echo ""

exec uv run uvicorn steward.main:app --host 127.0.0.1 --port 8000 --reload
