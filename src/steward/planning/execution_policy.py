"""Enforce execution-time policy checks on compiled plans."""

from __future__ import annotations

from dataclasses import dataclass

from steward.planning.plan_compiler import ExecutablePlan


@dataclass(slots=True)
class PlanPolicyViolation:
    """Single policy violation."""

    code: str
    message: str


class ExecutionPolicy:
    """Runtime execution policy guardrail."""

    def evaluate(self, plan: ExecutablePlan) -> list[PlanPolicyViolation]:
        """Return policy violations for a compiled plan."""
        violations: list[PlanPolicyViolation] = []

        if not plan.steps:
            violations.append(
                PlanPolicyViolation(
                    code="no_steps",
                    message="plan contains no executable steps",
                )
            )

        for step in plan.steps:
            if step.connector == "manual" and step.action_type == "noop":
                violations.append(
                    PlanPolicyViolation(
                        code="manual_noop_forbidden",
                        message="manual noop actions are not allowed",
                    )
                )
            if step.connector == "local":
                violations.append(
                    PlanPolicyViolation(
                        code="local_connector_disabled",
                        message="local connector execution is disabled",
                    )
                )

        if plan.risk_level == "high" and not plan.requires_confirmation:
            violations.append(
                PlanPolicyViolation(
                    code="high_risk_needs_confirmation",
                    message="high risk plan must require manual confirmation",
                )
            )

        return violations
