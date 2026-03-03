# Steward 项目常用命令集合。

VENV := .venv
PYTHON := $(VENV)/bin/python
UV := $(VENV)/bin/uv

.PHONY: start bootstrap doctor lint test format run worker migrate upgrade downgrade install-skills

# 一键启动（新用户推荐入口）
start:
	@bash scripts/quickstart.sh

install-skills:
	@bash scripts/install_project_skills.sh

bootstrap:
	bash scripts/bootstrap_macos.sh

doctor:
	@echo "[doctor] 检查 Python 与虚拟环境"
	@test -x "$(PYTHON)" || (echo "[doctor] 缺少 $(PYTHON)，请先运行 make bootstrap" && exit 1)
	@$(PYTHON) --version
	@test -x "$(UV)" || (echo "[doctor] 缺少 $(UV)，请先运行 make bootstrap" && exit 1)
	@$(UV) --version
	@echo "[doctor] 检查 Docker Desktop"
	@if command -v docker >/dev/null 2>&1; then docker --version; else echo "[doctor] 警告：未检测到 docker，数据库相关命令将不可用"; fi
	@echo "[doctor] 检查完成"

lint:
	$(UV) run ruff check .
	$(UV) run mypy src tests
	$(UV) run python scripts/check_module_comments.py

test:
	$(UV) run pytest

format:
	$(UV) run ruff format .

run:
	$(UV) run uvicorn steward.main:app --host 127.0.0.1 --port 8000 --reload

worker:
	$(UV) run steward-worker

migrate:
	$(UV) run alembic revision --autogenerate -m "auto migration"

upgrade:
	$(UV) run alembic upgrade head

downgrade:
	$(UV) run alembic downgrade -1
