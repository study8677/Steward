"""GitHub 连接器，基于 REST API 处理 issue/comment 相关动作。"""

from __future__ import annotations

from typing import Any

import httpx

from steward.connectors.base import ConnectorHealth, ExecutionResult


class GitHubConnector:
    """GitHub 连接器实现。"""

    name = "github"

    def __init__(self, token: str, base_url: str = "https://api.github.com") -> None:
        self._token = token
        self._base_url = base_url

    @property
    def _headers(self) -> dict[str, str]:
        """构建授权请求头。"""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def capabilities(self) -> list[str]:
        """返回支持能力。"""
        return ["add_issue_comment", "set_issue_state", "fetch_issue_events"]

    async def required_scopes(self) -> list[str]:
        """返回建议 scope。"""
        return ["issues:read", "issues:write"]

    async def pull(self, cursor: str | None) -> list[dict[str, object]]:
        """拉取 Issue 事件（占位实现，当前直接返回空）。"""
        _ = cursor
        return []

    async def execute(self, action: dict[str, object]) -> ExecutionResult:
        """执行 GitHub 动作。"""
        action_type = str(action.get("action_type", ""))
        payload = action.get("payload", {})
        if not isinstance(payload, dict):
            return ExecutionResult(success=False, reversible=True, detail="payload_invalid")

        if action_type == "add_issue_comment":
            return await self._add_issue_comment(payload)
        if action_type == "set_issue_state":
            return await self._set_issue_state(payload)

        return ExecutionResult(success=False, reversible=True, detail=f"unsupported:{action_type}")

    async def _add_issue_comment(self, payload: dict[str, Any]) -> ExecutionResult:
        """给指定 issue 增加评论。"""
        owner = str(payload.get("owner", ""))
        repo = str(payload.get("repo", ""))
        issue_number = int(payload.get("issue_number", 0))
        body = str(payload.get("body", ""))
        if not owner or not repo or issue_number <= 0 or not body:
            return ExecutionResult(success=False, reversible=True, detail="payload_missing")

        url = f"{self._base_url}/repos/{owner}/{repo}/issues/{issue_number}/comments"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=self._headers, json={"body": body})

        if response.status_code >= 400:
            return ExecutionResult(
                success=False,
                reversible=True,
                detail=f"github_error:{response.status_code}",
                data={"body": response.text},
            )

        return ExecutionResult(success=True, reversible=True, detail="comment_created")

    async def _set_issue_state(self, payload: dict[str, Any]) -> ExecutionResult:
        """设置 issue 状态（open/closed）。"""
        owner = str(payload.get("owner", ""))
        repo = str(payload.get("repo", ""))
        issue_number = int(payload.get("issue_number", 0))
        state = str(payload.get("state", "open"))
        if state not in {"open", "closed"}:
            return ExecutionResult(success=False, reversible=False, detail="state_invalid")
        if not owner or not repo or issue_number <= 0:
            return ExecutionResult(success=False, reversible=False, detail="payload_missing")

        url = f"{self._base_url}/repos/{owner}/{repo}/issues/{issue_number}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.patch(url, headers=self._headers, json={"state": state})

        if response.status_code >= 400:
            return ExecutionResult(
                success=False,
                reversible=False,
                detail=f"github_error:{response.status_code}",
                data={"body": response.text},
            )

        return ExecutionResult(success=True, reversible=False, detail="issue_state_updated")

    async def health(self) -> ConnectorHealth:
        """通过 /rate_limit 检查 API 健康。"""
        if not self._token:
            return ConnectorHealth(
                healthy=False, code="missing_token", message="STEWARD_GITHUB_TOKEN empty"
            )

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self._base_url}/rate_limit", headers=self._headers)

        if response.status_code >= 400:
            return ConnectorHealth(
                False, code=f"http_{response.status_code}", message=response.text
            )
        return ConnectorHealth(True)
