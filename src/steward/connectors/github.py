"""GitHub 连接器，基于 REST API 处理 issue/PR 通知与动作。"""

from __future__ import annotations

from typing import Any

import httpx

from steward.connectors.base import ConnectorHealth, ExecutionResult


class GitHubConnector:
    """GitHub 连接器实现——真实拉取用户通知、Issue、PR。"""

    name = "github"

    def __init__(
        self,
        token: str,
        repos: str = "",
        base_url: str = "https://api.github.com",
    ) -> None:
        self._token = token
        self._base_url = base_url
        # 用户配置的仓库列表，逗号分隔，如 "owner/repo1,owner/repo2"
        self._repos = [r.strip() for r in repos.split(",") if r.strip()]

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
        return [
            "add_issue_comment",
            "set_issue_state",
            "fetch_notifications",
            "fetch_repo_issues",
            "fetch_repo_pulls",
        ]

    async def required_scopes(self) -> list[str]:
        """返回建议 scope。"""
        return ["notifications", "repo", "issues:read", "issues:write"]

    async def pull(self, cursor: str | None) -> list[dict[str, object]]:
        """真实拉取 GitHub 数据：用户通知 + 仓库 Issue/PR。"""
        if not self._token:
            return []

        events: list[dict[str, object]] = []

        # 1) 拉取用户未读通知
        notif_events = await self._pull_notifications(cursor)
        events.extend(notif_events)

        # 2) 拉取配置仓库的最新 Issue 和 PR
        for repo_full in self._repos:
            issue_events = await self._pull_repo_issues(repo_full)
            events.extend(issue_events)
            pr_events = await self._pull_repo_pulls(repo_full)
            events.extend(pr_events)

        return events

    async def _pull_notifications(self, cursor: str | None) -> list[dict[str, object]]:
        """拉取 GitHub 未读通知。"""
        params: dict[str, str] = {"all": "false"}
        if cursor:
            params["since"] = cursor

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{self._base_url}/notifications",
                    headers=self._headers,
                    params=params,
                )
        except httpx.HTTPError:
            return []

        if response.status_code >= 400:
            return []

        notifications = response.json()
        if not isinstance(notifications, list):
            return []

        events: list[dict[str, object]] = []
        for notif in notifications[:20]:
            subject = notif.get("subject", {})
            repo = notif.get("repository", {})
            repo_full_name = repo.get("full_name", "unknown/unknown")
            subject_title = subject.get("title", "GitHub notification")
            subject_type = subject.get("type", "Unknown")
            reason = notif.get("reason", "subscribed")

            events.append(
                {
                    "source": "github",
                    "source_ref": f"github:notif:{notif.get('id', '')}",
                    "summary": f"[{subject_type}] {repo_full_name}: {subject_title} ({reason})",
                    "actor": "github",
                    "entities": ["github", repo_full_name, subject_type, reason],
                    "confidence": 0.85,
                }
            )

        return events

    async def _pull_repo_issues(self, repo_full: str) -> list[dict[str, object]]:
        """拉取仓库最近的 open Issue。"""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{self._base_url}/repos/{repo_full}/issues",
                    headers=self._headers,
                    params={"state": "open", "sort": "updated", "per_page": "10"},
                )
        except httpx.HTTPError:
            return []

        if response.status_code >= 400:
            return []

        items = response.json()
        if not isinstance(items, list):
            return []

        events: list[dict[str, object]] = []
        for item in items:
            # GitHub API 中 PR 也会出现在 issues 端点，跳过
            if item.get("pull_request"):
                continue

            number = item.get("number", 0)
            title = item.get("title", "")
            user = item.get("user", {}).get("login", "unknown")
            labels = [label.get("name", "") for label in item.get("labels", [])]

            events.append(
                {
                    "source": "github",
                    "source_ref": f"github:issue:{repo_full}#{number}",
                    "summary": f"[Issue #{number}] {repo_full}: {title}",
                    "actor": user,
                    "entities": ["github", repo_full, f"issue#{number}", *labels],
                    "confidence": 0.80,
                }
            )

        return events

    async def _pull_repo_pulls(self, repo_full: str) -> list[dict[str, object]]:
        """拉取仓库最近的 open PR。"""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{self._base_url}/repos/{repo_full}/pulls",
                    headers=self._headers,
                    params={"state": "open", "sort": "updated", "per_page": "10"},
                )
        except httpx.HTTPError:
            return []

        if response.status_code >= 400:
            return []

        items = response.json()
        if not isinstance(items, list):
            return []

        events: list[dict[str, object]] = []
        for item in items:
            number = item.get("number", 0)
            title = item.get("title", "")
            user = item.get("user", {}).get("login", "unknown")
            draft = item.get("draft", False)
            labels = [label.get("name", "") for label in item.get("labels", [])]

            status = "Draft" if draft else "Open"
            events.append(
                {
                    "source": "github",
                    "source_ref": f"github:pr:{repo_full}#{number}",
                    "summary": f"[PR #{number} {status}] {repo_full}: {title}",
                    "actor": user,
                    "entities": ["github", repo_full, f"pr#{number}", status, *labels],
                    "confidence": 0.82,
                }
            )

        return events

    async def execute(self, action: dict[str, object]) -> ExecutionResult:
        """执行 GitHub 动作（真实 API 调用）。"""
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
