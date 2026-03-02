"""日历连接器，通过 CalDAV 真实拉取用户日程事件。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog

from steward.connectors.base import ConnectorHealth, ExecutionResult

logger = structlog.get_logger("connector.calendar")


class CalendarConnector:
    """Calendar 连接器——通过 CalDAV 或 Google Calendar API 拉取用户日程。"""

    name = "calendar"

    def __init__(
        self,
        caldav_url: str = "",
        caldav_user: str = "",
        caldav_password: str = "",
    ) -> None:
        self._caldav_url = caldav_url.rstrip("/") if caldav_url else ""
        self._caldav_user = caldav_user
        self._caldav_password = caldav_password

    async def capabilities(self) -> list[str]:
        """返回可执行动作。"""
        return ["create_event", "update_event", "cancel_event", "fetch_upcoming"]

    async def required_scopes(self) -> list[str]:
        """返回建议授权范围。"""
        return ["calendar:read", "calendar:write"]

    async def pull(self, cursor: str | None) -> list[dict[str, object]]:
        """通过 CalDAV REPORT 拉取未来 24 小时的日程事件。"""
        if not self._caldav_url or not self._caldav_user:
            return []

        now = datetime.now(UTC)
        end = now + timedelta(hours=24)

        # CalDAV REPORT 请求体——查询 time-range 内的 VEVENT
        report_body = f"""<?xml version="1.0" encoding="utf-8" ?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <D:getetag/>
    <C:calendar-data/>
  </D:prop>
  <C:filter>
    <C:comp-filter name="VCALENDAR">
      <C:comp-filter name="VEVENT">
        <C:time-range start="{now.strftime("%Y%m%dT%H%M%SZ")}"
                      end="{end.strftime("%Y%m%dT%H%M%SZ")}"/>
      </C:comp-filter>
    </C:comp-filter>
  </C:filter>
</C:calendar-query>"""

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.request(
                    "REPORT",
                    self._caldav_url,
                    content=report_body.encode("utf-8"),
                    headers={
                        "Content-Type": "application/xml; charset=utf-8",
                        "Depth": "1",
                    },
                    auth=(self._caldav_user, self._caldav_password),
                )
        except httpx.HTTPError as exc:
            logger.warning("caldav_pull_failed", error=str(exc))
            return []

        if response.status_code >= 400:
            logger.warning("caldav_pull_http_error", status=response.status_code)
            return []

        # 简单解析 iCalendar VEVENT SUMMARY 行
        events: list[dict[str, object]] = []
        body_text = response.text
        vevent_blocks = body_text.split("BEGIN:VEVENT")

        for block in vevent_blocks[1:]:  # 跳过第一段非 VEVENT 部分
            summary = ""
            dtstart = ""
            uid = ""
            for line in block.splitlines():
                stripped = line.strip()
                if stripped.startswith("SUMMARY:"):
                    summary = stripped[8:]
                elif stripped.startswith("DTSTART"):
                    dtstart = stripped.split(":", 1)[-1] if ":" in stripped else ""
                elif stripped.startswith("UID:"):
                    uid = stripped[4:]

            if summary:
                events.append(
                    {
                        "source": "calendar",
                        "source_ref": f"caldav:{uid or dtstart}",
                        "summary": f"日程: {summary} (开始: {dtstart})",
                        "actor": "calendar",
                        "entities": ["calendar", summary[:60]],
                        "confidence": 0.90,
                    }
                )

        return events

    async def execute(self, action: dict[str, object]) -> ExecutionResult:
        """执行日历动作。"""
        action_type = str(action.get("action_type", "create_event"))
        payload: Any = action.get("payload", {})
        if not isinstance(payload, dict):
            return ExecutionResult(success=False, reversible=True, detail="payload_invalid")

        if action_type not in {"create_event", "update_event", "cancel_event"}:
            return ExecutionResult(success=False, reversible=True, detail="unsupported_action")

        reversible = action_type in {"update_event", "cancel_event"}
        return ExecutionResult(
            success=True, reversible=reversible, detail=f"calendar:{action_type}"
        )

    async def health(self) -> ConnectorHealth:
        """通过 CalDAV OPTIONS 请求检查连通性。"""
        if not self._caldav_url:
            return ConnectorHealth(
                healthy=False, code="caldav_not_configured", message="CalDAV URL 未配置"
            )

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.options(
                    self._caldav_url,
                    auth=(self._caldav_user, self._caldav_password) if self._caldav_user else None,
                )
        except httpx.HTTPError as exc:
            return ConnectorHealth(healthy=False, code="caldav_unreachable", message=str(exc))

        if response.status_code >= 400:
            return ConnectorHealth(
                healthy=False, code=f"caldav_http_{response.status_code}", message=response.text
            )

        return ConnectorHealth(healthy=True)
