---
name: ask-user
description: Ask which installed skill or workflow fits the user's situation.
disable-model-invocation: true
---

# Ask User

Route the user's situation to the smallest suitable workflow. Explain the recommendation briefly, then ask whether they want to invoke it. Do not invoke another user-invoked skill without confirmation.

## Main Flow

For an idea that needs to ship:

1. Use `/grill-with-docs` to sharpen an idea in a codebase while updating `CONTEXT.md` and ADRs. Use `/grill-me` when there is no codebase or durable project documentation is not wanted.
2. If a design question needs a runnable answer, use `/handoff` to branch into a fresh `/prototype` session, then `/handoff` the findings back.
3. For work that fits one session, use `/implement` directly. For multi-session work, use `/to-spec`, then `/to-tickets`, and start a fresh `/implement` session for each unblocked ticket.

`/implement` drives `/tdd` at agreed seams and closes with `/code-review`. Use `/tdd` or `/code-review` directly when only that focused workflow is needed.

Keep grilling, specification, and ticketing in one context window when practical. Use `/handoff` before context quality degrades; clear context between independently implementable tickets.

## On-Ramps

- Incoming bugs and requests that are not already agent-ready: `/triage`.
- A hard bug, intermittent failure, or performance regression: `/diagnosing-bugs`.
- A huge, foggy effort whose path cannot fit one session: `/wayfinder`, then `/to-spec` when the decision map is clear.

Do not triage tickets produced by `/to-tickets`; they are already agent-ready. Do not send a resolved wayfinder map directly to `/implement` unless the effort proved genuinely small.

## Codebase Health

- Survey a codebase for deepening opportunities: `/improve-codebase-architecture`.
- Design a chosen module or seam using deep-module vocabulary: `/codebase-design`.
- Resolve unclear or overloaded domain terminology: `/domain-modeling`.

## Crossing Sessions

- Use `/handoff` to open a new conversation while preserving relevant conversation and workspace state in `.tmp/handoff/`.
- Use the platform's compact feature to continue the same conversation with summarized history.

## Standalone

- `/prototype`: answer one state, logic, or UI design question with throwaway code.
- `/research`: delegate primary-source research and capture cited findings in the repo.
- `/teach`: learn a concept over multiple sessions in a stateful workspace.
- `/writing-great-skills`: guide the creation or revision of a skill.
- `/resolving-merge-conflicts`: resolve an in-progress merge or rebase by intent.

## Precondition

Use `/setup-matt-pocock-skills` once per repository before engineering flows that depend on its issue tracker, labels, or domain documentation layout.
