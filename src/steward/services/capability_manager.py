"""Skill/MCP 自管理服务（首版实现安装提议与审计占位）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CapabilityProposal:
    """能力安装建议。"""

    name: str
    reason: str
    source: str
    requires_confirmation: bool = True


class CapabilityManagerService:
    """管理外部能力的提议与生命周期（MVP 先实现建议层）。"""

    def propose_missing_capabilities(self, context: list[str]) -> list[CapabilityProposal]:
        """根据上下文返回安装建议。"""
        proposals: list[CapabilityProposal] = []
        joined = " ".join(context).lower()
        if "jira" in joined:
            proposals.append(
                CapabilityProposal(
                    name="jira-connector",
                    reason="检测到 Jira 相关任务但当前未启用连接器",
                    source="trusted-registry",
                )
            )
        return proposals
