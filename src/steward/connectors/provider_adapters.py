"""真实 Provider Webhook 适配器：GitHub/Gmail/Slack/Google Calendar。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from steward.core.config import Settings
from steward.domain.enums import SourceType
from steward.domain.schemas import EventIngestRequest


@dataclass(slots=True)
class VerificationResult:
    """验签结果。"""

    ok: bool
    reason: str
    dedup_key: str | None = None


class SlackWebhookAdapter:
    """Slack 事件适配器。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def verify(self, raw_body: bytes, headers: dict[str, str]) -> VerificationResult:
        """校验 Slack HMAC 签名。"""
        secret = self._settings.slack_signing_secret
        if not secret:
            return VerificationResult(ok=False, reason="slack_signing_secret_missing")

        timestamp = headers.get("x-slack-request-timestamp", "")
        signature = headers.get("x-slack-signature", "")
        if not timestamp or not signature:
            return VerificationResult(ok=False, reason="slack_signature_header_missing")

        try:
            ts = int(timestamp)
        except ValueError:
            return VerificationResult(ok=False, reason="slack_timestamp_invalid")

        now_ts = int(datetime.now(UTC).timestamp())
        if abs(now_ts - ts) > 300:
            return VerificationResult(ok=False, reason="slack_timestamp_expired")

        base_string = f"v0:{timestamp}:{raw_body.decode('utf-8', errors='ignore')}".encode()
        digest = hmac.new(secret.encode("utf-8"), base_string, hashlib.sha256).hexdigest()
        expected = f"v0={digest}"
        if not hmac.compare_digest(expected, signature):
            return VerificationResult(ok=False, reason="slack_signature_mismatch")

        return VerificationResult(ok=True, reason="ok")

    def normalize(self, payload: dict[str, Any]) -> EventIngestRequest:
        """标准化 Slack 事件。"""
        event = payload.get("event", {})
        if not isinstance(event, dict):
            event = {}

        event_id = str(payload.get("event_id", ""))
        channel = str(event.get("channel", "unknown"))
        ts = str(event.get("ts", "0"))
        user = str(event.get("user", "slack"))
        text = str(event.get("text", "slack event"))
        event_type = str(event.get("type", payload.get("type", "event_callback")))

        return EventIngestRequest(
            source=SourceType.CHAT,
            source_ref=f"slack:{channel}:{ts}",
            actor=user,
            summary=text,
            confidence=0.9,
            raw_ref=event_id or None,
            entities=["slack", channel, event_type],
        )


