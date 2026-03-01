"""跨平台屏幕传感器公共逻辑。"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx


@dataclass(slots=True)
class FrontmostWindow:
    """前台窗口快照。"""

    app_name: str
    window_title: str

    def signature(self) -> str:
        """返回用于去重的窗口签名。"""
        return f"{self.app_name.strip()}::{self.window_title.strip()}"


class BaseScreenSensor(ABC):
    """屏幕传感器抽象基类。"""

    def __init__(
        self,
        *,
        base_url: str,
        interval_seconds: float,
        http_timeout_seconds: float,
        webhook_token: str,
        actor: str,
        platform_tag: str,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._interval_seconds = max(2.0, interval_seconds)
        self._http_timeout_seconds = max(5.0, http_timeout_seconds)
        self._webhook_token = webhook_token.strip()
        self._platform_tag = platform_tag.strip().lower() or "unknown"
        self._actor = actor.strip() or f"{self._platform_tag}-screen-sensor"
        self._last_signature = ""

    @property
    def webhook_url(self) -> str:
        """返回屏幕 webhook 地址。"""
        return f"{self._base_url}/api/v1/webhooks/screen"

    def run_forever(self) -> None:
        """持续采集并上报。"""
        print(
            f"[screen-sensor:{self._platform_tag}] started, interval={self._interval_seconds}s, "
            f"target={self.webhook_url}"
        )
        while True:
            try:
                self.collect_once()
            except KeyboardInterrupt:
                print(f"\n[screen-sensor:{self._platform_tag}] stopped by user")
                return
            except Exception as error:  # noqa: BLE001
                print(f"[screen-sensor:{self._platform_tag}] warn: {type(error).__name__}: {error}")
            time.sleep(self._interval_seconds)

    def collect_once(self) -> bool:
        """执行单次采集并在有变化时上报。"""
        snapshot = self._read_frontmost_window()
        signature = snapshot.signature()
        if signature == "::" or signature == self._last_signature:
            return False
        self._send_event(snapshot)
        self._last_signature = signature
        return True

    @abstractmethod
    def _read_frontmost_window(self) -> FrontmostWindow:
        """读取当前前台应用与窗口标题。"""

    def _send_event(self, snapshot: FrontmostWindow) -> None:
        """将屏幕信号写入 Steward 事件链。"""
        app_name = snapshot.app_name.strip() or "unknown-app"
        title = snapshot.window_title.strip()[:120]
        source_title = title[:48]
        summary = f"前台窗口变化[{self._platform_tag}]: app={app_name}, title={title or '-'}"
        entities = [self._platform_tag, app_name]
        if title:
            entities.append(title)
        payload = {
            "source_ref": f"screen:{self._platform_tag}:{app_name}:{source_title}",
            "summary": summary,
            "actor": self._actor,
            "entities": entities,
            "confidence": 0.62,
        }
        headers = {"Content-Type": "application/json"}
        if self._webhook_token:
            headers["x-steward-webhook-token"] = self._webhook_token

        try:
            with httpx.Client(timeout=self._http_timeout_seconds, trust_env=False) as client:
                response = client.post(
                    self.webhook_url,
                    content=json.dumps(payload),
                    headers=headers,
                )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise RuntimeError(f"webhook_http_{error.response.status_code}") from error
        except httpx.TimeoutException as error:
            raise RuntimeError("webhook_timeout") from error
        except httpx.HTTPError as error:
            raise RuntimeError("webhook_unreachable") from error

        print(f"[screen-sensor:{self._platform_tag}] ingested: {app_name} | {title or '-'}")
