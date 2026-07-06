---
name: wrapping-up
description: Use when a feature, branch, or substantial work session is finishing — work is implemented and verified, before or just after opening/merging a PR — to capture what was built and what was learned.
---

# Wrapping Up

## Overview

At the end of a substantial piece of work, write down two things before the context is lost: **what got decided** (a recap) and **what got learned** (durable knowledge). Both live in the repo under `docs/`.

The split matters: a recap is about *this* feature and ages with it; knowledge is reusable across unrelated future work. Mixing them buries the durable lesson inside a feature story nobody re-reads.

## The two artifacts

| Artifact | Path | Scope | Lifecycle |
|---|---|---|---|
| Recap | `docs/recap/YYYY-MM-DD-<topic>.md` | This feature/session | One file per effort |
| Knowledge | `docs/knowledge/<area>.md` (e.g. `gotchas.md`) | Cross-session, reusable | Append over time |

### Recap — what got decided

Capture only what the spec and plan **don't** already say. A recap is the delta between the plan and reality:

- Divergences from the plan, and why
- Decisions made during implementation (not pre-recorded in the design)
- Findings from live validation / real runs
- Follow-ups filed (issue numbers) and deferred scope

Do **not** restate the design, the architecture, or anything already in the spec/plan — link to those instead. If a paragraph would survive unchanged in the spec, it belongs in the spec, not the recap.

### Knowledge — what got learned

Append durable, reusable lessons. The test: **would this help a future task unrelated to this feature?** If yes, it's knowledge. Group by area (environment, the SDK/library, schema/state, tooling/workflow). Each entry is the gotcha + the fix, stated so it's actionable cold — no session narrative ("we then tried…").

## Quick procedure

1. Recap → `docs/recap/YYYY-MM-DD-<topic>.md`: divergences, decisions, live findings, follow-ups.
2. Knowledge → append to the matching `docs/knowledge/*.md` (create `gotchas.md` if none fits).
3. Run the repo's pre-commit on the new files; commit with a `docs:` message.
4. Ask where it should land (feature branch / PR vs. main) before pushing — don't assume.

## Common mistakes

- **Recap restates the spec.** Cut anything already in the design; keep only the delta.
- **Knowledge written as a story.** "We discovered X by trying Y" → rewrite as "X. Do Z." stated for a cold reader.
- **Feature-specific gotcha filed as durable knowledge** (or vice versa). Apply the reuse test.
- **Auto-committing/pushing.** These are repo docs — confirm destination and follow the project's commit rules first.
