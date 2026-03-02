"""Connector cursor/bookmark persistence helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from steward.infra.db.models import ConnectorSyncState


class ConnectorStateStore:
    """Persist per-instance stream sync state."""

    async def get_state(
        self,
        session: AsyncSession,
        *,
        instance_id: str,
        stream_name: str,
    ) -> ConnectorSyncState | None:
        """Fetch state for one connector stream."""
        stmt = select(ConnectorSyncState).where(
            ConnectorSyncState.instance_id == instance_id,
            ConnectorSyncState.stream_name == stream_name,
        )
        return (await session.execute(stmt)).scalars().first()

    async def upsert_state(
        self,
        session: AsyncSession,
        *,
        instance_id: str,
        stream_name: str,
        cursor_payload: dict[str, Any],
        bookmark: str | None = None,
    ) -> ConnectorSyncState:
        """Create or update state for one connector stream."""
        current = await self.get_state(
            session,
            instance_id=instance_id,
            stream_name=stream_name,
        )
        if current is None:
            current = ConnectorSyncState(
                instance_id=instance_id,
                stream_name=stream_name,
                cursor_payload=cursor_payload,
                bookmark=bookmark,
                checkpoint_at=datetime.now(UTC),
            )
            session.add(current)
            await session.flush()
            return current

        current.cursor_payload = cursor_payload
        current.bookmark = bookmark
        current.checkpoint_at = datetime.now(UTC)
        await session.flush()
        return current
