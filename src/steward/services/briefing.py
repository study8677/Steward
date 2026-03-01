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

    async def generate_latest(self, session: AsyncSession, window_hours: int) -> BriefResponse:
        """生成最近窗口的简报。"""
        now = datetime.now(UTC)
        start = now - timedelta(hours=window_hours)

        auto_rows = await self._query_logs(session, start, GateResult.AUTO.value)
        confirm_rows = await self._query_logs(session, start, GateResult.CONFIRM.value)
        brief_rows = await self._query_logs(session, start, GateResult.BRIEF.value)

        waiting_stmt = select(ActionPlan).where(ActionPlan.state == PlanState.WAITING.value)
        waiting_items = list((await session.execute(waiting_stmt)).scalars().all())

        conflict_stmt = select(ConflictCase).where(ConflictCase.status == "open")
        conflict_items = list((await session.execute(conflict_stmt)).scalars().all())

        # 逐条生成总结（串行调用，避免触发 API 频率限制）
        auto_summaries = await self._summarize_rows(auto_rows, default_outcome="succeeded")

        # 需确认/需干预区总结
        confirm_brief_rows = list(confirm_rows) + list(brief_rows)
        confirm_summaries = await self._summarize_rows(
            confirm_brief_rows, default_outcome="pending"
        )

        sections = [
            BriefSection(
                title="已自动完成",
                items=[f"- {summary}" for summary in auto_summaries] if auto_summaries else ["无"],
            ),
            BriefSection(
                title="正在等待",
                items=[
                    f"- Plan {plan.plan_id}: wait_condition={plan.wait_condition}"
                    for plan in waiting_items
                ]
                if waiting_items
                else ["无"],
            ),
            BriefSection(
                title="冲突与风险",
                items=[
                    f"- Conflict {item.conflict_id}: {item.plan_a_id} vs {item.plan_b_id}, resolution={item.resolution}"
                    for item in conflict_items
                ]
                if conflict_items
                else ["无"],
            ),
            BriefSection(
                title="需要你确认 / 被阻断的任务",
                items=[f"- {summary}" for summary in confirm_summaries]
                if confirm_summaries
                else ["无"],
            ),
            BriefSection(
                title="能力安装建议",
                items=["检测到能力缺口时会在此显示安装建议（当前暂无）。"],
            ),
            BriefSection(
                title="个性化反馈入口",
                items=["可反馈：太打扰 / 太保守 / 刚好。"],
            ),
        ]

        markdown = self._to_markdown(now, start, sections)
        return BriefResponse(markdown=markdown, sections=sections)

    async def _summarize_rows(
        self,
        rows: Sequence[Row],
        *,
        default_outcome: str,
    ) -> list[str]:
        """逐条调用大模型生成每条日志的自然语言总结，按 plan_id 去重，最多 5 条。"""
        seen_plan_ids: set[str] = set()
        summaries: list[str] = []

        for row in rows:
            plan_id = row.DecisionLog.plan_id
            if plan_id in seen_plan_ids:
                continue
            seen_plan_ids.add(plan_id)

            # 最多生成 5 条总结，避免 API 请求过多
            if len(summaries) >= 5:
                break

            summary = await self._model_gateway.summarize_executed_plan(
                plan_id=plan_id,
                intent=row.TaskCandidate.intent if row.TaskCandidate else "未知任务",
                steps=row.ActionPlan.steps if row.ActionPlan else [],
                outcome=row.DecisionLog.outcome or default_outcome,
                reason=row.DecisionLog.reason or "",
            )
            summaries.append(summary)
            # 串行请求之间加间隔，避免触发 API 频率限制 (NVIDIA API 限制较严)
            await asyncio.sleep(3.0)

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

    def _to_markdown(self, now: datetime, start: datetime, sections: list[BriefSection]) -> str:
        """将分区转成 Markdown。"""
        lines = [
            f"Steward Brief | {now.isoformat()}",
            f"周期：{start.isoformat()} - {now.isoformat()}",
            "",
        ]
        for index, section in enumerate(sections, start=1):
            lines.append(f"{index}) {section.title}")
            for item in section.items:
                lines.append(item)
            lines.append("")
        return "\n".join(lines)
