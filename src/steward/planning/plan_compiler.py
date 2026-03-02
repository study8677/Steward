"""Compile and validate executable plans from planner output."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, ValidationError


class ExecutableStep(BaseModel):
    """A single executable step bound to a connector/action pair."""

    connector: str = Field(min_length=1, max_length=64)
    action_type: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    verification: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = True


class ExecutablePlan(BaseModel):
    """Validated executable plan."""

    intent: str = Field(min_length=1, max_length=128)
    risk_level: str = Field(min_length=1, max_length=16)
    reversibility: str = Field(min_length=1, max_length=16)
    requires_confirmation: bool
    source: str = Field(min_length=1, max_length=32)
    source_ref: str = Field(default="", max_length=255)
    steps: list[ExecutableStep] = Field(default_factory=list)


@dataclass(slots=True)
class PlanCompilationError:
    """Compilation failure details."""

    reason: str
    details: list[str]


class PlanCompiler:
    """Turn loose plan steps into strict executable plan schema."""

    _github_ref = re.compile(
        r"(?:github:(?:issue|pr):)?(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)#(?P<number>\d+)",
        re.IGNORECASE,
    )

    def __init__(self, writing_guidance: str = "", executing_guidance: str = "") -> None:
        self._writing_guidance = writing_guidance.strip()
        self._executing_guidance = executing_guidance.strip()

    def compile(
        self,
        *,
        intent: str,
        source: str,
        source_ref: str,
        risk_level: str,
        reversibility: str,
        requires_confirmation: bool,
        raw_steps: list[dict[str, Any]],
    ) -> tuple[ExecutablePlan | None, PlanCompilationError | None]:
        """Validate and normalize raw step dictionaries."""
        normalized_steps: list[dict[str, Any]] = []
        errors: list[str] = []

        for index, raw in enumerate(raw_steps):
            if not isinstance(raw, dict):
                errors.append(f"step[{index}] is not object")
                continue

            connector = str(raw.get("connector", "")).strip().lower()
            action_type = str(raw.get("action_type", "")).strip()
            payload = raw.get("payload", {})

            if not connector:
                errors.append(f"step[{index}] missing connector")
                continue
            if not action_type:
                errors.append(f"step[{index}] missing action_type")
                continue
            if not isinstance(payload, dict):
                errors.append(f"step[{index}] payload must be object")
                continue

            step = {
                "connector": connector,
                "action_type": action_type,
                "payload": payload,
                "verification": raw.get("verification") or {},
                "retryable": bool(raw.get("retryable", True)),
            }
            normalized_steps.append(step)

        if source == "github":
            self._repair_github_steps(source_ref=source_ref, steps=normalized_steps, errors=errors)

        if not normalized_steps:
            details = errors or ["no_executable_steps"]
            if self._writing_guidance:
                details.append(f"writing_guidance:{self._writing_guidance.splitlines()[0][:120]}")
            if self._executing_guidance:
                details.append(
                    f"executing_guidance:{self._executing_guidance.splitlines()[0][:120]}"
                )
            return None, PlanCompilationError(reason="no_executable_steps", details=details)

        try:
            plan = ExecutablePlan(
                intent=intent,
                source=source,
                source_ref=source_ref,
                risk_level=risk_level,
                reversibility=reversibility,
                requires_confirmation=requires_confirmation,
                steps=[ExecutableStep.model_validate(item) for item in normalized_steps],
            )
        except ValidationError as exc:
            return None, PlanCompilationError(reason="schema_validation_failed", details=[str(exc)])

        return plan, None

    def _repair_github_steps(
        self,
        *,
        source_ref: str,
        steps: list[dict[str, Any]],
        errors: list[str],
    ) -> None:
        match = self._github_ref.search(source_ref)
        if match is None:
            return

        owner = match.group("owner")
        repo = match.group("repo")
        number = int(match.group("number"))

        for step in steps:
            if step.get("connector") != "github":
                continue
            payload = step.get("payload", {})
            if not isinstance(payload, dict):
                continue
            payload.setdefault("owner", owner)
            payload.setdefault("repo", repo)
            payload.setdefault("issue_number", number)

            if (
                not payload.get("owner")
                or not payload.get("repo")
                or int(payload.get("issue_number", 0)) <= 0
            ):
                errors.append("github step still missing owner/repo/issue_number")
