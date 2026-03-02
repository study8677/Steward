"""Load planning/execution guidance assets from vendored superpowers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class SuperpowersAssets:
    """Resolved superpowers plan/execution guidance."""

    writing_plans: str
    executing_plans: str
    source_root: Path

    @classmethod
    def load(cls, project_root: Path | None = None) -> SuperpowersAssets:
        """Load vendored assets with safe fallbacks."""
        root = project_root or Path(__file__).resolve().parents[3]
        superpowers_root = root / "third_party" / "superpowers"

        writing = _read_asset(
            superpowers_root / "skills" / "writing-plans" / "SKILL.md",
            fallback=(
                "Write concrete execution plans with explicit assumptions, "
                "validation, and failure paths."
            ),
        )
        executing = _read_asset(
            superpowers_root / "skills" / "executing-plans" / "SKILL.md",
            fallback=(
                "Execute plans step by step, verify every step, and record outcomes "
                "for deterministic retries."
            ),
        )
        return cls(
            writing_plans=writing,
            executing_plans=executing,
            source_root=superpowers_root,
        )


def _read_asset(path: Path, fallback: str) -> str:
    if not path.exists():
        return fallback
    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError:
        return fallback
    return content or fallback
