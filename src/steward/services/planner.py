"""Planner 服务：从事件生成可执行计划。"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from steward.domain.enums import PlanState, PriorityLevel, Reversibility, RiskLevel
from steward.infra.db.models import (
    ActionPlan,
    ContextEvent,
    ContextSpace,
    PlanEffect,
    TaskCandidate,
)
from steward.planning.execution_policy import ExecutionPolicy
from steward.planning.plan_compiler import PlanCompiler
from steward.services.model_gateway import ModelGateway


class PlannerService:
    """将事件转换为可执行计划。"""

    _github_ref = re.compile(
        r"(?:github:(?:issue|pr):)?(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)#(?P<number>\d+)",
        re.IGNORECASE,
    )

    def __init__(
        self,
        plan_compiler: PlanCompiler | None = None,
        execution_policy: ExecutionPolicy | None = None,
        model_gateway: ModelGateway | None = None,
        workspace_dir: str | Path | None = None,
    ) -> None:
        self._plan_compiler = plan_compiler or PlanCompiler()
        self._execution_policy = execution_policy or ExecutionPolicy()
        self._model_gateway = model_gateway
        self._workspace_dir = Path(workspace_dir).expanduser() if workspace_dir else Path.cwd()

    async def build_plan(
        self,
        session: AsyncSession,
        event: ContextEvent,
        space: ContextSpace,
    ) -> tuple[TaskCandidate, ActionPlan]:
        """创建任务与计划。"""
        intent = self._infer_intent(event.summary)
        risk_level = self._infer_risk(event.summary)
        priority = self._infer_priority(event.summary, risk_level)
        reversibility = (
            Reversibility.IRREVERSIBLE if risk_level == RiskLevel.HIGH else Reversibility.REVERSIBLE
        )
        raw_steps = await self._build_steps(event, intent)
        requires_confirmation = reversibility == Reversibility.IRREVERSIBLE
        wait_condition: str | None = None
        resume_trigger: str | None = None

        if self._model_gateway is not None:
            planned = await self._model_gateway.plan_event_execution(
                event_summary=event.summary,
                source=event.source,
                source_ref=event.source_ref,
                entities=event.entity_set,
                default_intent=intent,
                default_risk_level=risk_level.value,
                default_priority=priority.value,
                default_reversibility=reversibility.value,
                default_requires_confirmation=requires_confirmation,
                candidate_steps=raw_steps,
            )
            intent = str(planned.get("intent", intent)).strip()[:128] or intent
            risk_level = self._coerce_risk(str(planned.get("risk_level", risk_level.value)))
            priority = self._coerce_priority(str(planned.get("priority", priority.value)))
            reversibility = self._coerce_reversibility(
                str(planned.get("reversibility", reversibility.value))
            )
            requires_confirmation = bool(
                planned.get("requires_confirmation", requires_confirmation)
            )
            if risk_level == RiskLevel.HIGH or reversibility == Reversibility.IRREVERSIBLE:
                requires_confirmation = True
            steps_from_model = planned.get("steps", raw_steps)
            raw_steps = steps_from_model if isinstance(steps_from_model, list) else raw_steps
            wait_condition_raw = planned.get("wait_condition")
            if isinstance(wait_condition_raw, str) and wait_condition_raw.strip():
                wait_condition = wait_condition_raw.strip()[:255]
            resume_trigger_raw = planned.get("resume_trigger")
            if isinstance(resume_trigger_raw, str) and resume_trigger_raw.strip():
                resume_trigger = resume_trigger_raw.strip()[:255]

        task = TaskCandidate(
            derived_from=space.space_id,
            intent=intent,
            priority=priority.value,
            risk_level=risk_level.value,
            impact_score=60 if risk_level == RiskLevel.HIGH else 30,
            urgency_score=70 if "today" in event.summary.lower() else 40,
        )
        session.add(task)
        await session.flush()

        compiled_plan, compile_error = self._plan_compiler.compile(
            intent=intent,
            source=event.source,
            source_ref=event.source_ref,
            risk_level=risk_level.value,
            reversibility=reversibility.value,
            requires_confirmation=requires_confirmation,
            raw_steps=raw_steps,
        )

        compile_errors: list[str] = []
        steps: list[dict[str, object]] = []
        if compiled_plan is None:
            requires_confirmation = True
            compile_errors.append(compile_error.reason if compile_error else "compile_failed")
            if compile_error is not None:
                compile_errors.extend(compile_error.details)
        else:
            steps = [step.model_dump() for step in compiled_plan.steps]
            violations = self._execution_policy.evaluate(compiled_plan)
            if violations:
                requires_confirmation = True
                compile_errors.extend(f"{item.code}:{item.message}" for item in violations)

        if wait_condition is None and "等待" in event.summary:
            wait_condition = "await_external_reply"
        if resume_trigger is None and wait_condition:
            resume_trigger = event.match_key

        plan = ActionPlan(
            task_id=task.task_id,
            state=PlanState.PLANNED.value,
            steps=steps,
            rollback=[],
            reversibility=reversibility.value,
            requires_confirmation=requires_confirmation,
            wait_condition=wait_condition,
            resume_trigger=resume_trigger,
            wait_timeout_at=(datetime.now(UTC) + timedelta(hours=24)) if wait_condition else None,
            on_wait_timeout="remind_then_escalate" if wait_condition else None,
            execution_status="pending_confirmation" if requires_confirmation else "idle",
            last_error="; ".join(compile_errors)[:1000] if compile_errors else None,
        )
        session.add(plan)
        await session.flush()

        resource_key = self._infer_resource_key(event)
        if resource_key:
            effect = PlanEffect(
                plan_id=plan.plan_id,
                resource_key=resource_key,
                operation=f"intent:{intent}",
                reversibility=reversibility.value,
            )
            session.add(effect)

        await session.flush()
        return task, plan

    def _infer_intent(self, summary: str) -> str:
        """基于摘要推断意图。"""
        content = summary.lower()
        if "review" in content or "审核" in summary:
            return "review"
        if "回复" in summary or "reply" in content:
            return "reply"
        if "安排" in summary or "schedule" in content:
            return "arrange"
        return "follow_up"

    def _infer_risk(self, summary: str) -> RiskLevel:
        """基于关键词推断风险级别。"""
        high_keywords = ["不可逆", "外部承诺", "付款", "合同", "delete", "payment"]
        medium_keywords = ["发送", "发布", "merge", "升级"]
        if any(keyword in summary for keyword in high_keywords):
            return RiskLevel.HIGH
        if any(keyword in summary for keyword in medium_keywords):
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _infer_priority(self, summary: str, risk_level: RiskLevel) -> PriorityLevel:
        """推断优先级。"""
        if "P0" in summary or "紧急" in summary:
            return PriorityLevel.P0
        if risk_level == RiskLevel.HIGH:
            return PriorityLevel.P1
        return PriorityLevel.P2

    async def _build_steps(self, event: ContextEvent, intent: str) -> list[dict[str, object]]:
        """构建执行步骤。

        重构后：不再按 source 硬编码每种 connector 的动作，
        而是生成一个统一的 agent_execute 步骤，由 ExecutionAgent 自主决策。
        仅保留必要的安全检查（如自回复检测）。
        """
        # 安全检查：跳过自己生成的 GitHub 评论，防止回复死循环
        if event.source == "github" and await self._is_self_generated_github_comment(event):
            return [
                {
                    "connector": "manual",
                    "action_type": "record_note",
                    "payload": {
                        "summary": "Skip self-generated GitHub comment event to avoid reply loop.",
                        "intent": "observe",
                    },
                }
            ]

        # 核心：生成一个 agent_execute 步骤，委托给 ExecutionAgent 自主完成
        return [
            {
                "connector": "agent",
                "action_type": "agent_execute",
                "payload": {
                    "intent": intent,
                    "event_summary": event.summary,
                    "source": event.source,
                    "source_ref": event.source_ref,
                    "entities": event.entity_set,
                },
            }
        ]

    async def _build_github_issue_reply(
        self,
        *,
        event: ContextEvent,
        intent: str,
        owner: str,
        repo: str,
        issue_number: int,
    ) -> str:
        if self._model_gateway is None:
            return self._fallback_github_reply(event.summary)
        repo_context = self._model_gateway.build_local_repo_context(
            workspace_dir=self._workspace_dir,
            file_limit=3,
        )
        reply = await self._model_gateway.compose_github_issue_reply(
            owner=owner,
            repo=repo,
            issue_number=issue_number,
            event_summary=event.summary,
            intent=intent,
            repo_context=repo_context,
        )
        return reply or self._fallback_github_reply(event.summary)

    def _fallback_github_reply(self, summary: str) -> str:
        compact = summary.strip()[:160] or "issue update"
        return (
            f"收到你的反馈：{compact}。\n"
            "当前仓库已具备事件接入、规划、异步执行与执行日志能力，后续会基于仓库上下文继续跟进。\n"
            "建议补充复现步骤和期望结果，便于更精准处理。\n\n"
            f"We received your feedback: {compact}.\n"
            "The repository already includes event ingest, planning, async execution, and execution logs. We will continue based on repository context.\n"
            "Please share repro steps and expected behavior for a more precise follow-up."
        )

    async def _is_self_generated_github_comment(self, event: ContextEvent) -> bool:
        if event.source != "github":
            return False
        summary = event.summary.lower()
        if "steward 自动跟进" in summary or "steward auto follow-up" in summary:
            return True
        entities = {item.strip().lower() for item in event.entity_set if isinstance(item, str)}
        if "issue_comment" not in entities:
            return False
        if self._model_gateway is None:
            return False
        return await self._model_gateway.is_github_actor_self(event.actor)

    def _parse_github_ref(self, source_ref: str) -> tuple[str, str, int] | None:
        match = self._github_ref.search(source_ref)
        if match is None:
            return None
        return match.group("owner"), match.group("repo"), int(match.group("number"))

    def _infer_resource_key(self, event: ContextEvent) -> str | None:
        """从事件中推断资源键。"""
        if event.match_key:
            return event.match_key
        if event.source_ref:
            return f"{event.source}:{event.source_ref}"
        return None

    def _coerce_risk(self, value: str) -> RiskLevel:
        normalized = value.strip().lower()
        if normalized == "high":
            return RiskLevel.HIGH
        if normalized == "medium":
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _coerce_priority(self, value: str) -> PriorityLevel:
        normalized = value.strip().upper()
        if normalized == PriorityLevel.P0.value:
            return PriorityLevel.P0
        if normalized == PriorityLevel.P1.value:
            return PriorityLevel.P1
        return PriorityLevel.P2

    def _coerce_reversibility(self, value: str) -> Reversibility:
        normalized = value.strip().lower()
        if normalized == Reversibility.IRREVERSIBLE.value:
            return Reversibility.IRREVERSIBLE
        return Reversibility.REVERSIBLE
