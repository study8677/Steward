---
name: gog
description: Grounded Ops for GitHub (GoG). Build repository-grounded, low-risk issue responses and action plans.
---

# GoG (Grounded Ops for GitHub)

Use this skill when handling GitHub issues/comments and you need grounded answers from the current repo.

## Workflow

1. Ground in repo context first.
- Read `README.md`, `README_CN.md`, `agent.md`.
- Search implementation evidence with `rg` before making claims.

2. Understand issue intent.
- Extract: user question, expected outcome, risk level.
- If low risk, prepare direct response; if medium/high risk, propose confirmation-first plan.

3. Build answer with evidence.
- Chinese + English concise response.
- Include:
  - what is already implemented
  - what is missing / under tuning
  - next concrete step

4. Keep actions safe.
- No destructive changes.
- No secret disclosure.
- Prefer read-only inspection unless explicitly asked to modify.

## Output template

- Understanding: ...
- Current capability in repo: ...
- Suggested next step: ...
- (EN) Understanding / capability / next step: ...

