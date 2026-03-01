"""定时简报服务。"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import Row, select
from sqlalchemy.ext.asyncio import AsyncSession

from steward.domain.enums import GateResult, PlanState
from steward.domain.schemas import BriefResponse, BriefSection
from steward.infra.db.models import ActionPlan, ConflictCase, DecisionLog, TaskCandidate
from steward.services.model_gateway import ModelGateway


class BriefingService:
    """聚合最近执行结果并生成 Markdown 简报。"""

    def __init__(self, model_gateway: ModelGateway) -> None:
        self._model_gateway = model_gateway

    async def generate_latest(
        self,
        session: AsyncSession,
        window_hours: int,
        *,
        content_level: str = "medium",
    ) -> BriefResponse:
        """生成最近窗口的简报。"""
        now = datetime.now(UTC)
        start = now - timedelta(hours=window_hours)
        level = self._normalize_content_level(content_level)
        limits = self._level_limits(level)

        auto_rows = await self._query_logs(session, start, GateResult.AUTO.value)
        confirm_rows = await self._query_logs(session, start, GateResult.CONFIRM.value)
        brief_rows = await self._query_logs(session, start, GateResult.BRIEF.value)

        waiting_stmt = select(ActionPlan).where(ActionPlan.state == PlanState.WAITING.value)
        waiting_items = list((await session.execute(waiting_stmt)).scalars().all())

        conflict_stmt = select(ConflictCase).where(ConflictCase.status == "open")
        conflict_items = list((await session.execute(conflict_stmt)).scalars().all())

        # 逐条生成总结（串行调用，避免触发 API 频率限制）
        auto_summaries = await self._summarize_rows(
            auto_rows,
            default_outcome="succeeded",
            max_items=limits["auto"],
            content_level=level,
        )

        # 需确认/需干预区总结
        confirm_brief_rows = list(confirm_rows) + list(brief_rows)
        confirm_summaries = await self._summarize_rows(
            confirm_brief_rows,
            default_outcome="pending",
            max_items=limits["confirm"],
            content_level=level,
        )
        waiting_lines = self._render_waiting_items(
            waiting_items,
            content_level=level,
            limit=limits["waiting"],
        )
        conflict_lines = self._render_conflict_items(
            conflict_items,
            content_level=level,
            limit=limits["conflict"],
        )
        capability_items = self._capability_advice_items(level)
        feedback_items = self._feedback_entry_items(level)

        sections = [
            BriefSection(
                title="已自动完成",
                items=[f"- {summary}" for summary in auto_summaries] if auto_summaries else ["无"],
            ),
            BriefSection(
                title="正在等待",
                items=waiting_lines if waiting_lines else ["无"],
            ),
            BriefSection(
                title="冲突与风险",
                items=conflict_lines if conflict_lines else ["无"],
            ),
            BriefSection(
                title="需要你确认 / 被阻断的任务",
                items=[f"- {summary}" for summary in confirm_summaries]
                if confirm_summaries
                else ["无"],
            ),
            BriefSection(
                title="能力安装建议",
                items=capability_items,
            ),
            BriefSection(
                title="个性化反馈入口",
                items=feedback_items,
            ),
        ]

        markdown = self._to_markdown(now, start, sections, content_level=level)
        return BriefResponse(markdown=markdown, sections=sections)

    async def _summarize_rows(
        self,
        rows: Sequence[Row],
        *,
        default_outcome: str,
        max_items: int,
        content_level: str,
    ) -> list[str]:
        """逐条调用大模型生成日志总结，按 plan_id 去重并按上限截断。"""
        seen_plan_ids: set[str] = set()
        summaries: list[str] = []

        for row in rows:
            plan_id = row.DecisionLog.plan_id
            if plan_id in seen_plan_ids:
                continue
            seen_plan_ids.add(plan_id)

            # 按内容层级控制条目数，避免简报过长。
            if len(summaries) >= max_items:
                break

            summary = await self._model_gateway.summarize_executed_plan(
                plan_id=plan_id,
                intent=row.TaskCandidate.intent if row.TaskCandidate else "未知任务",
                steps=row.ActionPlan.steps if row.ActionPlan else [],
                outcome=row.DecisionLog.outcome or default_outcome,
                reason=row.DecisionLog.reason or "",
                content_level=content_level,
            )
            summaries.append(summary)
            # 串行请求之间加间隔，避免触发 API 频率限制。
            if self._model_gateway.is_model_configured():
                await asyncio.sleep(1.0)

        return summaries

    async def _query_logs(
        self,
        session: AsyncSession,
        start: datetime,
        gate_result: str,
    ) -> Sequence[Row]:
        """按 gate_result 联表查询日志及其对应的计划和任务。"""
        stmt = (
            select(DecisionLog, ActionPlan, TaskCandidate)
            .join(ActionPlan, DecisionLog.plan_id == ActionPlan.plan_id, isouter=True)
            .join(TaskCandidate, ActionPlan.task_id == TaskCandidate.task_id, isouter=True)
            .where(DecisionLog.created_at >= start, DecisionLog.gate_result == gate_result)
            .order_by(DecisionLog.created_at.desc())
        )
        return (await session.execute(stmt)).all()

    def _to_markdown(
        self,
        now: datetime,
        start: datetime,
        sections: list[BriefSection],
        *,
        content_level: str,
    ) -> str:
        """将分区转成 Markdown。"""
        lines = [
            f"Steward Brief | {now.isoformat()}",
            f"周期：{start.isoformat()} - {now.isoformat()}",
            f"内容级别：{content_level}",
            "",
        ]
        for index, section in enumerate(sections, start=1):
            lines.append(f"{index}) {section.title}")
            for item in section.items:
                lines.append(item)
            lines.append("")
        return "\n".join(lines)

    def _normalize_content_level(self, content_level: str) -> str:
        """规范化内容层级。"""
        level = content_level.strip().lower()
        if level not in {"simple", "medium", "rich"}:
            return "medium"
        return level

    def _level_limits(self, content_level: str) -> dict[str, int]:
        """按层级返回各分区条目上限。"""
        if content_level == "simple":
            return {"auto": 3, "confirm": 3, "waiting": 3, "conflict": 3}
        if content_level == "rich":
            return {"auto": 8, "confirm": 8, "waiting": 8, "conflict": 8}
        return {"auto": 5, "confirm": 5, "waiting": 5, "conflict": 5}

    def _render_waiting_items(
        self,
        waiting_items: list[ActionPlan],
        *,
        content_level: str,
        limit: int,
    ) -> list[str]:
        """渲染等待区内容。"""
        if not waiting_items:
            return []
        rendered: list[str] = []
        for plan in waiting_items[:limit]:
            wait_condition = plan.wait_condition or "await_external_reply"
            if content_level == "simple":
                rendered.append(f"- Plan {plan.plan_id}: 等待 {wait_condition}")
                continue

            if content_level == "rich":
                wait_timeout = plan.wait_timeout_at.isoformat() if plan.wait_timeout_at else "-"
                rendered.append(
                    f"- Plan {plan.plan_id}: wait={wait_condition}, resume={plan.resume_trigger or '-'}, timeout={wait_timeout}"
                )
                continue

            rendered.append(f"- Plan {plan.plan_id}: wait_condition={wait_condition}")

        if len(waiting_items) > limit:
            rendered.append(f"- 另有 {len(waiting_items) - limit} 条等待项未展开")
        return rendered

    def _render_conflict_items(
        self,
        conflict_items: list[ConflictCase],
        *,
        content_level: str,
        limit: int,
    ) -> list[str]:
        """渲染冲突区内容。"""
        if not conflict_items:
            return []
        rendered: list[str] = []
        for item in conflict_items[:limit]:
            if content_level == "simple":
                rendered.append(
                    f"- Conflict {item.conflict_id}: {item.conflict_type}, action={item.resolution}"
                )
                continue

            if content_level == "rich":
                rendered.append(
                    f"- Conflict {item.conflict_id}: type={item.conflict_type}, "
                    f"plan_a={item.plan_a_id}, plan_b={item.plan_b_id}, "
                    f"resolution={item.resolution}, status={item.status}"
                )
                continue

            rendered.append(
                f"- Conflict {item.conflict_id}: {item.plan_a_id} vs {item.plan_b_id}, resolution={item.resolution}"
            )

        if len(conflict_items) > limit:
            rendered.append(f"- 另有 {len(conflict_items) - limit} 条冲突未展开")
        return rendered

    def _capability_advice_items(self, content_level: str) -> list[str]:
        """返回能力建议区内容。"""
        if content_level == "simple":
            return ["当前暂无安装建议。"]
        if content_level == "rich":
            return [
                "当前未发现新增能力缺口。",
                "若近期重复出现人工兜底动作，建议补充对应 Connector / MCP Skill。",
            ]
        return ["检测到能力缺口时会在此显示安装建议（当前暂无）。"]

    def _feedback_entry_items(self, content_level: str) -> list[str]:
        """返回反馈入口文案。"""
        if content_level == "rich":
            return [
                "可反馈：太打扰 / 太保守 / 刚好。",
                "建议附带具体 plan_id，可加速个性化策略收敛。",
            ]
        return ["可反馈：太打扰 / 太保守 / 刚好。"]
