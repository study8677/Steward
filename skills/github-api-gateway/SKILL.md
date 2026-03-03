---
name: github-api-gateway
description: Execute GitHub issue/PR operations through authenticated API with webhook-safe checks.
---

# GitHub API Gateway

Use this skill for GitHub operations that require real API calls.

## Capabilities

- Read issue/PR context.
- Add issue comments.
- Update issue state (open/closed) when explicitly requested.
- Validate webhook signature and dedup id for inbound events.

## Minimal procedure

1. Validate identifiers: `owner`, `repo`, `issue_number`.
2. Fetch latest issue + recent comments.
3. Generate grounded reply (prefer bilingual for user-facing repos).
4. Post comment with idempotent dispatch context.
5. Record result status and error details.

## Safety

- Never leak tokens/secrets.
- Avoid replying to self-generated bot comment events.
- Keep write operations limited to requested repo scope.

