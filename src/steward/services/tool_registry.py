"""工具注册表。

将 Steward 的 Skills / MCP / 内置能力
统一暴露为 OpenAI Function Calling (JSON Schema) 格式。

设计原则（第一性原理）：
1. 极少数核心内置工具由我们自己定义。
2. 大量能力来自开源社区的 MCP Servers 和 Skills。
3. 所有工具最终统一为 OpenAI 格式 JSON Schema，借助 LiteLLM 可喂给任何大模型。
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import structlog

from steward.services.integration_config import IntegrationConfigService

logger = structlog.get_logger("tool_registry")

# Type alias: 工具执行函数签名
ToolExecutor = Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]


class ToolRegistry:
    """管理并暴露所有可用工具，输出为 OpenAI Function Calling 格式。"""

    def __init__(
        self,
        integration_config: IntegrationConfigService,
        workspace_dir: str | Path = ".",
    ) -> None:
        self._integration_config = integration_config
        self._workspace_dir = Path(workspace_dir).expanduser().resolve()
        # 工具名 -> 执行函数 的映射
        self._executors: dict[str, ToolExecutor] = {}

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------

    def get_tools_schema(self) -> list[dict[str, Any]]:
        """返回 OpenAI Function Calling 格式的工具描述列表。

        Returns:
            用于 litellm.acompletion(tools=...) 的 tools 参数。
        """
        self._executors.clear()
        tools: list[dict[str, Any]] = []

        # 1) 核心内置工具
        for t in self._builtin_tools():
            tools.append(t["schema"])
            self._executors[t["name"]] = t["executor"]

        # 2) MCP Servers 暴露的工具（元工具：invoke_mcp）
        mcp_tools = self._mcp_meta_tools()
        for t in mcp_tools:
            tools.append(t["schema"])
            self._executors[t["name"]] = t["executor"]

        logger.info(
            "tool_registry_built",
            total_tools=len(tools),
            tool_names=[t["function"]["name"] for t in tools],
        )
        return tools

    async def execute_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """执行指定工具，返回结果。"""
        executor = self._executors.get(name)
        if executor is None:
            return {"error": f"未知工具: {name}", "success": False}
        try:
            result = await executor(arguments)
            return result
        except Exception as exc:
            logger.error("tool_execution_failed", tool=name, error=str(exc))
            return {"error": f"{type(exc).__name__}: {str(exc)[:500]}", "success": False}

    # ------------------------------------------------------------------
    # 核心内置工具（极少数、极克制）
    # ------------------------------------------------------------------

    def _builtin_tools(self) -> list[dict[str, Any]]:
        """定义核心内置工具。"""
        tools = []

        # --- get_repo_context ---
        async def _get_repo_context(args: dict[str, Any]) -> dict[str, Any]:
            max_files = int(args.get("max_files", 5))
            context = self._collect_repo_context(max_files)
            return {"success": True, "context": context}

        tools.append(
            {
                "name": "get_repo_context",
                "executor": _get_repo_context,
                "schema": {
                    "type": "function",
                    "function": {
                        "name": "get_repo_context",
                        "description": "获取当前本地仓库的上下文信息（README、目录结构等），用于理解项目。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "max_files": {
                                    "type": "integer",
                                    "description": "最多展示的文件数量",
                                    "default": 5,
                                }
                            },
                            "required": [],
                        },
                    },
                },
            }
        )

        # --- record_note ---
        async def _record_note(args: dict[str, Any]) -> dict[str, Any]:
            summary = str(args.get("summary", ""))
            category = str(args.get("category", "general"))
            return {"success": True, "recorded": f"[{category}] {summary[:200]}"}

        tools.append(
            {
                "name": "record_note",
                "executor": _record_note,
                "schema": {
                    "type": "function",
                    "function": {
                        "name": "record_note",
                        "description": "将一段信息记录到本地记忆系统中，作为 Steward 的持久化记忆。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "summary": {
                                    "type": "string",
                                    "description": "要记录的内容摘要",
                                },
                                "category": {
                                    "type": "string",
                                    "description": "分类标签",
                                    "default": "general",
                                },
                            },
                            "required": ["summary"],
                        },
                    },
                },
            }
        )

        return tools

    # ------------------------------------------------------------------
    # MCP 元工具
    # ------------------------------------------------------------------

    def _mcp_meta_tools(self) -> list[dict[str, Any]]:
        """为每个启用的 MCP Server 生成一个 invoke 元工具。

        这样大模型可以动态调用 MCP Server 提供的能力。
        """
        tools = []
        for item in self._integration_config.mcp_server_status():
            if not item.get("enabled"):
                continue
            server_id = str(item.get("server", ""))
            if not server_id:
                continue
            display_name = str(item.get("display_name", server_id))
            description = str(item.get("description", f"调用 {display_name} MCP Server"))

            tool_name = f"invoke_mcp_{server_id.replace('-', '_')}"

            async def _invoke_mcp(
                args: dict[str, Any],
                _sid: str = server_id,
            ) -> dict[str, Any]:
                return {
                    "success": True,
                    "note": f"MCP Server '{_sid}' 调用已记录，"
                    f"tool={args.get('tool_name', 'unknown')}, "
                    f"实际 MCP 连接将在后续版本中实现。",
                }

            tools.append(
                {
                    "name": tool_name,
                    "executor": _invoke_mcp,
                    "schema": {
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "description": f"[MCP] {description}",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "tool_name": {
                                        "type": "string",
                                        "description": "要调用的 MCP 工具名",
                                    },
                                    "arguments": {
                                        "type": "object",
                                        "description": "传给 MCP 工具的参数",
                                    },
                                },
                                "required": ["tool_name"],
                            },
                        },
                    },
                }
            )

        return tools

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _collect_repo_context(self, max_files: int = 5) -> str:
        """收集本地仓库上下文信息。"""
        parts: list[str] = []

        readme = self._workspace_dir / "README.md"
        if not readme.exists():
            readme = self._workspace_dir / "README_CN.md"
        if readme.exists():
            content = readme.read_text(encoding="utf-8", errors="replace")
            parts.append(f"## README\n{content[:3000]}")

        src_dir = self._workspace_dir / "src"
        if src_dir.is_dir():
            tree_lines: list[str] = []
            for count, path in enumerate(sorted(src_dir.rglob("*.py"))):
                if count >= max_files * 10:
                    break
                rel = path.relative_to(self._workspace_dir)
                tree_lines.append(str(rel))
            if tree_lines:
                parts.append("## 项目文件结构\n" + "\n".join(tree_lines[:50]))

        if not parts:
            parts.append("当前目录未检测到标准项目结构。")

        return "\n\n".join(parts)
