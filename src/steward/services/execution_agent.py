"""Execution Agent：基于 LiteLLM + OpenAI Tool Calling 的自主执行引擎。

设计原则（第一性原理）：
1. 完全基于 LiteLLM 的 acompletion()，通过 OpenAI 格式的 Tool Calling
   与任何大模型（DeepSeek / Claude / GPT 等）进行交互。
2. 核心循环：推断 → 调用工具 → 获取结果 → 再推断 → 直到任务完成。
3. 安全底线不可绕过：最大循环次数 (max_turns) 防止死循环。
4. 工具由 ToolRegistry 统一提供，支持 MCP / Skill / 内置能力。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog

from steward.core.config import Settings
from steward.services.tool_registry import ToolRegistry

logger = structlog.get_logger("execution_agent")

# 默认最大推理轮次，防止死循环
DEFAULT_MAX_TURNS = 15


@dataclass(slots=True)
class ExecutionResult:
    """Agent 执行结果。"""

    success: bool
    summary: str
    detail: str
    turns_used: int


class ExecutionAgent:
    """基于 LiteLLM 的 Steward 自主执行引擎。

    工作流程：
    1. 接收任务意图 (intent) + 上下文。
    2. 将所有可用工具（OpenAI 格式）+ 系统提示词 + 用户 prompt 发给大模型。
    3. 如果大模型返回 tool_calls，执行工具并把结果反馈给大模型。
    4. 循环直到大模型返回纯文本（不再调用工具）或达到 max_turns。
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        settings: Settings,
        *,
        max_turns: int = DEFAULT_MAX_TURNS,
        system_prompt: str = "",
    ) -> None:
        self._tool_registry = tool_registry
        self._settings = settings
        self._max_turns = max_turns
        self._system_prompt = system_prompt or self._default_system_prompt()

    async def execute(
        self,
        *,
        intent: str,
        event_summary: str,
        plan_id: str = "",
        extra_context: str = "",
    ) -> ExecutionResult:
        """执行一个任务。

        Args:
            intent: 任务核心意图（如 "reply", "review", "fix_ci"）。
            event_summary: 触发事件的自然语言摘要。
            plan_id: 关联的 ActionPlan ID。
            extra_context: 额外上下文信息。

        Returns:
            ExecutionResult: 执行结果。
        """
        import litellm

        tools = self._tool_registry.get_tools_schema()
        user_prompt = self._build_prompt(
            intent=intent,
            event_summary=event_summary,
            extra_context=extra_context,
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        model = self._settings.model_default
        api_base = self._settings.model_base_url
        api_key = self._settings.model_api_key

        logger.info(
            "execution_agent_start",
            plan_id=plan_id[:8] if plan_id else "N/A",
            intent=intent,
            model=model,
            api_base=api_base[:40] if api_base else "N/A",
            tools_count=len(tools),
            max_turns=self._max_turns,
        )

        turns_used = 0
        final_text = ""

        try:
            for turn in range(self._max_turns):
                turns_used = turn + 1

                # 调用大模型
                response = await litellm.acompletion(
                    model=f"openai/{model}",
                    messages=messages,
                    tools=tools if tools else None,
                    tool_choice="auto" if tools else None,
                    api_base=api_base,
                    api_key=api_key,
                    temperature=0.1,
                    timeout=self._settings.model_timeout_ms / 1000,
                )

                choice = response.choices[0]
                assistant_msg = choice.message

                # 把 assistant 的消息加入上下文
                messages.append(assistant_msg.model_dump())

                # 检查是否有 tool_calls
                tool_calls = getattr(assistant_msg, "tool_calls", None)

                if not tool_calls:
                    # 没有工具调用 = 任务完成
                    final_text = str(getattr(assistant_msg, "content", "") or "")
                    break

                # 执行每个工具调用
                for tc in tool_calls:
                    func_name = tc.function.name
                    try:
                        func_args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        func_args = {}

                    logger.info(
                        "tool_call",
                        plan_id=plan_id[:8] if plan_id else "N/A",
                        turn=turn,
                        tool=func_name,
                        args=str(func_args)[:100],
                    )

                    result = await self._tool_registry.execute_tool(func_name, func_args)

                    # 将工具结果作为 tool message 反馈给大模型
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(result, ensure_ascii=False, default=str)[:2000],
                        }
                    )
            else:
                # 达到最大轮次
                final_text = f"已达到最大执行轮次 ({self._max_turns})，任务可能未完全完成。"

            logger.info(
                "execution_agent_completed",
                plan_id=plan_id[:8] if plan_id else "N/A",
                turns_used=turns_used,
                output_length=len(final_text),
            )

            return ExecutionResult(
                success=True,
                summary=self._extract_summary(final_text),
                detail=final_text[:2000],
                turns_used=turns_used,
            )

        except Exception as exc:
            logger.error(
                "execution_agent_failed",
                plan_id=plan_id[:8] if plan_id else "N/A",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return ExecutionResult(
                success=False,
                summary=f"执行失败: {type(exc).__name__}: {str(exc)[:200]}",
                detail=str(exc)[:2000],
                turns_used=turns_used,
            )

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        *,
        intent: str,
        event_summary: str,
        extra_context: str,
    ) -> str:
        """构建发送给大模型的用户提示词。"""
        parts = [
            f"## 任务目标\n意图 (intent): {intent}",
            f"\n## 触发事件\n{event_summary}",
        ]
        if extra_context:
            parts.append(f"\n## 额外上下文\n{extra_context}")

        parts.append(
            "\n## 执行要求\n"
            "1. 请利用你手头的工具，采取一切必要措施完成上述任务。\n"
            "2. 如果需要了解项目信息，请先使用 get_repo_context 工具。\n"
            "3. 完成后请总结你做了什么、结果如何。\n"
            "4. 如果遇到无法解决的问题，请明确说明原因。"
        )
        return "\n".join(parts)

    def _extract_summary(self, full_output: str, max_len: int = 200) -> str:
        """从完整输出中提取简短摘要。"""
        if not full_output:
            return "任务已完成。"
        lines = [line.strip() for line in full_output.split("\n") if line.strip()]
        if not lines:
            return "任务已完成。"
        summary = " ".join(lines[-3:])
        if len(summary) > max_len:
            summary = summary[:max_len] + "…"
        return summary

    @staticmethod
    def _default_system_prompt() -> str:
        """默认的系统提示词。"""
        return (
            "你是 Steward——一个无感常驻、主动推进事务的智能管家 Agent。\n"
            "你的职责是利用手头的工具高效完成分配给你的任务。\n"
            "\n"
            "行为准则：\n"
            "1. 先理解任务目标，再规划执行步骤，最后逐一执行。\n"
            "2. 遇到不确定的信息，先用工具获取上下文再做判断。\n"
            "3. 执行完毕后，用简洁的中文总结你做了什么以及结果。\n"
            "4. 如果某个步骤失败，先尝试替代方案，实在不行再上报。\n"
            "5. 保持专业、简洁，不输出冗余信息。"
        )
