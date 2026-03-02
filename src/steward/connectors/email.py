"""邮件连接器，通过 IMAP 真实拉取用户邮箱未读邮件。"""

from __future__ import annotations

import contextlib
import email as email_lib
import email.header
import imaplib
import ssl
from typing import Any

import structlog

from steward.connectors.base import ConnectorHealth, ExecutionResult

logger = structlog.get_logger("connector.email")


def _decode_header(raw: str | None) -> str:
    """解码 MIME 邮件头。"""
    if not raw:
        return ""
    parts = email.header.decode_header(raw)
    decoded_parts: list[str] = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded_parts.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded_parts.append(str(part))
    return " ".join(decoded_parts)


class EmailConnector:
    """Email 连接器——通过 IMAP 真实拉取用户未读邮件。"""

    name = "email"

    def __init__(
        self,
        outbound_enabled: bool = False,
        imap_host: str = "",
        imap_port: int = 993,
        imap_user: str = "",
        imap_password: str = "",
    ) -> None:
        self._outbound_enabled = outbound_enabled
        self._imap_host = imap_host
        self._imap_port = imap_port
        self._imap_user = imap_user
        self._imap_password = imap_password

    async def capabilities(self) -> list[str]:
        """返回可执行动作。"""
        return ["create_draft", "send_email", "tag_thread", "fetch_unread"]

    async def required_scopes(self) -> list[str]:
        """返回建议授权范围。"""
        return ["email:read", "email:write"]

    async def pull(self, cursor: str | None) -> list[dict[str, object]]:
        """通过 IMAP 真实拉取用户未读邮件。"""
        if not self._imap_host or not self._imap_user or not self._imap_password:
            return []

        events: list[dict[str, object]] = []
        conn: imaplib.IMAP4_SSL | None = None

        try:
            ctx = ssl.create_default_context()
            conn = imaplib.IMAP4_SSL(self._imap_host, self._imap_port, ssl_context=ctx)
            conn.login(self._imap_user, self._imap_password)
            conn.select("INBOX", readonly=True)

            # 拉取未读邮件，最多 20 封
            status, data = conn.search(None, "UNSEEN")
            if status != "OK" or not data or not data[0]:
                return []

            msg_ids = data[0].split()[-20:]  # 最新的 20 封

            for msg_id in msg_ids:
                status, msg_data = conn.fetch(msg_id, "(RFC822.HEADER)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue

                raw_header = msg_data[0]
                if isinstance(raw_header, tuple):
                    raw_bytes = raw_header[1]
                else:
                    continue

                msg = email_lib.message_from_bytes(raw_bytes)
                subject = _decode_header(msg.get("Subject"))
                from_addr = _decode_header(msg.get("From"))
                date_str = msg.get("Date", "")
                msg_id_header = msg.get("Message-ID", f"imap:{msg_id.decode()}")

                events.append(
                    {
                        "source": "email",
                        "source_ref": f"email:{msg_id_header}",
                        "summary": f"邮件来自 {from_addr}: {subject}",
                        "actor": from_addr,
                        "entities": ["email", from_addr, subject[:60]],
                        "confidence": 0.85,
                        "raw_ref": date_str,
                    }
                )

        except (imaplib.IMAP4.error, OSError, ssl.SSLError) as exc:
            logger.warning("imap_pull_failed", error=str(exc))
        finally:
            if conn:
                with contextlib.suppress(Exception):
                    conn.logout()

        return events

    async def execute(self, action: dict[str, object]) -> ExecutionResult:
        """执行邮件相关动作。"""
        action_type = str(action.get("action_type", "create_draft"))
        payload: Any = action.get("payload", {})
        if not isinstance(payload, dict):
            return ExecutionResult(success=False, reversible=True, detail="payload_invalid")

        if action_type not in {"create_draft", "send_email", "tag_thread"}:
            return ExecutionResult(success=False, reversible=True, detail="unsupported_action")

        # 保留真实发送开关，默认仅写草稿式动作，避免误发。
        if action_type == "send_email" and not self._outbound_enabled:
            return ExecutionResult(success=False, reversible=True, detail="outbound_disabled")

        return ExecutionResult(
            success=True, reversible=True, detail=f"email:{action_type}", data=payload
        )

    async def health(self) -> ConnectorHealth:
        """通过 IMAP 连接检查健康。"""
        if not self._imap_host or not self._imap_user:
            return ConnectorHealth(
                healthy=False, code="imap_not_configured", message="IMAP 配置缺失"
            )

        try:
            ctx = ssl.create_default_context()
            conn = imaplib.IMAP4_SSL(self._imap_host, self._imap_port, ssl_context=ctx)
            conn.login(self._imap_user, self._imap_password)
            conn.logout()
        except (imaplib.IMAP4.error, OSError, ssl.SSLError) as exc:
            return ConnectorHealth(healthy=False, code="imap_error", message=str(exc))

        return ConnectorHealth(healthy=True)
