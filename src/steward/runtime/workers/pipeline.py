"""执行流水线占位模块，用于后续扩展多 worker 并发策略。"""

from __future__ import annotations


class PipelineWorker:
    """流水线 worker 占位实现。"""

    async def run_once(self) -> None:
        """执行单次循环（当前为占位）。"""
        return None
