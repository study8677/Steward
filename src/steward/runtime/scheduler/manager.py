"""APScheduler 管理模块。"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from steward.core.logging import get_logger
from steward.infra.db.session import db
from steward.services.container import ServiceContainer

logger = get_logger(component="scheduler")


class SchedulerManager:
    """统一管理后台定时任务。"""

    def __init__(self, services: ServiceContainer) -> None:
        self._services = services
        self._scheduler = AsyncIOScheduler(timezone=services.settings.timezone)

    async def start(self) -> None:
        """注册并启动任务。"""
        self._scheduler.add_job(
            self._scan_waiting_timeout,
            IntervalTrigger(seconds=self._services.settings.waiting_timeout_scan_seconds),
            id="waiting-timeout-scan",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._generate_periodic_brief,
            IntervalTrigger(hours=self._services.settings.brief_window_hours),
            id="periodic-brief",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info("scheduler_started")

    async def shutdown(self) -> None:
        """关闭任务调度器。"""
        self._scheduler.shutdown(wait=False)
        logger.info("scheduler_stopped")

    async def _scan_waiting_timeout(self) -> None:
        """扫描 WAITING 超时。"""
        async with db.session_factory() as session:
            count = await self._services.waiting_service.scan_timeouts(session)
            await session.commit()
        if count:
            logger.info("waiting_timeout_processed", count=count)

    async def _generate_periodic_brief(self) -> None:
        """按窗口生成简报并记录日志。"""
        async with db.session_factory() as session:
            brief = await self._services.briefing_service.generate_latest(
                session,
                self._services.settings.brief_window_hours,
            )
        logger.info("periodic_brief_generated", length=len(brief.markdown))
