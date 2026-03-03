"""Quick Start capability bundle helper.

Usage:
  python scripts/quickstart_capabilities.py --bundle github
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from steward.core.config import get_settings
from steward.services.integration_config import IntegrationConfigService
from steward.services.model_gateway import ModelGateway


def enable_github_bundle(service: IntegrationConfigService) -> dict[str, Any]:
    """Enable GitHub-focused MCP + skills for first-run bootstrap."""
    enabled_mcp: list[str] = []
    enabled_skills: list[str] = []
    missing_skills: list[str] = []

    configured = service.configure_mcp_server(server="github", payload={"enabled": True})
    if str(configured.get("server", "")) == "github":
        mcp_status = service.set_mcp_server_enabled("github", True)
        if mcp_status is not None and bool(mcp_status.get("enabled")):
            enabled_mcp.append("github")

    for skill in [
        "gh-address-comments",
        "gh-fix-ci",
        "playwright",
        "gog",
        "self-improving-agent",
        "github-api-gateway",
    ]:
        status = service.set_skill_enabled(skill, True)
        if status is None:
            missing_skills.append(skill)
            continue
        if bool(status.get("enabled")):
            enabled_skills.append(skill)

    return {
        "bundle": "github",
        "enabled_mcp": enabled_mcp,
        "enabled_skills": enabled_skills,
        "missing_skills": missing_skills,
    }


def main() -> int:
    """Enable quickstart capability bundles via CLI."""
    parser = argparse.ArgumentParser(description="Enable quickstart capability bundles.")
    parser.add_argument("--bundle", default="github", choices=["github"])
    args = parser.parse_args()

    settings = get_settings()
    gateway = ModelGateway(settings)
    service = IntegrationConfigService(settings, gateway)
    service.load_runtime_overrides()

    if args.bundle == "github":
        result = enable_github_bundle(service)
    else:
        result = {
            "bundle": args.bundle,
            "enabled_mcp": [],
            "enabled_skills": [],
            "missing_skills": [],
        }

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
