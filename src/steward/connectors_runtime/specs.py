"""Declarative connector specifications (Airbyte-style shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AuthSpec(BaseModel):
    """Authentication requirements."""

    mode: str = Field(default="none")
    required_env: list[str] = Field(default_factory=list)


class StreamSpec(BaseModel):
    """Incremental stream description."""

    name: str
    cursor_field: str = "updated_at"
    page_size: int = 100


class ActionSpec(BaseModel):
    """Action contract for execute path."""

    name: str
    required_payload_fields: list[str] = Field(default_factory=list)
    retryable: bool = True


class ConnectorSpec(BaseModel):
    """Top-level connector definition."""

    connector: str
    implemented: bool = True
    auth: AuthSpec = Field(default_factory=AuthSpec)
    streams: list[StreamSpec] = Field(default_factory=list)
    actions: list[ActionSpec] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
