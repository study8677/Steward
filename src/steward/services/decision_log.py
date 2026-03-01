"""决策日志写入服务。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from steward.domain.enums import DecisionOutcome, GateResult
from steward.infra.db.models import DecisionLog


class DecisionLogService:
    """记录门禁判定与执行结果。"""

    async def append(
        self,
        session: AsyncSession,
        *,
        plan_id: str,
        gate_result: GateResult,
        state_from: str,
        state_to: str,
        reason: str,
        outcome: DecisionOutcome,
    ) -> DecisionLog:
        """写入一条审计记录。"""
        log = DecisionLog(
            plan_id=plan_id,
            gate_result=gate_result.value,
            state_from=state_from,
            state_to=state_to,
            reason=reason,
            outcome=outcome.value,
        )
        session.add(log)
        await session.flush()
        return log
