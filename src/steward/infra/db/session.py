"""数据库会话管理模块。"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class Database:
    """统一管理 AsyncEngine 与 AsyncSessionFactory。"""

    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._database_url: str | None = None

    def configure(self, database_url: str) -> None:
        """初始化数据库连接。"""
        if self._engine is not None and self._database_url == database_url:
            return
        if self._engine is not None:
            raise RuntimeError(
                "Database already configured with another URL; dispose() before reconfigure."
            )
        engine_options: dict[str, object] = {"pool_pre_ping": True}
        if database_url.startswith("sqlite"):
            # SQLite 开发模式下提高并发写容忍度，减少「database is locked」。
            engine_options["connect_args"] = {"timeout": 30}

        self._engine = create_async_engine(database_url, **engine_options)
        if database_url.startswith("sqlite"):
            self._configure_sqlite_pragmas()
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._database_url = database_url

    def _configure_sqlite_pragmas(self) -> None:
        """为 SQLite 连接设置 WAL/busy_timeout 等参数。"""
        if self._engine is None:
            return

        @event.listens_for(self._engine.sync_engine, "connect")
        def _apply_sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA busy_timeout=30000;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.close()

    @property
    def engine(self) -> AsyncEngine:
        """获取已初始化的引擎。"""
        if self._engine is None:
            raise RuntimeError("Database engine has not been configured")
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """获取 Session 工厂。"""
        if self._session_factory is None:
            raise RuntimeError("Database session factory has not been configured")
        return self._session_factory

    async def dispose(self) -> None:
        """关闭引擎连接池。"""
        if self._engine is not None:
            await self._engine.dispose()
        self._engine = None
        self._session_factory = None
        self._database_url = None


db = Database()


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖注入使用的会话生成器。"""
    session_factory = db.session_factory
    async with session_factory() as session:
        yield session
