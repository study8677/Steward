---
name: self-improving-agent
description: Plan -> Execute -> Reflect loop for continuous quality improvement with measurable feedback.
---

# Self-Improving Agent

Use this skill when tasks should run in a closed-loop agent cycle.

## Loop

1. Plan
- Define goal, constraints, risk, and success criteria.
- Produce minimal executable steps.

2. Execute
- Run one step at a time.
- Persist attempt details and errors.

3. Reflect
- Decide `continue | halt | replan`.
- If `replan`, append validated next steps only.

4. Learn
- Record failures and user feedback into next-plan heuristics.

## Rules

- Prefer low-risk auto execution.
- Escalate irreversible/high-risk actions to confirmation.
- Keep summaries human-readable (zh/en if external facing).

## Acceptance

- Every run must leave auditable trace: dispatch status, attempt status, reflection decision.
- No noop/placeholder executable path.

