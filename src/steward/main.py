"""FastAPI 应用入口。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from steward.api.routers import (
    briefs,
    dashboard,
    events,
    feedback,
    health,
    integrations,
    metrics,
    plans,
    spaces,
    ui,
    webhooks,
)
from steward.core.config import get_settings
from steward.core.logging import configure_logging, get_logger
from steward.core.model_config import enforce_model_config

# 确保模型被导入，避免 metadata 不完整。
from steward.infra.db import models as _models  # noqa: F401
from steward.infra.db.base import Base
from steward.infra.db.session import db
from steward.observability.tracing import configure_tracing
from steward.runtime.scheduler.manager import SchedulerManager
from steward.services.container import build_service_container
from steward.services.webhook_backpressure import WebhookBackpressureService

logger = get_logger(component="app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """应用生命周期管理。"""
    settings = get_settings()
    enforce_model_config(settings)
    configure_logging(settings.log_level)
    configure_tracing()

    db.configure(settings.database_url)
    if settings.database_url.startswith("sqlite"):
        async with db.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    services = build_service_container(settings)
    scheduler = SchedulerManager(services)
    webhook_backpressure = WebhookBackpressureService(
        max_inflight_per_provider=settings.webhook_backpressure_max_inflight,
        max_events_per_window=settings.webhook_backpressure_max_events_per_window,
        window_seconds=settings.webhook_backpressure_window_seconds,
        dedup_ttl_seconds=settings.webhook_backpressure_dedup_ttl_seconds,
    )

    app.state.settings = settings
    app.state.services = services
    app.state.scheduler = scheduler
    app.state.webhook_backpressure = webhook_backpressure

    if settings.enable_scheduler:
        await scheduler.start()
    logger.info("app_started", env=settings.env)
    try:
        yield
    finally:
        if settings.enable_scheduler:
            await scheduler.shutdown()
        await db.dispose()
        logger.info("app_stopped")


app = FastAPI(title="Steward", version="0.1.0", lifespan=lifespan)
app.mount(
    "/ui",
    StaticFiles(directory=Path(__file__).resolve().parent / "ui" / "static"),
    name="ui",
)
app.include_router(health.router)
app.include_router(events.router)
app.include_router(webhooks.router)
app.include_router(spaces.router)
app.include_router(plans.router)
app.include_router(briefs.router)
app.include_router(feedback.router)
app.include_router(dashboard.router)
app.include_router(integrations.router)
app.include_router(ui.router)
app.include_router(metrics.router)


def run() -> None:
    """脚本入口。"""
    uvicorn.run("steward.main:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    run()
