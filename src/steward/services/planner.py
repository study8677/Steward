"""Planner 服务：从事件生成可执行计划。"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

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
    ) -> None:
        self._plan_compiler = plan_compiler or PlanCompiler()
        self._execution_policy = execution_policy or ExecutionPolicy()

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

        reversibility = (
            Reversibility.IRREVERSIBLE if risk_level == RiskLevel.HIGH else Reversibility.REVERSIBLE
        )
        raw_steps = self._build_steps(event, intent)
        requires_confirmation = reversibility == Reversibility.IRREVERSIBLE

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

        wait_condition = "await_external_reply" if "等待" in event.summary else None
        resume_trigger = event.match_key if wait_condition else None

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

    def _build_steps(self, event: ContextEvent, intent: str) -> list[dict[str, object]]:
        """构建执行步骤。"""
        if event.source == "github":
            parsed = self._parse_github_ref(event.source_ref)
            if parsed is None:
                return []
            owner, repo, issue_number = parsed
            return [
                {
                    "connector": "github",
                    "action_type": "add_issue_comment",
                    "payload": {
                        "owner": owner,
                        "repo": repo,
                        "issue_number": issue_number,
                        "body": f"Steward 自动跟进：{intent}",
                    },
                }
            ]

        if event.source == "email":
            return [
                {
                    "connector": "email",
                    "action_type": "create_draft",
                    "payload": {"subject": f"Re: {event.summary[:60]}", "intent": intent},
                }
            ]

        if event.source == "chat":
            return [
                {
                    "connector": "chat",
                    "action_type": "reply_thread",
                    "payload": {"text": f"Steward 跟进建议：{intent}", "intent": intent},
                }
            ]

        if event.source == "calendar":
            return [
                {
                    "connector": "calendar",
                    "action_type": "update_event",
                    "payload": {"title": f"Steward follow-up: {intent}"},
                }
            ]

        if event.source == "screen":
            return [
                {
                    "connector": "screen",
                    "action_type": "collect_screen_signal",
                    "payload": {"summary": event.summary, "intent": intent},
                }
            ]

        if event.source in {"manual", "custom"}:
            return [
                {
                    "connector": "manual",
                    "action_type": "record_note",
                    "payload": {"summary": event.summary, "intent": intent},
                }
            ]

        return []

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