class GitHubWebhookAdapter:
    """GitHub 事件适配器（Issue/PR/comment）。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def verify(self, raw_body: bytes, headers: dict[str, str]) -> VerificationResult:
        """校验 GitHub HMAC 签名。"""
        event = headers.get("x-github-event", "").strip()
        delivery = headers.get("x-github-delivery", "").strip()
        if not event:
            return VerificationResult(ok=False, reason="github_event_missing")
        if not delivery:
            return VerificationResult(ok=False, reason="github_delivery_missing")

        secret = self._settings.github_webhook_secret.strip()
        if not secret:
            return VerificationResult(ok=False, reason="github_webhook_secret_missing")

        signature = headers.get("x-hub-signature-256", "").strip()
        if not signature.startswith("sha256="):
            return VerificationResult(ok=False, reason="github_signature_missing")

        digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        expected = f"sha256={digest}"
        if not hmac.compare_digest(expected, signature):
            return VerificationResult(ok=False, reason="github_signature_mismatch")

        return VerificationResult(ok=True, reason="ok", dedup_key=delivery)

    def normalize(self, payload: dict[str, Any], *, event_type: str) -> EventIngestRequest:
        """标准化 GitHub webhook 事件。"""
        action = str(payload.get("action", "updated")).strip() or "updated"
        sender = payload.get("sender", {})
        actor = str(sender.get("login", "github")) if isinstance(sender, dict) else "github"
        repo = payload.get("repository", {})
        repo_full = (
            str(repo.get("full_name", "unknown/unknown"))
            if isinstance(repo, dict)
            else "unknown/unknown"
        )

        issue = payload.get("issue", {})
        pr = payload.get("pull_request", {})
        comment = payload.get("comment", {})

        summary = f"GitHub {event_type} {action}"
        source_ref = f"github:{event_type}:{repo_full}"
        entities = ["github", repo_full, event_type, action]

        if isinstance(issue, dict) and issue:
            number = int(issue.get("number", 0) or 0)
            title = str(issue.get("title", "")).strip()
            issue_body = str(issue.get("body", "")).strip()
            source_ref = f"github:issue:{repo_full}#{number}" if number > 0 else source_ref
            summary = f"[{repo_full}] Issue #{number} {action}: {title or '(no title)'}"
            if issue_body:
                summary = f"{summary} | body: {issue_body[:120]}"
            entities.append(f"issue#{number}")
        elif isinstance(pr, dict) and pr:
            number = int(pr.get("number", 0) or 0)
            title = str(pr.get("title", "")).strip()
            pr_body = str(pr.get("body", "")).strip()
            source_ref = f"github:pr:{repo_full}#{number}" if number > 0 else source_ref
            summary = f"[{repo_full}] PR #{number} {action}: {title or '(no title)'}"
            if pr_body:
                summary = f"{summary} | body: {pr_body[:120]}"
            entities.append(f"pr#{number}")

        if isinstance(comment, dict) and comment:
            body = str(comment.get("body", "")).strip()
            comment_user = comment.get("user", {})
            comment_author = (
                str(comment_user.get("login", "")).strip() if isinstance(comment_user, dict) else ""
            )
            if body:
                summary = f"{summary} | comment: {body[:80]}"
            if comment_author:
                summary = f"{summary} | by: {comment_author}"
            entities.append("comment")

        return EventIngestRequest(
            source=SourceType.GITHUB,
            source_ref=source_ref,
            actor=actor,
            summary=summary,
            confidence=0.93,
            raw_ref=source_ref,
            entities=entities,
        )


class GmailWebhookAdapter:
    """Gmail Pub/Sub 推送适配器。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def verify(self, headers: dict[str, str]) -> VerificationResult:
        """校验 Gmail 推送身份字段。"""
        expected_token = self._settings.gmail_pubsub_verification_token
        if expected_token:
            auth = headers.get("authorization", "")
            if auth != f"Bearer {expected_token}":
                return VerificationResult(ok=False, reason="gmail_auth_invalid")

        expected_topic = self._settings.gmail_pubsub_topic
        if expected_topic:
            topic = headers.get("x-goog-topic", "")
            if topic and topic != expected_topic:
                return VerificationResult(ok=False, reason="gmail_topic_mismatch")

        return VerificationResult(ok=True, reason="ok")

    def normalize(self, payload: dict[str, Any]) -> tuple[EventIngestRequest, str | None]:
        """标准化 Gmail Pub/Sub 事件。"""
        message = payload.get("message", {})
        if not isinstance(message, dict):
            message = {}

        message_id = str(message.get("messageId", ""))
        encoded_data = str(message.get("data", ""))

        decoded: dict[str, Any] = {}
        if encoded_data:
            decoded = self._decode_base64_json(encoded_data)

        email_address = str(decoded.get("emailAddress", "unknown"))
        history_id = str(decoded.get("historyId", "0"))

        request = EventIngestRequest(
            source=SourceType.EMAIL,
            source_ref=f"gmail:{email_address}:{history_id}",
            actor=email_address,
            summary=f"Gmail 收到更新通知（historyId={history_id}）",
            confidence=0.88,
            raw_ref=message_id or None,
            entities=["gmail", email_address, history_id],
        )
        return request, message_id or None

    def _decode_base64_json(self, encoded_data: str) -> dict[str, Any]:
        """解码 Pub/Sub data 字段。"""
        padded = encoded_data + "=" * (-len(encoded_data) % 4)
        try:
            raw = base64.urlsafe_b64decode(padded.encode("utf-8"))
            parsed = json.loads(raw.decode("utf-8"))
        except ValueError, json.JSONDecodeError:
            return {}

        return parsed if isinstance(parsed, dict) else {}


class GoogleCalendarWebhookAdapter:
    """Google Calendar 推送适配器。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def verify(self, headers: dict[str, str]) -> VerificationResult:
        """校验 Calendar channel token。"""
        expected_token = self._settings.google_calendar_channel_token
        channel_token = headers.get("x-goog-channel-token", "")
        if expected_token and channel_token != expected_token:
            return VerificationResult(ok=False, reason="calendar_channel_token_invalid")

        expected_ids = [
            item.strip()
            for item in self._settings.google_calendar_channel_ids.split(",")
            if item.strip()
        ]
        if expected_ids:
            channel_id = headers.get("x-goog-channel-id", "")
            if channel_id not in expected_ids:
                return VerificationResult(ok=False, reason="calendar_channel_id_invalid")

        dedup_key = (
            f"{headers.get('x-goog-channel-id', '')}:{headers.get('x-goog-message-number', '')}"
        )
        return VerificationResult(ok=True, reason="ok", dedup_key=dedup_key)

    def normalize(self, headers: dict[str, str], payload: dict[str, Any]) -> EventIngestRequest:
        """标准化 Calendar 事件。"""
        channel_id = headers.get("x-goog-channel-id", "unknown")
        message_number = headers.get("x-goog-message-number", "0")
        resource_state = headers.get("x-goog-resource-state", "exists")
        resource_id = headers.get("x-goog-resource-id", "unknown")
        summary = str(payload.get("summary", f"Google Calendar 更新：{resource_state}"))

        return EventIngestRequest(
            source=SourceType.CALENDAR,
            source_ref=f"gcal:{channel_id}:{message_number}",
            actor="google-calendar",
            summary=summary,
            confidence=0.9,
            raw_ref=resource_id,
            entities=["google-calendar", channel_id, resource_state, resource_id],
        )
