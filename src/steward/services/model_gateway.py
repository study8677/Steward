"""模型网关服务，提供 OpenAI 兼容接口与回退策略。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
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
