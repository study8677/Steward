"""动作执行结果校验服务。"""

from __future__ import annotations

from steward.connectors.base import ExecutionResult


class VerifierService:
    """执行后校验器。"""

    def verify(self, results: list[ExecutionResult]) -> tuple[bool, str]:
        """校验执行结果是否全部成功。"""
        failed = [item for item in results if not item.success]
        if failed:
            return False, failed[0].detail
        return True, "all_steps_verified"
