"""模型网关服务，提供 OpenAI 兼容接口与回退策略。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx
import structlog

from steward.core.config import Settings
from steward.domain.schemas import RouteDecision
from steward.observability.metrics import LLM_ROUTE_LATENCY_SECONDS


@dataclass(slots=True)
class SpaceCandidate:
    """用于路由的空间候选。"""

    space_id: str
    focus_ref: str
    entities: list[str]


class ModelGateway:
    """统一封装模型调用。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._logger = structlog.get_logger("model_gateway")
        self._github_actor_login: str | None = None

    def is_model_configured(self) -> bool:
        """模型 API 是否可用。"""
        return bool(self._settings.model_api_key.strip())

    async def route_space(
        self,
        event_summary: str,
        event_entities: list[str],
        candidates: list[SpaceCandidate],
        *,
        allow_model: bool = True,
    ) -> RouteDecision:
        """将事件路由到已有空间或 NEW。"""
        started = perf_counter()
        self._logger.info(
            "route_space_start",
            summary=event_summary[:50],
            candidates_count=len(candidates),
        )
        try:
            if allow_model and self._settings.model_api_key and candidates:
                decision = await self._route_with_model(event_summary, event_entities, candidates)
                if decision is not None:
                    if decision.confidence < self._settings.model_router_min_confidence:
                        return RouteDecision(
                            target="NEW",
                            confidence=decision.confidence,
                            reason="model_low_confidence_fallback_to_new",
                        )
                    self._logger.info(
                        "route_space_decision_model",
                        target=decision.target,
                        confidence=decision.confidence,
                        reason=decision.reason,
                    )
                    return decision

            heuristic_decision = self._route_with_heuristics(
                event_summary, event_entities, candidates
            )
            self._logger.info(
                "route_space_decision_heuristic",
                target=heuristic_decision.target,
                confidence=heuristic_decision.confidence,
                reason=heuristic_decision.reason,
            )
            return heuristic_decision
        finally:
            elapsed = perf_counter() - started
            LLM_ROUTE_LATENCY_SECONDS.observe(elapsed)

    async def summarize_pending_plan(
        self,
        *,
        plan_id: str,
        intent: str,
        risk_level: str,
        priority: str,
        reversibility: str,
        steps: list[dict[str, object]],
    ) -> str:
        """为待确认计划生成用户可读摘要。"""
        heuristic = self._build_pending_summary_heuristic(
            intent=intent,
            risk_level=risk_level,
            priority=priority,
            reversibility=reversibility,
            steps=steps,
        )
        if not self._settings.model_api_key:
            return heuristic

        payload = {
            "model": self._settings.model_default,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是执行计划解释助手。"
                        "请把待确认计划总结成一句中文，便于用户快速决定确认或拒绝。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "输出要求：\n"
                        "1) 只输出一句中文，不要 Markdown。\n"
                        "2) 必须同时包含：将执行什么 + 主要风险。\n"
                        "3) 18-50 字，避免空话。\n"
                        f"计划ID: {plan_id}\n"
                        f"intent: {intent}\n"
                        f"risk_level: {risk_level}\n"
                        f"priority: {priority}\n"
                        f"reversibility: {reversibility}\n"
                        f"steps_json: {json.dumps(steps, ensure_ascii=False)}"
                    ),
                },
            ],
            "temperature": 0.0,
        }
        timeout = self._settings.model_timeout_ms / 1000
        headers = {
            "Authorization": f"Bearer {self._settings.model_api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self._settings.model_base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
        except httpx.HTTPError:
            return heuristic

        if response.status_code >= 400:
            return heuristic

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            return heuristic
        content = str(choices[0].get("message", {}).get("content", "")).strip()
        if not content:
            return heuristic
        return self._normalize_pending_summary(content, fallback=heuristic)

    async def summarize_executed_plan(
        self,
        *,
        plan_id: str,
        intent: str,
        steps: list[dict[str, object]],
        outcome: str,
        reason: str,
        content_level: str = "medium",
    ) -> str:
        """为已执行完毕/被阻断的计划生成自然语言总结汇报。"""
        level = self._normalize_brief_content_level(content_level)
        fallback = self._build_executed_summary_fallback(
            intent=intent,
            steps=steps,
            outcome=outcome,
            reason=reason,
            content_level=level,
        )
        if not self.is_model_configured():
            self._logger.warning("summarize_executed_plan_no_api_key")
            return fallback

        payload = {
            "model": self._settings.model_default,
            "messages": [
                {
                    "role": "system",
                    "content": self._executed_summary_system_prompt(level),
                },
                {
                    "role": "user",
                    "content": (
                        "输出要求：\n"
                        f"{self._executed_summary_output_requirements(level)}\n"
                        f"计划ID: {plan_id}\n"
                        f"意图: {intent}\n"
                        f"步骤: {json.dumps(steps, ensure_ascii=False)}\n"
                        f"执行结果(outcome): {outcome}\n"
                        f"详情/原因(reason): {reason}"
                    ),
                },
            ],
            "temperature": 0.0,
        }

        timeout = self._settings.model_timeout_ms / 1000
        headers = {
            "Authorization": f"Bearer {self._settings.model_api_key}",
            "Content-Type": "application/json",
        }
        self._logger.info(
            "summarize_executed_plan_start",
            plan_id=plan_id[:8],
            model=self._settings.model_default,
            base_url=self._settings.model_base_url,
        )
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self._settings.model_base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            self._logger.error("summarize_executed_plan_http_error", error=str(exc))
            return fallback

        if response.status_code >= 400:
            self._logger.error(
                "summarize_executed_plan_api_error",
                status_code=response.status_code,
                body=response.text[:200],
            )
            return fallback

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            self._logger.warning("summarize_executed_plan_empty_choices", data=str(data)[:200])
            return fallback

        content = str(choices[0].get("message", {}).get("content", "")).strip()
        if not content:
            return fallback

        # Clean up output
        text = self._normalize_executed_summary(content, content_level=level, fallback=fallback)
        self._logger.info("summarize_executed_plan_ok", plan_id=plan_id[:8], summary=text[:50])
        return text

    async def summarize_runtime_decisions(
        self,
        *,
        decisions: list[dict[str, Any]],
    ) -> dict[str, str]:
        """为运行日志中的决策记录生成人话摘要（批量）。"""
        if not decisions:
            return {}

        fallback_map: dict[str, str] = {}
        compact_items: list[dict[str, str]] = []

        for item in decisions:
            decision_id = str(item.get("decision_id", "")).strip()
            if not decision_id:
                continue

            intent = str(item.get("intent", "follow_up"))
            reason = str(item.get("reason", ""))
            gate_result = str(item.get("gate_result", ""))
            state_from = str(item.get("state_from", ""))
            state_to = str(item.get("state_to", ""))
            outcome = str(item.get("outcome", ""))
            steps_raw = item.get("steps", [])
            steps = steps_raw if isinstance(steps_raw, list) else []
            action_detail = self._extract_action_detail(intent=intent, steps=steps)

            fallback_map[decision_id] = self._build_runtime_decision_fallback(
                intent=intent,
                gate_result=gate_result,
                state_from=state_from,
                state_to=state_to,
                reason=reason,
                outcome=outcome,
                action_detail=action_detail,
            )
            compact_items.append(
                {
                    "decision_id": decision_id,
                    "intent": intent,
                    "gate_result": gate_result,
                    "state_from": state_from,
                    "state_to": state_to,
                    "outcome": outcome,
                    "action": action_detail,
                    "reason": reason[:120],
                }
            )

        if not compact_items or not self.is_model_configured():
            return fallback_map

        payload = {
            "model": self._settings.model_default,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是系统运行日志摘要助手。"
                        "请把机器可读的决策日志转成人类可读的一句话中文。"
                        "必须准确、客观、简短。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "只输出 JSON，不要 Markdown，不要解释。\n"
                        '输出 schema: {"items":[{"decision_id":"...","summary":"..."}]}\n'
                        "要求：\n"
                        "1) 每条 summary 用中文 18-48 字。\n"
                        "2) 必须包含：做了什么 + 当前结果。\n"
                        "3) 禁止输出 UUID、snake_case、状态码、字段名。\n"
                        f"输入: {json.dumps(compact_items, ensure_ascii=False)}"
                    ),
                },
            ],
            "temperature": 0.0,
        }

        parsed = await self._call_json_completion(payload)
        if not parsed:
            return fallback_map

        items = parsed.get("items", [])
        if not isinstance(items, list):
            return fallback_map

        summaries = dict(fallback_map)
        for entry in items:
            if not isinstance(entry, dict):
                continue
            decision_id = str(entry.get("decision_id", "")).strip()
            if not decision_id or decision_id not in summaries:
                continue
            raw_summary = str(entry.get("summary", "")).strip()
            summaries[decision_id] = self._normalize_runtime_summary(
                raw_summary,
                fallback=summaries[decision_id],
            )
        return summaries

    async def plan_event_execution(
        self,
        *,
        event_summary: str,
        source: str,
        source_ref: str,
        entities: list[str],
        default_intent: str,
        default_risk_level: str,
        default_priority: str,
        default_reversibility: str,
        default_requires_confirmation: bool,
        candidate_steps: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Use LLM to produce a structured executable plan draft for one event."""
        fallback = {
            "intent": default_intent,
            "risk_level": default_risk_level,
            "priority": default_priority,
            "reversibility": default_reversibility,
            "requires_confirmation": bool(default_requires_confirmation),
            "steps": self._normalize_plan_steps(candidate_steps),
            "wait_condition": None,
            "resume_trigger": None,
        }
        if not self.is_model_configured():
            return fallback

        payload = {
            "model": self._settings.model_default,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是执行计划生成器。请基于事件内容输出可执行计划 JSON，禁止输出解释。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "只输出 JSON，不要 Markdown。\n"
                        'schema: {"intent":"...","risk_level":"low|medium|high","priority":"P0|P1|P2",'
                        '"reversibility":"reversible|irreversible","requires_confirmation":true|false,'
                        '"steps":[{"connector":"...","action_type":"...","payload":{},"verification":{},"retryable":true}],'
                        '"wait_condition":"...|null","resume_trigger":"...|null"}\n'
                        "要求：\n"
                        "1) steps 必须可执行，禁止 noop/placeholder。\n"
                        "2) 对高风险或不可逆动作，requires_confirmation 必须为 true。\n"
                        "3) 如果信息不足，保持 steps 为最小安全动作。\n"
                        f"event_summary: {event_summary}\n"
                        f"source: {source}\n"
                        f"source_ref: {source_ref}\n"
                        f"entities: {json.dumps(entities, ensure_ascii=False)}\n"
                        f"default_intent: {default_intent}\n"
                        f"default_risk_level: {default_risk_level}\n"
                        f"default_priority: {default_priority}\n"
                        f"default_reversibility: {default_reversibility}\n"
                        f"default_requires_confirmation: {default_requires_confirmation}\n"
                        f"candidate_steps: {json.dumps(candidate_steps, ensure_ascii=False)}"
                    ),
                },
            ],
            "temperature": 0.0,
        }
        parsed = await self._call_json_completion(payload)
        if not parsed:
            return fallback

        intent = str(parsed.get("intent", default_intent)).strip()[:128] or default_intent
        risk_level = str(parsed.get("risk_level", default_risk_level)).strip().lower()
        if risk_level not in {"low", "medium", "high"}:
            risk_level = default_risk_level

        priority = str(parsed.get("priority", default_priority)).strip().upper()
        if priority not in {"P0", "P1", "P2"}:
            priority = default_priority

        reversibility = str(parsed.get("reversibility", default_reversibility)).strip().lower()
        if reversibility not in {"reversible", "irreversible"}:
            reversibility = default_reversibility

        requires_confirmation = bool(
            parsed.get("requires_confirmation", default_requires_confirmation)
        )
        if risk_level == "high" or reversibility == "irreversible":
            requires_confirmation = True

        raw_steps = parsed.get("steps", candidate_steps)
        steps = self._normalize_plan_steps(raw_steps)
        if not steps:
            steps = fallback["steps"]

        wait_condition_raw = parsed.get("wait_condition")
        wait_condition = (
            str(wait_condition_raw).strip()[:255]
            if isinstance(wait_condition_raw, str) and wait_condition_raw.strip()
            else None
        )
        resume_trigger_raw = parsed.get("resume_trigger")
        resume_trigger = (
            str(resume_trigger_raw).strip()[:255]
            if isinstance(resume_trigger_raw, str) and resume_trigger_raw.strip()
            else None
        )

        return {
            "intent": intent,
            "risk_level": risk_level,
            "priority": priority,
            "reversibility": reversibility,
            "requires_confirmation": requires_confirmation,
            "steps": steps,
            "wait_condition": wait_condition,
            "resume_trigger": resume_trigger,
        }

    async def reflect_execution_step(
        self,
        *,
        plan_id: str,
        intent: str,
        step_index: int,
        step: dict[str, Any],
        step_success: bool,
        step_detail: str,
        remaining_steps: int,
    ) -> dict[str, Any]:
        """Reflect on one executed step and decide continue/halt/replan."""
        fallback = {
            "decision": "continue",
            "summary": "本步骤已完成，继续执行后续步骤。",
            "next_steps": [],
        }
        if not self.is_model_configured():
            return fallback

        payload = {
            "model": self._settings.model_default,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是执行反思器。根据步骤执行结果判断是否继续、停止或重规划。只输出 JSON。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "只输出 JSON，不要解释，不要 Markdown。\n"
                        'schema: {"decision":"continue|halt|replan","summary":"...","next_steps":[...]}'
                        "\n要求：\n"
                        "1) 若 decision=continue 或 halt，next_steps 必须为空数组。\n"
                        "2) 若 decision=replan，next_steps 必须是可执行步骤列表。\n"
                        "3) summary 用中文一句话，18-48 字。\n"
                        f"plan_id: {plan_id}\n"
                        f"intent: {intent}\n"
                        f"step_index: {step_index}\n"
                        f"current_step: {json.dumps(step, ensure_ascii=False)}\n"
                        f"step_success: {step_success}\n"
                        f"step_detail: {step_detail[:200]}\n"
                        f"remaining_steps: {remaining_steps}"
                    ),
                },
            ],
            "temperature": 0.0,
        }
        parsed = await self._call_json_completion(payload)
        if not parsed:
            return fallback

        decision = str(parsed.get("decision", "continue")).strip().lower()
        if decision not in {"continue", "halt", "replan"}:
            decision = "continue"

        summary = self._normalize_runtime_summary(
            str(parsed.get("summary", "")).strip(),
            fallback=fallback["summary"],
        )
        next_steps = self._normalize_plan_steps(parsed.get("next_steps", []), limit=8)
        if decision != "replan":
            next_steps = []
        if decision == "replan" and not next_steps:
            decision = "continue"

        return {
            "decision": decision,
            "summary": summary,
            "next_steps": next_steps,
        }

    async def compose_github_issue_reply(
        self,
        *,
        owner: str,
        repo: str,
        issue_number: int,
        event_summary: str,
        intent: str,
        repo_context: str,
    ) -> str:
        """Compose a contextual GitHub issue reply using issue + local repo context."""
        issue_context = await self._fetch_github_issue_context(
            owner=owner,
            repo=repo,
            issue_number=issue_number,
        )
        fallback = self._build_github_issue_reply_fallback(
            owner=owner,
            repo=repo,
            issue_number=issue_number,
            event_summary=event_summary,
            issue_context=issue_context,
            repo_context=repo_context,
        )
        if not self.is_model_configured():
            return fallback

        payload = {
            "model": self._settings.model_default,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是仓库协作助手。请基于 Issue 内容和仓库上下文，"
                        "生成可直接发布到 GitHub issue 的回复。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "输出要求：\n"
                        "1) 输出纯文本，不要 Markdown 标题，不要代码块。\n"
                        "2) 必须中英双语，先中文再英文。\n"
                        "3) 每种语言 2-5 行，总长度 120-420 字符。\n"
                        "4) 必须包含：你理解的问题 + 当前仓库已具备能力 + 下一步建议。\n"
                        "5) 禁止虚构尚未实现的能力；无法确认时用“建议确认/please verify”。\n"
                        "6) 语气专业、简洁，避免模板化口头禅。\n"
                        f"repo: {owner}/{repo}\n"
                        f"issue_number: {issue_number}\n"
                        f"intent: {intent}\n"
                        f"event_summary: {event_summary}\n"
                        f"issue_context_json: {json.dumps(issue_context, ensure_ascii=False)}\n"
                        f"repo_context: {repo_context[:5000]}"
                    ),
                },
            ],
            "temperature": 0.2,
        }

        timeout = self._settings.model_timeout_ms / 1000
        headers = {
            "Authorization": f"Bearer {self._settings.model_api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self._settings.model_base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
        except httpx.HTTPError:
            return fallback
        if response.status_code >= 400:
            return fallback

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            return fallback
        content = str(choices[0].get("message", {}).get("content", "")).strip()
        return self._normalize_github_issue_reply(content, fallback=fallback)

    async def parse_integration_config_text(self, text: str) -> dict[str, Any]:
        """将自然语言转成接入配置字段。"""
        fallback = {"updates": {}, "custom_providers": [], "reason": "model_unavailable"}
        if not self._settings.model_api_key:
            return {"updates": {}, "custom_providers": [], "reason": "no_model_api_key"}

        payload = {
            "model": self._settings.model_default,
            "messages": [
                {
                    "role": "system",
                    "content": ("你是系统配置解析器。仅输出 JSON，不输出解释。"),
                },
                {
                    "role": "user",
                    "content": (
                        "请从下面自然语言中提取 webhook 配置字段。\n"
                        "仅允许提取字段："
                        "slack_signing_secret, "
                        "gmail_pubsub_verification_token, "
                        "gmail_pubsub_topic, "
                        "google_calendar_channel_token, "
                        "google_calendar_channel_ids, "
                        "screen_webhook_secret。\n"
                        "若用户在新增自定义信息源，请输出 custom_providers 数组。"
                        "source 只允许 manual|email|chat|calendar|github|screen|local|custom。\n"
                        '输出 schema: {"updates":{"field":"value"},"custom_providers":[{"provider":"name","source":"chat","webhook_secret":"x","description":""}],"reason":"<=30字"}\n'
                        f"输入：{text}"
                    ),
                },
            ],
            "temperature": 0.0,
        }
        parsed = await self._call_json_completion(payload)
        if not parsed:
            return fallback
        updates = parsed.get("updates", {})
        if not isinstance(updates, dict):
            updates = {}
        custom_providers = parsed.get("custom_providers", [])
        if not isinstance(custom_providers, list):
            custom_providers = []
        reason = str(parsed.get("reason", "model_parse_success"))
        return {
            "updates": updates,
            "custom_providers": custom_providers,
            "reason": reason[:80],
        }

    async def is_github_actor_self(self, login: str) -> bool:
        """Check whether the given GitHub login matches current token owner."""
        actor = login.strip().lower()
        if not actor:
            return False
        current = await self._get_github_actor_login()
        if not current:
            return False
        return actor == current.lower()

    async def _fetch_github_issue_context(
        self,
        *,
        owner: str,
        repo: str,
        issue_number: int,
    ) -> dict[str, Any]:
        """Fetch issue title/body/comments for grounded reply generation."""
        empty: dict[str, Any] = {"title": "", "body": "", "comments": []}
        token = self._settings.github_token.strip()
        if not token:
            return empty

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {token}",
        }
        issue_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
        comments_url = f"{issue_url}/comments"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                issue_resp = await client.get(issue_url, headers=headers)
                comments_resp = await client.get(
                    comments_url,
                    headers=headers,
                    params={"per_page": "3", "sort": "created", "direction": "desc"},
                )
        except httpx.HTTPError:
            return empty
        if issue_resp.status_code >= 400:
            return empty

        issue_data = issue_resp.json() if issue_resp.content else {}
        comments_data = comments_resp.json() if comments_resp.status_code < 400 else []
        title = ""
        body = ""
        if isinstance(issue_data, dict):
            title = str(issue_data.get("title", "")).strip()
            body = str(issue_data.get("body", "")).strip()

        comments: list[dict[str, str]] = []
        if isinstance(comments_data, list):
            for item in comments_data[:3]:
                if not isinstance(item, dict):
                    continue
                user = item.get("user", {})
                login = str(user.get("login", "")) if isinstance(user, dict) else ""
                comment_body = str(item.get("body", "")).strip()
                if not comment_body:
                    continue
                comments.append({"author": login, "body": comment_body[:400]})

        return {
            "title": title[:300],
            "body": body[:1500],
            "comments": comments,
        }

    async def _get_github_actor_login(self) -> str:
        """Resolve GitHub login bound to configured token."""
        if self._github_actor_login is not None:
            return self._github_actor_login
        token = self._settings.github_token.strip()
        if not token:
            self._github_actor_login = ""
            return ""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {token}",
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get("https://api.github.com/user", headers=headers)
        except httpx.HTTPError:
            self._github_actor_login = ""
            return ""
        if response.status_code >= 400:
            self._github_actor_login = ""
            return ""
        data = response.json()
        login = str(data.get("login", "")).strip() if isinstance(data, dict) else ""
        self._github_actor_login = login
        return login

    def _build_github_issue_reply_fallback(
        self,
        *,
        owner: str,
        repo: str,
        issue_number: int,
        event_summary: str,
        issue_context: dict[str, Any],
        repo_context: str,
    ) -> str:
        """Deterministic bilingual fallback when model/network is unavailable."""
        title = str(issue_context.get("title", "")).strip()
        body = str(issue_context.get("body", "")).strip()
        top_line = title or event_summary or f"Issue #{issue_number}"
        zh_capability = "已接入规划、门禁、异步执行与执行日志。"
        if "github webhook" in repo_context.lower() or "webhook" in repo_context.lower():
            zh_capability = "当前仓库已接入 GitHub webhook、计划生成、worker 异步执行与结果追踪。"
        en_capability = "The repo already supports GitHub webhook ingestion, planning, async worker execution, and execution tracing."
        zh = (
            f"已收到并理解这个问题：{top_line[:120]}。\n"
            f"{zh_capability}\n"
            "建议下一步：请补充可复现步骤/期望结果，我们会基于仓库现状继续细化处理。"
        )
        en = (
            f"Got it. We understand this request: {top_line[:120]}.\n"
            f"{en_capability}\n"
            "Next step: please add reproduction steps and expected behavior; we will refine the follow-up based on the current codebase."
        )
        if body:
            zh = f"{zh}\n补充说明：已读取 issue 描述并纳入判断。"
            en = f"{en}\nAdditional note: the issue description has been considered."
        return self._normalize_github_issue_reply(f"{zh}\n\n{en}", fallback=f"{zh}\n\n{en}")

    def _normalize_github_issue_reply(self, content: str, *, fallback: str) -> str:
        """Normalize generated issue reply for safe posting."""
        text = content.replace("\r", "").strip()
        if not text:
            return fallback
        text = re.sub(r"```[\s\S]*?```", "", text).strip()
        if not text:
            return fallback
        if len(text) > 1200:
            text = text[:1200].rstrip()
        if len(text) < 60:
            return fallback
        return text

    def build_local_repo_context(
        self,
        *,
        workspace_dir: str | Path,
        file_limit: int = 3,
    ) -> str:
        """Load a compact local repository context snippet for grounded responses."""
        base = Path(workspace_dir).expanduser().resolve()
        candidates = ["README.md", "README_CN.md", "agent.md", "AGENTS.md"]
        chunks: list[str] = []
        for name in candidates:
            if len(chunks) >= file_limit:
                break
            path = base / name
            if not path.exists() or not path.is_file():
                continue
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError:
                continue
            normalized = re.sub(r"\s+", " ", raw).strip()
            if not normalized:
                continue
            chunks.append(f"[{name}] {normalized[:1200]}")
        return "\n".join(chunks)

    async def parse_natural_language_event_text(self, text: str) -> dict[str, Any]:
        """将自然语言描述解析为事件字段。"""
        fallback = self._build_nl_event_fallback(text)
        if not self._settings.model_api_key:
            return fallback

        payload = {
            "model": self._settings.model_default,
            "messages": [
                {
                    "role": "system",
                    "content": "你是事件结构化解析器，只输出 JSON。",
                },
                {
                    "role": "user",
                    "content": (
                        "从输入文本中抽取事件。\n"
                        "source 只允许：manual|email|chat|calendar|github|screen|local|custom。\n"
                        '输出 schema: {"source":"manual","summary":"...","source_ref":"...","entities":["..."],"confidence":0.0}\n'
                        "要求：summary 用中文一句话；source_ref 若无明确引用可自动生成。\n"
                        f"输入：{text}"
                    ),
                },
            ],
            "temperature": 0.0,
        }
        parsed = await self._call_json_completion(payload)
        if not parsed:
            return fallback

        source = str(parsed.get("source", "manual")).strip().lower()
        allowed_sources = {
            "manual",
            "email",
            "chat",
            "calendar",
            "github",
            "screen",
            "local",
            "custom",
        }
        if source not in allowed_sources:
            source = "manual"
        summary = str(parsed.get("summary", "")).strip() or fallback["summary"]
        source_ref = str(parsed.get("source_ref", "")).strip() or fallback["source_ref"]
        entities_raw = parsed.get("entities", [])
        entities = (
            [str(item).strip() for item in entities_raw] if isinstance(entities_raw, list) else []
        )
        entities = [item for item in entities if item][:12]

        confidence_raw = parsed.get("confidence", 0.85)
        try:
            confidence = float(confidence_raw)
        except TypeError, ValueError:
            confidence = 0.85
        confidence = max(0.0, min(1.0, confidence))

        return {
            "source": source,
            "summary": summary[:240],
            "source_ref": source_ref[:255],
            "entities": entities,
            "confidence": confidence,
        }

    async def _route_with_model(
        self,
        event_summary: str,
        event_entities: list[str],
        candidates: list[SpaceCandidate],
    ) -> RouteDecision | None:
        """通过多项选择题式 Prompt 调用模型路由。"""
        narrowed_candidates = self._select_candidates_for_model(
            event_summary=event_summary,
            event_entities=event_entities,
            candidates=candidates,
        )

        prompt = self._build_router_prompt(
            event_summary=event_summary,
            event_entities=event_entities,
            candidates=narrowed_candidates,
        )
        payload = {
            "model": self._settings.model_router,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是 Context Space 路由器。"
                        "你只能进行多项选择，不得产生新的任务或解释性长文。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
        }

        timeout = self._settings.model_timeout_ms / 1000
        headers = {
            "Authorization": f"Bearer {self._settings.model_api_key}",
            "Content-Type": "application/json",
        }

        self._logger.debug("llm_route_request_start", model=self._settings.model_router)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self._settings.model_base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
        except httpx.HTTPError as e:
            self._logger.error("llm_route_request_error", error=str(e))
            return None

        if response.status_code >= 400:
            self._logger.error(
                "llm_route_request_failed",
                status_code=response.status_code,
                text=response.text[:200],
            )
            return None

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            self._logger.warning("llm_route_response_empty_choices")
            return None

        content = str(choices[0].get("message", {}).get("content", "")).strip()
        self._logger.debug("llm_route_response", content=content)
        if not content:
            return None

        return self._parse_router_response(content, narrowed_candidates)

    def _build_router_prompt(
        self,
        event_summary: str,
        event_entities: list[str],
        candidates: list[SpaceCandidate],
    ) -> str:
        """构建严格输出约束的路由 Prompt。"""
        candidate_text = "\n".join(
            [
                f"- {item.space_id} | focus={item.focus_ref or '-'} | entities={','.join(item.entities[:8])}"
                for item in candidates
            ]
        )

        return (
            "任务：判断新事件属于哪个 Context Space，或输出 NEW。\n"
            "规则：\n"
            "1) 只能从候选中选择 SPACE_<id> 或 NEW。\n"
            "2) 如果证据不足，优先 NEW。\n"
            "3) 只输出 JSON，不要 Markdown。\n"
            "输出 JSON schema："
            '{"target":"SPACE_xxx|NEW","confidence":0.0,"reason":"<=20字"}\n\n'
            f"候选列表：\n{candidate_text}\n\n"
            f"新事件摘要：{event_summary}\n"
            f"新事件实体：{','.join(event_entities) or '-'}"
        )

    def _parse_router_response(
        self,
        content: str,
        candidates: list[SpaceCandidate],
    ) -> RouteDecision | None:
        """解析模型路由输出。"""
        candidate_ids = {item.space_id for item in candidates}

        parsed = self._parse_json_object(content)
        if parsed:
            target = str(parsed.get("target", "")).strip()
            confidence_raw = parsed.get("confidence", 0.0)
            reason = str(parsed.get("reason", "model_router"))
            try:
                confidence = float(confidence_raw)
            except TypeError, ValueError:
                confidence = 0.0

            if target == "NEW" or target in candidate_ids:
                return RouteDecision(
                    target=target,
                    confidence=max(0.0, min(1.0, confidence)),
                    reason=reason[:80],
                )

        # JSON 解析失败时，回退正则提取。
        target_match = re.search(r"(SPACE_[A-Za-z0-9_-]+|NEW)", content)
        confidence_match = re.search(r"confidence\s*[:=]\s*(0(?:\.\d+)?|1(?:\.0+)?)", content)
        if target_match is None:
            return None

        target = target_match.group(1)
        confidence = float(confidence_match.group(1)) if confidence_match else 0.55
        if target != "NEW" and target not in candidate_ids:
            return None

        return RouteDecision(target=target, confidence=confidence, reason="model_regex_fallback")

    def _parse_json_object(self, content: str) -> dict[str, Any] | None:
        """提取并解析响应中的 JSON 对象。"""
        try:
            direct = json.loads(content)
            if isinstance(direct, dict):
                return direct
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if match is None:
            return None

        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

        return parsed if isinstance(parsed, dict) else None

    def _select_candidates_for_model(
        self,
        event_summary: str,
        event_entities: list[str],
        candidates: list[SpaceCandidate],
    ) -> list[SpaceCandidate]:
        """在进入模型前做轻量候选压缩。"""
        summary_lower = event_summary.lower()
        entity_set = {item.lower() for item in event_entities}

        scored: list[tuple[float, SpaceCandidate]] = []
        for candidate in candidates:
            score = 0.0
            if candidate.focus_ref and candidate.focus_ref.lower() in summary_lower:
                score += 0.6
            overlap = len(entity_set & {item.lower() for item in candidate.entities})
            score += min(0.4, overlap * 0.12)
            scored.append((score, candidate))

        scored.sort(key=lambda item: item[0], reverse=True)
        narrowed = [item for _, item in scored[:12]]
        return narrowed or candidates[:12]

    def _route_with_heuristics(
        self,
        event_summary: str,
        event_entities: list[str],
        candidates: list[SpaceCandidate],
    ) -> RouteDecision:
        """模型不可用时采用启发式路由。"""
        if not candidates:
            return RouteDecision(target="NEW", confidence=0.9, reason="no_candidates")

        summary_lower = event_summary.lower()
        event_entity_set = {item.lower() for item in event_entities}

        scored: list[tuple[str, float]] = []
        for candidate in candidates:
            score = 0.0
            if candidate.focus_ref and candidate.focus_ref.lower() in summary_lower:
                score += 0.6

            candidate_entities = {item.lower() for item in candidate.entities}
            overlap = len(event_entity_set & candidate_entities)
            score += min(0.4, overlap * 0.2)
            scored.append((candidate.space_id, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        top_id, top_score = scored[0]
        if top_score < 0.35:
            return RouteDecision(target="NEW", confidence=0.55, reason="heuristic_low_score")

        return RouteDecision(
            target=top_id,
            confidence=min(top_score, 0.99),
            reason="heuristic_match",
        )

    def _build_pending_summary_heuristic(
        self,
        *,
        intent: str,
        risk_level: str,
        priority: str,
        reversibility: str,
        steps: list[dict[str, object]],
    ) -> str:
        """在模型不可用时构建可读摘要。"""
        connector = "manual"
        action_type = intent
        detail = ""
        if steps:
            first_step = steps[0]
            connector = str(first_step.get("connector", "manual"))
            action_type = str(first_step.get("action_type", intent))
            payload = first_step.get("payload", {})
            if isinstance(payload, dict):
                for key in ("summary", "text", "body", "title", "subject", "intent"):
                    raw_value = payload.get(key)
                    if raw_value:
                        detail = str(raw_value).strip()
                        break

        risk_text = {
            "high": "高风险",
            "medium": "中风险",
            "low": "低风险",
        }.get(risk_level.lower(), risk_level)
        sentence = (
            f"将通过 {connector} 执行 {action_type}"
            f"{'：' + detail if detail else ''}；"
            f"风险 {risk_text}，优先级 {priority}，{reversibility}，建议人工确认。"
        )
        return self._normalize_pending_summary(
            sentence, fallback="该计划为待确认任务，请根据风险后再执行。"
        )

    def _normalize_brief_content_level(self, content_level: str) -> str:
        """标准化简报内容层级。"""
        level = content_level.strip().lower()
        if level not in {"simple", "medium", "rich"}:
            return "medium"
        return level

    def _executed_summary_system_prompt(self, content_level: str) -> str:
        """返回分层级的系统 Prompt。"""
        if content_level == "simple":
            return "你是系统执行简报助手。输出短句式中文结果，优先传达动作与结果，避免背景解释。"
        if content_level == "rich":
            return (
                "你是系统执行简报助手。输出信息密度较高的中文总结，覆盖动作、结果、风险或后续建议。"
            )
        return "你是系统执行简报助手。请根据计划意图、步骤、最终结果和原因，写一句客观的中文战报。"

    def _executed_summary_output_requirements(self, content_level: str) -> str:
        """返回分层级输出约束。"""
        if content_level == "simple":
            return (
                "1) 只输出一句中文，不带 Markdown，不要出现 '根据...'\n"
                "2) 必须包含核心动作和最终结果。\n"
                "3) 12-28 字，越短越好。"
            )
        if content_level == "rich":
            return (
                "1) 仅输出中文，不带 Markdown。\n"
                "2) 输出 1-2 句，覆盖：执行动作 + 最终结果 + 关键原因/风险。\n"
                "3) 40-110 字，信息密度高但不啰嗦。"
            )
        return (
            "1) 只输出一句中文，不带 Markdown，不要出现 '根据...'\n"
            "2) 必须包含核心动作的业务含义和最终结果（成功/失败原因）。\n"
            "3) 18-50 字，精简干练，体现助理帮用户处理完事情的状态。"
        )

    def _build_executed_summary_fallback(
        self,
        *,
        intent: str,
        steps: list[dict[str, object]],
        outcome: str,
        reason: str,
        content_level: str,
    ) -> str:
        """模型不可用时构建执行摘要回退文案。"""
        action_detail = self._extract_action_detail(intent=intent, steps=steps)
        result = self._normalize_outcome(outcome)
        reason_text = reason.strip()
        if content_level == "simple":
            sentence = f"{action_detail}，结果：{result}。"
            return self._normalize_executed_summary(
                sentence,
                content_level=content_level,
                fallback="任务已处理，结果请查看计划详情。",
            )
        if content_level == "rich":
            rich_sentence = (
                f"已执行 {action_detail}，结果：{result}。"
                f"{' 关键原因：' + reason_text + '。' if reason_text else ''}"
                "如需调整策略，可在反馈入口标注此 plan。"
            )
            return self._normalize_executed_summary(
                rich_sentence,
                content_level=content_level,
                fallback="任务已执行完成，请在计划详情中查看完整结果与原因。",
            )
        medium_sentence = (
            f"已执行 {action_detail}，结果：{result}"
            f"{'，原因：' + reason_text if reason_text else ''}。"
        )
        return self._normalize_executed_summary(
            medium_sentence,
            content_level=content_level,
            fallback="任务已执行完成，请查看计划详情。",
        )

    def _extract_action_detail(self, *, intent: str, steps: list[dict[str, object]]) -> str:
        """从步骤中提取核心动作信息。"""
        if not steps:
            return intent or "任务"
        first_step = steps[0]
        connector = str(first_step.get("connector", "manual"))
        action_type = str(first_step.get("action_type", intent or "follow_up"))
        detail = ""
        payload = first_step.get("payload")
        if isinstance(payload, dict):
            for key in ("summary", "text", "body", "title", "subject", "intent"):
                value = payload.get(key)
                if value:
                    detail = str(value).strip()
                    break
        if detail:
            return f"{connector}.{action_type}（{detail[:40]}）"
        return f"{connector}.{action_type}"

    def _normalize_outcome(self, outcome: str) -> str:
        """标准化执行结果。"""
        normalized = outcome.strip().lower()
        mapping = {
            "succeeded": "成功",
            "success": "成功",
            "failed": "失败",
            "pending": "待处理",
            "running": "执行中",
            "blocked": "受阻",
            "canceled": "已取消",
        }
        return mapping.get(normalized, outcome or "未知")

    def _normalize_executed_summary(
        self,
        content: str,
        *,
        content_level: str,
        fallback: str,
    ) -> str:
        """按层级清洗执行摘要输出。"""
        text = content.replace("\n", " ").replace("\r", " ").strip()
        if not text:
            return fallback

        max_length = 80 if content_level == "simple" else (220 if content_level == "rich" else 140)
        if len(text) > max_length:
            text = f"{text[: max_length - 3]}..."
        return text

    def _normalize_pending_summary(self, content: str, *, fallback: str) -> str:
        """清洗模型/启发式输出，统一长度与可读性。"""
        text = content.replace("\n", " ").replace("\r", " ").strip()
        if not text:
            return fallback
        if len(text) > 120:
            text = f"{text[:117]}..."
        return text

    def _build_runtime_decision_fallback(
        self,
        *,
        intent: str,
        gate_result: str,
        state_from: str,
        state_to: str,
        reason: str,
        outcome: str,
        action_detail: str,
    ) -> str:
        """模型不可用时，生成可读的日志摘要。"""
        normalized_reason = reason.strip().lower()
        normalized_outcome = self._normalize_outcome(outcome)

        reason_map = {
            "low_risk_auto_execute": "系统评估为低风险，已自动放行执行。",
            "async_execution_completed": "系统已完成自动执行并记录结果。",
            "execution_engine_disabled": "执行引擎当前关闭，任务未进入自动执行。",
            "wait_timeout_triggered": "等待外部反馈超时，系统已转回重新评估。",
            "resume_trigger_matched": "检测到恢复条件，系统已继续执行流程。",
            "medium_risk_default_to_brief": "事项风险中等，已进入简报待你决策。",
        }
        if normalized_reason.startswith("auto_execution_dispatched"):
            return "系统已通过门禁并加入执行队列，正在后台处理。"
        if normalized_reason.startswith("step_") and "invalid" in normalized_reason:
            return "执行前校验未通过，系统已阻止该步骤进入执行。"
        if normalized_reason in reason_map:
            return reason_map[normalized_reason]

        gate_text = {
            "auto": "自动执行",
            "confirm": "人工确认",
            "brief": "进入简报",
            "blocked": "已阻断",
        }.get(gate_result.strip().lower(), gate_result or "决策")
        state_map = {
            "NEW": "新建",
            "PLANNED": "已计划",
            "GATED": "已门禁",
            "RUNNING": "执行中",
            "SUCCEEDED": "已成功",
            "FAILED": "已失败",
            "WAITING": "等待中",
            "CONFLICTED": "冲突中",
            "ROLLED_BACK": "已回滚",
        }
        from_text = state_map.get(state_from.strip().upper(), state_from.strip() or "未知状态")
        to_text = state_map.get(state_to.strip().upper(), state_to.strip() or "未知状态")

        sentence = (
            f"系统对 {intent or '任务'} 做出“{gate_text}”决策，"
            f"当前从 {from_text} 变更为 {to_text}，"
            f"动作 {action_detail}，结果 {normalized_outcome}。"
        )
        return self._normalize_runtime_summary(
            sentence,
            fallback="系统已记录该条决策，详情可在计划中查看。",
        )

    def _normalize_runtime_summary(self, content: str, *, fallback: str) -> str:
        """清洗运行日志摘要，避免展示机器码样式。"""
        text = content.replace("\n", " ").replace("\r", " ").strip()
        if not text:
            return fallback

        text = re.sub(r"\b[0-9a-f]{8,}\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\b[A-Z_]{2,}\b", "", text)
        text = re.sub(r"\s{2,}", " ", text).strip(" .|:;，,")
        if not text:
            return fallback
        if len(text) > 120:
            text = f"{text[:117]}..."
        return text

    def _normalize_plan_steps(self, raw_steps: Any, *, limit: int = 12) -> list[dict[str, Any]]:
        """Normalize model/raw plan steps into execution-safe dictionaries."""
        if not isinstance(raw_steps, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in raw_steps[:limit]:
            if not isinstance(item, dict):
                continue
            connector = str(item.get("connector", "")).strip().lower()
            action_type = str(item.get("action_type", "")).strip()
            payload_raw = item.get("payload", {})
            payload = payload_raw if isinstance(payload_raw, dict) else {}
            verification_raw = item.get("verification", {})
            verification = verification_raw if isinstance(verification_raw, dict) else {}
            retryable = bool(item.get("retryable", True))

            if not connector or not action_type:
                continue

            normalized.append(
                {
                    "connector": connector,
                    "action_type": action_type,
                    "payload": payload,
                    "verification": verification,
                    "retryable": retryable,
                }
            )
        return normalized

    async def _call_json_completion(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """调用模型并尝试解析 JSON。"""
        timeout = self._settings.model_timeout_ms / 1000
        headers = {
            "Authorization": f"Bearer {self._settings.model_api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self._settings.model_base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
        except httpx.HTTPError:
            return None
        if response.status_code >= 400:
            return None

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            return None
        content = str(choices[0].get("message", {}).get("content", "")).strip()
        if not content:
            return None
        parsed = self._parse_json_object(content)
        return parsed if isinstance(parsed, dict) else None

    def _build_nl_event_fallback(self, text: str) -> dict[str, Any]:
        """自然语言事件解析失败时的兜底结构。"""
        normalized = text.strip()
        compact = re.sub(r"\s+", "-", normalized[:40]) or "event"
        source_ref = f"manual:nl:{compact}"
        entities = list(re.findall(r"[A-Za-z0-9_-]{3,}", normalized)[:8])
        return {
            "source": "manual",
            "summary": normalized[:240],
            "source_ref": source_ref[:255],
            "entities": entities,
            "confidence": 0.86,
        }
