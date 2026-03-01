"""反馈学习服务（首版实现最小闭环）。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from steward.domain.enums import FeedbackType
from steward.infra.db.models import FeedbackEvent, UserPreferenceProfile


class FeedbackLearningService:
    """处理用户反馈并更新偏好画像。"""

    async def record_feedback(
        self,
        session: AsyncSession,
        *,
        plan_id: str,
        feedback_type: FeedbackType,
        note: str | None = None,
    ) -> FeedbackEvent:
        """写入反馈事件。"""
        feedback = FeedbackEvent(plan_id=plan_id, feedback_type=feedback_type.value, note=note)
        session.add(feedback)
        await session.flush()
        await self._apply_default_profile(session)
        return feedback

    async def _apply_default_profile(self, session: AsyncSession) -> None:
        """确保默认用户画像存在。"""
        profile = await session.get(UserPreferenceProfile, "default")
        if profile is None:
            profile = UserPreferenceProfile(user_id="default")
            session.add(profile)
            await session.flush()
