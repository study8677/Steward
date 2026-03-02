"""Validate connector actions against declarative specs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from steward.connectors_runtime.specs import ActionSpec, ConnectorSpec


class ConnectorRuntimeRunner:
    """Load connector specs and enforce payload contracts."""

    def __init__(self, specs_dir: Path | None = None) -> None:
        project_root = Path(__file__).resolve().parents[3]
        self._specs_dir = specs_dir or project_root / "config" / "connectors"
        self._specs: dict[str, ConnectorSpec] = self._load_specs()

    def names(self) -> list[str]:
        """Return registered connector spec names."""
        return sorted(self._specs.keys())

    def get_spec(self, connector: str) -> ConnectorSpec | None:
        """Return a connector spec by id."""
        return self._specs.get(connector)

    def validate_action(
        self,
        *,
        connector: str,
        action_type: str,
        payload: dict[str, Any],
    ) -> tuple[bool, str, ActionSpec | None]:
        """Validate action payload against the connector spec contract."""
        spec = self._specs.get(connector)
        if spec is None:
            return False, "connector_spec_missing", None
        if not spec.implemented:
            return False, "connector_not_implemented", None

        action = next((item for item in spec.actions if item.name == action_type), None)
        if action is None:
            return False, "action_not_supported", None

        missing = [
            field
            for field in action.required_payload_fields
            if payload.get(field) is None or payload.get(field) == "" or payload.get(field) == []
        ]
        if missing:
            return False, f"missing_payload_fields:{','.join(missing)}", action

        return True, "ok", action

    def _load_specs(self) -> dict[str, ConnectorSpec]:
        if not self._specs_dir.exists():
            return {}

        loaded: dict[str, ConnectorSpec] = {}
        for path in sorted(self._specs_dir.glob("*.yaml")):
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            except OSError, yaml.YAMLError:
                continue
            if not isinstance(raw, dict):
                continue
            try:
                spec = ConnectorSpec.model_validate(raw)
            except Exception:
                continue
            loaded[spec.connector] = spec
        return loaded
