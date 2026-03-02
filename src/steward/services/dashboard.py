"""Dashboard 汇总服务。"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
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
    ExecutionAttempt,
    ExecutionDispatch,
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
        # 用 decision_id + updated_at 作为缓存键，避免每次刷新重复生成日志摘要。
        self._runtime_decision_summary_cache: dict[str, str] = {}

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
        queue_depth = await self._queue_depth(session)

        return {
            "plans_total": total_plans,
            "decisions_total": total_decisions,
            "plans_waiting": waiting_count,
            "plans_running": running_count,
            "plans_conflicted": conflicted_count,
            "queue_depth": queue_depth,
        }

    async def snapshot(self, session: AsyncSession) -> dict[str, Any]:
        """返回前端消费的一体化快照。"""
        overview = await self.overview(session)
        pending = await self.pending_confirmations(session)
        conflicts = await self.open_conflicts(session)
        connector_health = await self.connector_health()
        recent_logs = await self.recent_runtime_logs(session)
        retries_24h = await self.retries_24h(session)
        failed_steps_24h = await self.failed_steps_24h(session)
        return {
            "overview": overview,
            "pending_confirmations": pending,
            "open_conflicts": conflicts,
            "connector_health": connector_health,
            "recent_logs": recent_logs,
            "queue_depth": overview.get("queue_depth", 0),
            "retries_24h": retries_24h,
            "failed_steps_24h": failed_steps_24h,
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
                    "execution_status": plan.execution_status,
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

    async def _queue_depth(self, session: AsyncSession) -> int:
        stmt = (
            select(func.count())
            .select_from(ExecutionDispatch)
            .where(ExecutionDispatch.status.in_(["queued", "running", "retrying"]))
        )
        return int((await session.execute(stmt)).scalar_one())

    async def retries_24h(self, session: AsyncSession) -> int:
        """Return total retries across dispatches in the last 24 hours."""
        since = datetime.now(UTC) - timedelta(hours=24)
        stmt = (
            select(func.coalesce(func.sum(ExecutionDispatch.retry_count), 0))
            .select_from(ExecutionDispatch)
            .where(ExecutionDispatch.created_at >= since)
        )
        return int((await session.execute(stmt)).scalar_one())

    async def failed_steps_24h(self, session: AsyncSession) -> int:
        """Return failed execution step attempts in the last 24 hours."""
        since = datetime.now(UTC) - timedelta(hours=24)
        stmt = (
            select(func.count())
            .select_from(ExecutionAttempt)
            .where(ExecutionAttempt.status == "failed", ExecutionAttempt.created_at >= since)
        )
        return int((await session.execute(stmt)).scalar_one())

    async def recent_executions(
        self, session: AsyncSession, limit: int = 30, lang: str = "zh"
    ) -> list[dict[str, Any]]:
        """返回最近执行结果，包含 dispatch 与每一步 attempt。"""
        effective_limit = max(1, min(limit, 200))
        locale = "en" if lang == "en" else "zh"
        dispatch_stmt = (
            select(ExecutionDispatch, ActionPlan, TaskCandidate)
            .join(ActionPlan, ExecutionDispatch.plan_id == ActionPlan.plan_id)
            .outerjoin(TaskCandidate, ActionPlan.task_id == TaskCandidate.task_id)
            .order_by(ExecutionDispatch.queued_at.desc(), ExecutionDispatch.created_at.desc())
            .limit(effective_limit)
        )
        dispatch_rows = list((await session.execute(dispatch_stmt)).all())

        dispatch_ids = [dispatch.dispatch_id for dispatch, _plan, _task in dispatch_rows]
        attempts_by_dispatch: dict[str, list[ExecutionAttempt]] = defaultdict(list)

        if dispatch_ids:
            attempt_stmt = (
                select(ExecutionAttempt)
                .where(ExecutionAttempt.dispatch_id.in_(dispatch_ids))
                .order_by(
                    ExecutionAttempt.dispatch_id.asc(),
                    ExecutionAttempt.step_index.asc(),
                    ExecutionAttempt.created_at.asc(),
                )
            )
            for attempt in (await session.execute(attempt_stmt)).scalars().all():
                attempts_by_dispatch[attempt.dispatch_id].append(attempt)

        items: list[dict[str, Any]] = []
        for dispatch, plan, task in dispatch_rows:
            plan_steps = plan.steps if isinstance(plan.steps, list) else []
            attempts = attempts_by_dispatch.get(dispatch.dispatch_id, [])
            planned_steps: list[dict[str, Any]] = []
            step_meta_by_index: dict[int, dict[str, Any]] = {}
            for idx, raw_step in enumerate(plan_steps):
                step = raw_step if isinstance(raw_step, dict) else {}
                connector = str(step.get("connector", "manual") or "manual").strip().lower()
                action_type = str(step.get("action_type", "unknown") or "unknown").strip().lower()
                payload_raw = step.get("payload", {})
                payload = payload_raw if isinstance(payload_raw, dict) else {}
                payload_summary = self._payload_summary(payload)
                step_label = self._step_label(
                    connector=connector,
                    action_type=action_type,
                    payload_summary=payload_summary,
                    lang=locale,
                )
                step_meta = {
                    "step_index": idx,
                    "connector": connector,
                    "connector_label": self._connector_label(connector, lang=locale),
                    "action_type": action_type,
                    "action_label": self._action_label(action_type, lang=locale),
                    "payload_summary": payload_summary,
                    "step_label": step_label,
                }
                planned_steps.append(step_meta)
                step_meta_by_index[idx] = step_meta

            attempts_payload = [
                {
                    "attempt_id": item.attempt_id,
                    "step_index": item.step_index,
                    "connector_instance_id": item.connector_instance_id,
                    "status": item.status,
                    "detail": item.detail,
                    "duration_ms": item.duration_ms,
                    "error_type": item.error_type,
                    "error_message": item.error_message,
                    "human_error": self._human_error(
                        error_type=item.error_type,
                        error_message=item.error_message,
                        lang=locale,
                    ),
                    "connector_label": (
                        step_meta_by_index.get(item.step_index, {}).get("connector_label")
                        or self._connector_label(item.connector_instance_id, lang=locale)
                    ),
                    "action_type": step_meta_by_index.get(item.step_index, {}).get(
                        "action_type", "unknown"
                    ),
                    "action_label": step_meta_by_index.get(item.step_index, {}).get(
                        "action_label", self._action_label("unknown", lang=locale)
                    ),
                    "step_label": step_meta_by_index.get(item.step_index, {}).get(
                        "step_label",
                        self._step_label(
                            connector=item.connector_instance_id,
                            action_type="unknown",
                            payload_summary="",
                            lang=locale,
                        ),
                    ),
                    "human_detail": self._human_attempt_detail(
                        detail=item.detail,
                        connector=item.connector_instance_id,
                        action_type=step_meta_by_index.get(item.step_index, {}).get(
                            "action_type", "unknown"
                        ),
                        payload_summary=step_meta_by_index.get(item.step_index, {}).get(
                            "payload_summary", ""
                        ),
                        lang=locale,
                    ),
                    "record_filename": self._extract_record_filename(item.detail),
                    "record_url": self._record_url(item.detail),
                    "retryable": item.retryable,
                    "created_at": self._to_iso(item.created_at),
                    "updated_at": self._to_iso(item.updated_at),
                }
                for item in attempts
            ]

            succeeded_steps = sum(1 for item in attempts if item.status == "succeeded")
            failed_steps = sum(1 for item in attempts if item.status == "failed")
            intent = task.intent if task is not None else "unknown"
            last_error_human = self._human_last_error(plan.last_error, lang=locale)

            items.append(
                {
                    "dispatch_id": dispatch.dispatch_id,
                    "plan_id": plan.plan_id,
                    "dispatch_id_short": self._short_id(dispatch.dispatch_id),
                    "plan_id_short": self._short_id(plan.plan_id),
                    "task_id": plan.task_id,
                    "intent": intent,
                    "intent_label": self._intent_label(intent, lang=locale),
                    "plan_state": plan.state,
                    "execution_status": plan.execution_status,
                    "dispatch_status": dispatch.status,
                    "dispatch_status_label": self._dispatch_status_label(
                        dispatch.status, lang=locale
                    ),
                    "trigger_reason": dispatch.trigger_reason,
                    "trigger_reason_label": self._trigger_reason_label(
                        dispatch.trigger_reason, lang=locale
                    ),
                    "retry_count": dispatch.retry_count,
                    "current_step": plan.current_step,
                    "total_steps": len(plan_steps),
                    "succeeded_steps": succeeded_steps,
                    "failed_steps": failed_steps,
                    "last_error": plan.last_error,
                    "last_error_human": last_error_human,
                    "human_summary": self._execution_summary(
                        status=dispatch.status,
                        total_steps=len(plan_steps),
                        succeeded_steps=succeeded_steps,
                        current_step=plan.current_step,
                        trigger_reason=dispatch.trigger_reason,
                        last_error=last_error_human,
                        lang=locale,
                    ),
                    "queued_at": self._to_iso(dispatch.queued_at),
                    "started_at": self._to_iso(dispatch.started_at),
                    "finished_at": self._to_iso(dispatch.finished_at),
                    "updated_at": self._to_iso(dispatch.updated_at),
                    "planned_steps": planned_steps,
                    "attempts": attempts_payload,
                }
            )

        return items

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
        ("GATED", "GATED"): "📥 已进入执行队列",
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

    _DISPATCH_STATUS_LABELS_ZH: dict[str, str] = {
        "queued": "已入队",
        "running": "执行中",
        "retrying": "重试中",
        "waiting": "等待外部输入",
        "succeeded": "执行成功",
        "failed": "执行失败",
    }

    _DISPATCH_STATUS_LABELS_EN: dict[str, str] = {
        "queued": "Queued",
        "running": "Running",
        "retrying": "Retrying",
        "waiting": "Waiting for input",
        "succeeded": "Succeeded",
        "failed": "Failed",
    }

    _TRIGGER_REASON_LABELS_ZH: dict[str, str] = {
        "low_risk_auto_execute": "低风险自动执行",
        "manual_confirmed": "人工确认后执行",
        "retry_after_failure": "失败后自动重试",
        "resume_from_waiting": "等待事件触发后恢复执行",
    }

    _TRIGGER_REASON_LABELS_EN: dict[str, str] = {
        "low_risk_auto_execute": "Low-risk auto execution",
        "manual_confirmed": "User confirmed then execute",
        "retry_after_failure": "Auto retry after failure",
        "resume_from_waiting": "Resume after external trigger",
    }

    _INTENT_LABELS_ZH: dict[str, str] = {
        "follow_up": "跟进事项",
        "reply": "回复消息",
        "summarize": "生成摘要",
        "schedule": "安排日程",
        "sync": "同步更新",
        "review": "执行检查",
    }

    _INTENT_LABELS_EN: dict[str, str] = {
        "follow_up": "Follow-up",
        "reply": "Reply",
        "summarize": "Summarize",
        "schedule": "Schedule",
        "sync": "Sync",
        "review": "Review",
    }

    _CONNECTOR_LABELS_ZH: dict[str, str] = {
        "manual": "手动输入",
        "github": "GitHub",
        "email": "邮件",
        "calendar": "日历",
        "chat": "聊天消息",
        "mcp": "MCP",
        "custom": "自定义连接器",
        "local": "本地环境",
    }

    _CONNECTOR_LABELS_EN: dict[str, str] = {
        "manual": "Manual input",
        "github": "GitHub",
        "email": "Email",
        "calendar": "Calendar",
        "chat": "Chat",
        "mcp": "MCP",
        "custom": "Custom connector",
        "local": "Local environment",
    }

    _ACTION_LABELS_ZH: dict[str, str] = {
        "record_note": "记录笔记",
        "reply_email": "回复邮件",
        "send_message": "发送消息",
        "create_issue": "创建事项",
        "update_issue": "更新事项",
        "schedule_event": "创建日程",
        "summarize": "生成摘要",
        "notify": "发送提醒",
        "unknown": "执行动作",
    }

    _ACTION_LABELS_EN: dict[str, str] = {
        "record_note": "Record note",
        "reply_email": "Reply email",
        "send_message": "Send message",
        "create_issue": "Create issue",
        "update_issue": "Update issue",
        "schedule_event": "Create calendar event",
        "summarize": "Generate summary",
        "notify": "Send notification",
        "unknown": "Run action",
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

    def _dispatch_status_label(self, status: str, *, lang: str = "zh") -> str:
        labels = (
            self._DISPATCH_STATUS_LABELS_EN if lang == "en" else self._DISPATCH_STATUS_LABELS_ZH
        )
        return labels.get(status, status)

    def _trigger_reason_label(self, reason: str, *, lang: str = "zh") -> str:
        labels = self._TRIGGER_REASON_LABELS_EN if lang == "en" else self._TRIGGER_REASON_LABELS_ZH
        return labels.get(reason, reason)

    def _intent_label(self, intent: str, *, lang: str = "zh") -> str:
        labels = self._INTENT_LABELS_EN if lang == "en" else self._INTENT_LABELS_ZH
        return labels.get(intent, intent)

    def _connector_label(self, connector: str, *, lang: str = "zh") -> str:
        labels = self._CONNECTOR_LABELS_EN if lang == "en" else self._CONNECTOR_LABELS_ZH
        return labels.get(connector, connector)

    def _action_label(self, action_type: str, *, lang: str = "zh") -> str:
        labels = self._ACTION_LABELS_EN if lang == "en" else self._ACTION_LABELS_ZH
        return labels.get(action_type, action_type)

    def _short_id(self, value: str) -> str:
        if len(value) <= 8:
            return value
        return value[:8]

    def _payload_summary(self, payload: dict[str, object]) -> str:
        for key in ["summary", "title", "subject", "message", "text", "target", "thread_id"]:
            raw = payload.get(key)
            if raw is None:
                continue
            text = str(raw).strip()
            if text:
                return text[:80]
        return ""

    def _step_label(
        self, connector: str, action_type: str, payload_summary: str, *, lang: str = "zh"
    ) -> str:
        connector_label = self._connector_label(connector, lang=lang)
        action_label = self._action_label(action_type, lang=lang)
        if payload_summary:
            if lang == "en":
                return f"{action_label} ({connector_label}): {payload_summary}"
            return f"{action_label}（{connector_label}）：{payload_summary}"
        if lang == "en":
            return f"{action_label} ({connector_label})"
        return f"{action_label}（{connector_label}）"

    def _human_error(
        self, error_type: str | None, error_message: str | None, *, lang: str = "zh"
    ) -> str:
        if error_message:
            return error_message[:180]
        if error_type == "connector_error":
            if lang == "en":
                return "Connector execution failed"
            return "连接器执行失败"
        if error_type:
            if lang == "en":
                return f"Execution exception: {error_type}"
            return f"执行异常：{error_type}"
        return ""

    def _human_attempt_detail(
        self,
        *,
        detail: str,
        connector: str,
        action_type: str,
        payload_summary: str,
        lang: str = "zh",
    ) -> str:
        stripped = detail.strip()
        if stripped.startswith("manual:record_note:"):
            filename = stripped.split(":", 2)[-1]
            if lang == "en":
                return f"Saved follow-up note to {filename}"
            return f"已写入跟进笔记到 {filename}"
        if stripped.startswith("manual:"):
            action = stripped.split(":", 2)[1] if ":" in stripped else "action"
            if lang == "en":
                return f"Manual action executed: {action}"
            return f"已执行手动动作：{action}"
        if stripped.startswith("exception:"):
            exception_name = stripped.split(":", 1)[-1]
            if lang == "en":
                return f"Execution exception: {exception_name}"
            return f"执行出现异常：{exception_name}"
        if stripped:
            return stripped[:180]
        step_label = self._step_label(
            connector=connector,
            action_type=action_type,
            payload_summary=payload_summary,
            lang=lang,
        )
        if lang == "en":
            return f"Step completed: {step_label}"
        return f"步骤完成：{step_label}"

    def _human_last_error(self, last_error: str | None, *, lang: str = "zh") -> str:
        if not last_error:
            return ""
        if last_error == "execution_engine_disabled":
            if lang == "en":
                return "Execution engine is disabled. Task was not executed."
            return "执行引擎未启用，任务未被执行。"
        if last_error.startswith("reflection_halt:"):
            reason = last_error.split(":", 1)[-1].strip()
            if lang == "en":
                return f"Reflection halted execution: {reason or 'no details'}"
            return f"执行反思阶段中止：{reason or '无详细说明'}"
        if last_error.startswith("reflection_replan_invalid:"):
            reason = last_error.split(":", 1)[-1].strip()
            if lang == "en":
                return f"Replanned steps are invalid: {reason or 'no details'}"
            return f"重规划步骤不合法：{reason or '无详细说明'}"

        matched = re.match(r"^step_(\d+)_(invalid|failed|exception)(?::(.*))?$", last_error)
        if matched:
            step_no = int(matched.group(1)) + 1
            err_type = matched.group(2)
            message = (matched.group(3) or "").strip()
            if err_type == "invalid":
                if lang == "en":
                    return f"Step {step_no} config is invalid."
                return f"第 {step_no} 步配置无效。"
            if err_type == "failed":
                if lang == "en":
                    suffix = f": {message}" if message else ""
                    return f"Step {step_no} failed{suffix}"
                suffix = f"：{message}" if message else ""
                return f"第 {step_no} 步执行失败{suffix}"
            if err_type == "exception":
                if lang == "en":
                    suffix = f": {message}" if message else ""
                    return f"Step {step_no} exception{suffix}"
                suffix = f"：{message}" if message else ""
                return f"第 {step_no} 步执行异常{suffix}"

        return last_error[:180]

    def _execution_summary(
        self,
        *,
        status: str,
        total_steps: int,
        succeeded_steps: int,
        current_step: int,
        trigger_reason: str,
        last_error: str,
        lang: str = "zh",
    ) -> str:
        status_normalized = status.strip().lower()
        if status_normalized == "succeeded":
            if lang == "en":
                return f"Execution completed: {succeeded_steps}/{total_steps} steps succeeded."
            return f"自动执行已完成，共 {total_steps} 步，成功 {succeeded_steps} 步。"
        if status_normalized == "failed":
            if last_error:
                if lang == "en":
                    return f"Execution failed: {last_error}"
                return f"自动执行失败：{last_error}"
            if lang == "en":
                return "Execution failed. Check step details."
            return "自动执行失败，请查看步骤明细。"
        if status_normalized == "running":
            step_no = min(max(current_step + 1, 1), max(total_steps, 1))
            if lang == "en":
                return f"Running step {step_no}/{max(total_steps, 1)}."
            return f"正在执行第 {step_no}/{max(total_steps, 1)} 步。"
        if status_normalized == "retrying":
            if lang == "en":
                return "A failed step is being retried."
            return "执行失败后正在自动重试。"
        if status_normalized == "waiting":
            if lang == "en":
                return "Execution paused and waiting for external trigger."
            return "执行已暂停，等待外部事件触发后继续。"
        if status_normalized == "queued":
            reason = self._trigger_reason_label(trigger_reason, lang=lang)
            if reason:
                if lang == "en":
                    return f"Task queued. Trigger: {reason}."
                return f"任务已入队，触发原因：{reason}。"
            if lang == "en":
                return "Task queued, waiting for worker execution."
            return "任务已入队，等待 Worker 执行。"
        if lang == "en":
            return f"Current status: {self._dispatch_status_label(status, lang=lang)}"
        return f"当前状态：{self._dispatch_status_label(status, lang=lang)}"

    def _extract_record_filename(self, detail: str | None) -> str | None:
        text = (detail or "").strip()
        if not text.startswith("manual:record_note:"):
            return None
        filename = text.split(":", 2)[-1].strip()
        if not filename.endswith(".md"):
            return None
        safe = filename.split("/")[-1].split("\\")[-1]
        return safe or None

    def _record_url(self, detail: str | None) -> str | None:
        filename = self._extract_record_filename(detail)
        if not filename:
            return None
        return f"/api/v1/dashboard/records/{filename}"

    def _to_iso(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.isoformat()

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

        pending_summaries: list[dict[str, object]] = []
        for decision, plan, task in decision_rows:
            cache_key = f"{decision.decision_id}:{decision.updated_at.isoformat()}"
            if cache_key in self._runtime_decision_summary_cache:
                continue
            pending_summaries.append(
                {
                    "cache_key": cache_key,
                    "decision_id": decision.decision_id,
                    "intent": task.intent if task else "unknown",
                    "gate_result": decision.gate_result,
                    "state_from": decision.state_from,
                    "state_to": decision.state_to,
                    "reason": decision.reason or "",
                    "outcome": decision.outcome or "",
                    "steps": plan.steps if isinstance(plan.steps, list) else [],
                }
            )

        if pending_summaries:
            generated = await self._model_gateway.summarize_runtime_decisions(
                decisions=[
                    {
                        "decision_id": str(item["decision_id"]),
                        "intent": str(item["intent"]),
                        "gate_result": str(item["gate_result"]),
                        "state_from": str(item["state_from"]),
                        "state_to": str(item["state_to"]),
                        "reason": str(item["reason"]),
                        "outcome": str(item["outcome"]),
                        "steps": item["steps"],
                    }
                    for item in pending_summaries
                ]
            )
            for item in pending_summaries:
                cache_key = str(item["cache_key"])
                decision_id = str(item["decision_id"])
                summary = generated.get(decision_id, "")
                self._runtime_decision_summary_cache[cache_key] = summary

        for decision, _plan, task in decision_rows:
            gate_label = self._gate_label(decision.gate_result)
            transition = self._transition_label(decision.state_from, decision.state_to)
            intent = task.intent if task else "unknown"
            cache_key = f"{decision.decision_id}:{decision.updated_at.isoformat()}"
            detail = self._runtime_decision_summary_cache.get(cache_key, "")

            logs.append(
                {
                    "timestamp": decision.created_at.isoformat(),
                    "kind": "decision",
                    "title": f"{transition} · {intent} ({gate_label})",
                    "detail": detail,
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
