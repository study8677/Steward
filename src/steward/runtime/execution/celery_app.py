"""Celery app factory for Steward execution workers."""

from __future__ import annotations

from celery import Celery

from steward.core.config import get_settings


def _create_app() -> Celery:
    settings = get_settings()
    app = Celery(
        "steward",
        broker=settings.execution_redis_url,
        backend=settings.execution_redis_url,
        include=["steward.runtime.execution.tasks"],
    )
    app.conf.update(
        task_default_queue="steward.execution",
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_track_started=True,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
    )
    return app


celery_app = _create_app()
