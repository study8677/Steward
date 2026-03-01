"""Steward 命令行入口。"""

from __future__ import annotations

import asyncio

import typer
import uvicorn

from steward.core.config import Settings, get_settings
from steward.core.logging import configure_logging
from steward.core.model_config import enforce_model_config
from steward.infra.db.session import db
from steward.services.container import ServiceContainer, build_service_container

app = typer.Typer(help="Steward CLI")


def _init_services() -> tuple[Settings, ServiceContainer]:
    """初始化配置、日志、数据库和服务容器。"""
    settings = get_settings()
    enforce_model_config(settings)
    configure_logging(settings.log_level)
    db.configure(settings.database_url)
    services = build_service_container(settings)
    return settings, services


@app.command("serve")
def serve() -> None:
    """启动 FastAPI 服务。"""
    uvicorn.run("steward.main:app", host="127.0.0.1", port=8000, reload=True)


@app.command("brief")
def brief() -> None:
    """生成并打印最新简报。"""

    async def _run() -> None:
        settings, services = _init_services()
        async with db.session_factory() as session:
            result = await services.briefing_service.generate_latest(
                session, settings.brief_window_hours
            )
            typer.echo(result.markdown)
        await db.dispose()

    asyncio.run(_run())


@app.command("confirm")
def confirm(plan_id: str) -> None:
    """确认指定计划。"""

    async def _run() -> None:
        _settings, services = _init_services()
        async with db.session_factory() as session:
            plan = await services.plan_control_service.confirm(session, plan_id)
            await session.commit()
            typer.echo(f"confirmed: {plan.plan_id} -> {plan.state}")
        await db.dispose()

    asyncio.run(_run())


@app.command("reject")
def reject(plan_id: str) -> None:
    """拒绝指定计划。"""

    async def _run() -> None:
        _settings, services = _init_services()
        async with db.session_factory() as session:
            plan = await services.plan_control_service.reject(session, plan_id)
            await session.commit()
            typer.echo(f"rejected: {plan.plan_id} -> {plan.state}")
        await db.dispose()

    asyncio.run(_run())


if __name__ == "__main__":
    app()
