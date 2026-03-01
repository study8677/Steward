"""Dashboard 汇总服务。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from steward.connectors.registry import ConnectorRegistry
from steward.domain.enums import PlanState
from steward.infra.db.models import (
    ActionPlan,
    ConflictCase,
    ContextEvent,
    DecisionLog,
    TaskCandidate,
)
from steward.services.model_gateway import ModelGateway


class DashboardService:
    """生成运行总览、待确认项与连接器状态。"""

    def __init__(self, connectors: ConnectorRegistry, model_gateway: ModelGateway) -> None:
        self._connectors = connectors
        self._model_gateway = model_gateway
        # 用 plan_id + updated_at 作为缓存键，避免每次刷新重复调用模型生成摘要。
        self._pending_summary_cache: dict[str, str] = {}

    async def overview(self, session: AsyncSession) -> dict[str, object]:
        """返回 dashboard 总览数据。"""
        total_plans = int(
            (await session.execute(select(func.count()).select_from(ActionPlan))).scalar_one()
        )
        total_decisions = int(
            (await session.execute(select(func.count()).select_from(DecisionLog))).scalar_one()
        )

        waiting_count = await self._count_by_state(session, PlanState.WAITING.value)
        running_count = await self._count_by_state(session, PlanState.RUNNING.value)
        conflicted_count = await self._count_by_state(session, PlanState.CONFLICTED.value)

        return {
            "plans_total": total_plans,
            "decisions_total": total_decisions,
            "plans_waiting": waiting_count,
            "plans_running": running_count,
            "plans_conflicted": conflicted_count,
        }

    async def snapshot(self, session: AsyncSession) -> dict[str, Any]:
        """返回前端消费的一体化快照。"""
        overview = await self.overview(session)
        pending = await self.pending_confirmations(session)
        conflicts = await self.open_conflicts(session)
        connector_health = await self.connector_health()
        recent_logs = await self.recent_runtime_logs(session)
        return {
            "overview": overview,
            "pending_confirmations": pending,
            "open_conflicts": conflicts,
            "connector_health": connector_health,
            "recent_logs": recent_logs,
        }

    async def pending_confirmations(self, session: AsyncSession) -> list[dict[str, Any]]:
        """返回待人工确认的计划。"""
        stmt = (
            select(ActionPlan, TaskCandidate)
            .join(TaskCandidate, ActionPlan.task_id == TaskCandidate.task_id)
            .where(
                ActionPlan.requires_confirmation.is_(True),
                ActionPlan.state.in_(
                    [
                        PlanState.PLANNED.value,
                        PlanState.GATED.value,
                        PlanState.CONFLICTED.value,
                    ]
                ),
            )
            .order_by(ActionPlan.updated_at.desc())
            .limit(20)
        )
        rows = (await session.execute(stmt)).all()
        items: list[dict[str, Any]] = []
        for plan, task in rows:
            human_summary = await self._get_pending_plan_human_summary(
                plan_id=plan.plan_id,
                updated_at=plan.updated_at,
                intent=task.intent,
                risk_level=task.risk_level,
                priority=task.priority,
                reversibility=plan.reversibility,
                steps=plan.steps,
            )
            items.append(
                {
                    "plan_id": plan.plan_id,
                    "state": plan.state,
                    "reversibility": plan.reversibility,
                    "task_id": task.task_id,
                    "intent": task.intent,
                    "risk_level": task.risk_level,
                    "priority": task.priority,
                    "updated_at": plan.updated_at.isoformat(),
                    "human_summary": human_summary,
                }
            )
        return items

    async def open_conflicts(self, session: AsyncSession) -> list[dict[str, Any]]:
        """返回未关闭冲突列表。"""
        stmt = (
            select(ConflictCase)
            .where(ConflictCase.status == "open")
            .order_by(ConflictCase.created_at.desc())
            .limit(20)
        )
        conflicts = list((await session.execute(stmt)).scalars().all())
        return [
            {
                "conflict_id": item.conflict_id,
                "plan_a_id": item.plan_a_id,
                "plan_b_id": item.plan_b_id,
                "conflict_type": item.conflict_type,
                "resolution": item.resolution,
                "status": item.status,
            }
            for item in conflicts
        ]

    async def connector_health(self) -> list[dict[str, Any]]:
        """返回连接器健康视图。"""
        health_map = await self._connectors.health()
        return [
            {
                "name": name,
                "healthy": status.healthy,
                "code": status.code,
                "message": status.message,
            }
            for name, status in sorted(health_map.items())
        ]

    async def _count_by_state(self, session: AsyncSession, state: str) -> int:
        """统计指定状态计划数量。"""
        stmt = select(func.count()).select_from(ActionPlan).where(ActionPlan.state == state)
        return int((await session.execute(stmt)).scalar_one())

    # ---- 人类友好标签映射 ----

    _SOURCE_LABELS: dict[str, str] = {
        "manual": "手动输入",
        "github": "GitHub",
        "email": "邮件",
        "chat": "聊天消息",
        "calendar": "日历",
        "screen": "屏幕感知",
        "local": "本地环境",
        "custom": "自定义源",
    }

    _GATE_LABELS: dict[str, str] = {
        "auto": "自动执行",
        "brief": "进入简报",
        "confirm": "待用户确认",
        "blocked": "已阻断",
    }

    _TRANSITION_LABELS: dict[tuple[str, str], str] = {
        ("PLANNED", "GATED"): "🚧 门禁评估通过",
        ("GATED", "RUNNING"): "▶️ 开始执行",
        ("RUNNING", "SUCCEEDED"): "✅ 自动执行成功",
        ("RUNNING", "FAILED"): "❌ 执行失败",
        ("RUNNING", "ROLLED_BACK"): "↩️ 已回滚",
        ("RUNNING", "WAITING"): "⏳ 等待外部回复",
        ("WAITING", "GATED"): "⏰ 等待超时，重新评估",
        ("WAITING", "RUNNING"): "🔔 收到回复，继续执行",
        ("GATED", "CONFLICTED"): "⚠️ 检测到冲突",
        ("RUNNING", "CONFLICTED"): "⚠️ 执行中发现冲突",
        ("CONFLICTED", "GATED"): "🔄 冲突已处理，重新评估",
        ("NEW", "PLANNED"): "📋 已生成执行计划",
    }

    def _source_label(self, source: str) -> str:
        return self._SOURCE_LABELS.get(source, source)

    def _gate_label(self, gate_result: str) -> str:
        return self._GATE_LABELS.get(gate_result, gate_result)

    def _transition_label(self, state_from: str, state_to: str) -> str:
        return self._TRANSITION_LABELS.get(
            (state_from, state_to),
            f"{state_from} → {state_to}",
        )

    async def recent_runtime_logs(
        self, session: AsyncSession, limit: int = 30
    ) -> list[dict[str, str]]:
        """返回最近运行日志视图（事件 + 决策），对人类友好。"""
        event_stmt = select(ContextEvent).order_by(ContextEvent.created_at.desc()).limit(limit)
        decision_stmt = (
            select(DecisionLog, ActionPlan, TaskCandidate)
            .join(ActionPlan, DecisionLog.plan_id == ActionPlan.plan_id)
            .join(TaskCandidate, ActionPlan.task_id == TaskCandidate.task_id)
            .order_by(DecisionLog.created_at.desc())
            .limit(limit)
        )

        event_rows = list((await session.execute(event_stmt)).scalars().all())
        decision_rows = list((await session.execute(decision_stmt)).all())

        logs: list[dict[str, str]] = []

        for event in event_rows:
            source_label = self._source_label(event.source)
            logs.append(
                {
                    "timestamp": event.created_at.isoformat(),
                    "kind": "event",
                    "title": f"📨 收到事件 · {source_label}",
                    "detail": event.summary[:180] if event.summary else "(无摘要)",
                }
            )

        for decision, _plan, task in decision_rows:
            gate_label = self._gate_label(decision.gate_result)
            transition = self._transition_label(decision.state_from, decision.state_to)
            intent = task.intent if task else "unknown"
            short_id = decision.plan_id[:8]
            reason = decision.reason[:120] if decision.reason else ""

            logs.append(
                {
                    "timestamp": decision.created_at.isoformat(),
                    "kind": "decision",
                    "title": f"{transition} · {intent} ({gate_label})",
                    "detail": f"计划 {short_id}… | {reason}" if reason else f"计划 {short_id}…",
                }
            )

        logs.sort(key=lambda item: item["timestamp"], reverse=True)
        return logs[:limit]

    async def _get_pending_plan_human_summary(
        self,
        *,
        plan_id: str,
        updated_at: datetime,
        intent: str,
        risk_level: str,
        priority: str,
        reversibility: str,
        steps: list[dict[str, object]],
    ) -> str:
        """读取或生成待确认计划的人话摘要。"""
        cache_key = f"{plan_id}:{updated_at.isoformat()}"
        cached = self._pending_summary_cache.get(cache_key)
        if cached:
            return cached

        summary = await self._model_gateway.summarize_pending_plan(
            plan_id=plan_id,
            intent=intent,
            risk_level=risk_level,
            priority=priority,
            reversibility=reversibility,
            steps=steps,
        )
        self._pending_summary_cache[cache_key] = summary
        return summary
