"""Recorder Agent — 专门负责自动沉淀记忆的 Agent。

当 Context Space 关闭、事件处理完成、或 Policy Gate 拒绝时，
RecorderAgent 自动提取有价值的信息，写入 ~/.steward_brain/ 对应目录。
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog

from steward.services.memory_manager import MemoryManager

logger = structlog.get_logger("recorder_agent")


class RecorderAgent:
    """自动记忆沉淀 Agent。

    设计原则：
    - 仅在关键时刻触发（空间关闭、门禁拒绝、重要事件处理完成）
    - 自动识别实体类型（项目/人物/通用事件）并写入对应目录
    - 用户无需干预，但可以随时手动修改结果
    """

    def __init__(self, memory_manager: MemoryManager) -> None:
        self._memory = memory_manager

    def on_space_closed(
        self,
        space_focus: str,
        entities: list[str],
        summary: str,
        actions_taken: list[str] | None = None,
    ) -> None:
        """Context Space 关闭时触发——沉淀事件摘要到日志和项目记忆。"""
        today = datetime.now(UTC).strftime("%Y%m%d")

        # 1) 写入当日日志
        action_text = ""
        if actions_taken:
            action_lines = "\n".join(f"- {a}" for a in actions_taken)
            action_text = f"\n\n**执行的动作:**\n{action_lines}"

        journal_content = (
            f"**Space 关闭**: {space_focus}\n\n"
            f"**实体**: {', '.join(entities)}\n\n"
            f"**摘要**: {summary}{action_text}"
        )
        self._memory.write_journal(journal_content, date=today)

        # 2) 自动检测是否与已知项目相关，写入项目记忆
        project_name = self._detect_project(space_focus, entities)
        if project_name:
            self._memory.write_project_memo(
                project=project_name,
                content=f"[Space 关闭] {summary}",
            )

        # 3) 自动检测人物实体，写入人物记忆
        people = self._detect_people(entities)
        for person in people:
            self._memory.write_person_memo(
                person=person,
                content=f"[来自 {space_focus}] {summary}",
            )

        logger.info(
            "recorder_space_closed",
            focus=space_focus,
            project=project_name,
            people_count=len(people),
        )

    def on_gate_rejected(
        self,
        plan_summary: str,
        risk_level: str,
        rejection_reason: str,
    ) -> None:
        """Policy Gate 拒绝执行时触发——提取规则偏好。"""
        rule_content = (
            f"**场景**: {plan_summary}\n\n"
            f"**风险等级**: {risk_level}\n\n"
            f"**拒绝原因**: {rejection_reason}\n\n"
            f"**生成时间**: {datetime.now(UTC).isoformat()}\n\n"
            f"*此规则由 RecorderAgent 在用户拒绝执行时自动生成。*"
        )
        self._memory.write_rule(
            name=f"rejected_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}",
            content=rule_content,
        )
        logger.info("recorder_gate_rejected", reason=rejection_reason)

    def on_important_event(
        self,
        source: str,
        summary: str,
        entities: list[str],
    ) -> None:
        """重要事件处理完成时触发——短条目写入日志。"""
        today = datetime.now(UTC).strftime("%Y%m%d")
        content = f"**{source}**: {summary} (实体: {', '.join(entities[:5])})"
        self._memory.write_journal(content, date=today)

    # ── 实体识别（轻量级关键词方式） ──────────────────

    @staticmethod
    def _detect_project(focus: str, entities: list[str]) -> str | None:
        """从 Space Focus 和实体中识别项目名称。"""
        # 简单策略：如果 entities 中包含 "github" 且有 owner/repo 格式的项目名
        for entity in entities:
            if "/" in entity and entity.count("/") == 1:
                parts = entity.split("/")
                if len(parts[0]) > 0 and len(parts[1]) > 0:
                    return entity  # 可能是 GitHub repo 名
        # 如果 focus 中包含"项目"等关键词，使用 focus 作为项目名
        project_keywords = ["项目", "project", "repo", "仓库"]
        for kw in project_keywords:
            if kw in focus.lower():
                return focus
        return None

    @staticmethod
    def _detect_people(entities: list[str]) -> list[str]:
        """从实体中识别人物。"""
        people: list[str] = []
        # 简单策略：排除已知的非人物实体
        non_people = {
            "github",
            "email",
            "calendar",
            "chat",
            "screen",
            "slack",
            "gmail",
            "google-calendar",
            "macos",
            "windows",
            "linux",
        }
        for entity in entities:
            # 跳过明显非人名的实体
            if entity.lower() in non_people:
                continue
            if "/" in entity or "#" in entity:
                continue
            if entity.startswith("http") or "@" in entity:
                continue
            # issue/pr 标签也不是人名
            if entity.startswith(("issue", "pr", "PR", "Issue")):
                continue
            # 如果实体看起来像人名（简短、不含特殊字符）
            if 1 < len(entity) < 30 and entity[0].isalpha():
                people.append(entity)

        return people[:5]  # 最多返回 5 个
