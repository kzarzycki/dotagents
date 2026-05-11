---
name: flow
description: Persistent workflow orchestration that survives context resets. Activates when users discuss work items, ask to research/plan/execute/verify, mention project setup, check status, capture ideas, or when .work/ exists and context needs recovery. Also triggers on explicit /flow commands.
---

# Flow — Persistent Workflow Orchestration

Enhance Claude Code with persistent context, structured delegation, and multi-item tracking.

## Philosophy

- Enhance CC, don't replace it. Main CC is the orchestrator.
- Delegate heavy lifting (research, planning, execution, verification) to subagents.
- Handle discussion, shaping, status, quick capture directly in main context.
- Persist to `.work/` what needs to survive compaction/sessions.
- Items are independent work streams — any order, parallel, or interleaved.

## Session Bootstrap

Two layers ensure context recovery:

**Layer 1 — SessionStart hook (automatic, installed by /flow:init):**
A hook at `.claude/hooks/flow-bootstrap.sh` fires on every session start. It reads `.work/state.md`, `brief.md`, active item's `ITEM.md`, and last log entries, then injects them as `additionalContext`. This happens before Claude processes any message — zero-latency recovery.

**Layer 2 — CLAUDE.md instructions (installed by /flow:init):**
Project CLAUDE.md contains Flow instructions telling CC to use the injected state, follow item lifecycle, and delegate via Flow methodology.

**Together:** The hook provides live state; CLAUDE.md provides behavioral rules. On session start, acknowledge the injected context briefly: "Recovered Flow: [project], active: [item] ([status])."

**If hook is not installed** (e.g., .work/ created manually): Fall back to reading .work/ files directly on first message. Check if `.work/` exists, read state.md and brief.md, announce context.

**If `.work/` doesn't exist:** Proceed normally. If conversation reveals a multi-step project, suggest: "This could use Flow tracking. Want me to set up a workspace?"

Subagents also bootstrap from ITEM.md — it's their manifest.

## Conversation Triggers

These behaviors activate from natural conversation. Each can also be invoked explicitly via `/flow:*` commands.

### Project Initialization

**When:** User describes a multi-step project and `.work/` doesn't exist, OR says "let's set up" / "initialize" / "start tracking."
**Then:**
1. Ask conversationally (2-3 questions max): what are you working on? Key constraints or tech? Structured or creative tempo?
2. Create `.work/` structure (brief.md, state.md, log.md, ideas.md, standards/, research/, items/)
3. Install Flow into project: append Flow section to CLAUDE.md, install SessionStart hook (.claude/hooks/flow-bootstrap.sh), update .claude/settings.json
4. Ask about git: track `.work/` or gitignore it?
5. If conversation revealed a first item, offer to create it
**Command:** `/flow:init` (see commands/init.md for full installation procedure)

### Item Creation

**When:** User starts discussing a new scope of work that doesn't map to an existing item, OR says "create an item for X" / "let's add X."
**Then:**
1. Confirm: "Creating item '[name]' — does that scope sound right?"
2. Create `.work/items/<name>/ITEM.md` with goal, context files, status: not_started
3. Update state.md, log it
**Guard:** If the task is trivial (< 30 min), suggest quick task instead.

### Item Switching

**When:** User says "switch to X" / "let's work on X" (where X is an existing item), OR conversation shifts to another item's scope.
**Then:**
1. Update state.md active item
2. Read the target item's ITEM.md
3. Announce: "Switched to [item] ([status]). Last activity: [latest log entry]."
**Guard:** If X isn't an existing item, treat as Item Creation.

### Research

**When:** User says "research X" / "what are our options for X" / "compare X vs Y" / "what's the best approach for X."
**Then:**
1. Determine scope: active item or standalone?
2. Check existing research (items/<name>/research.md or .work/research/)
3. If found: "Found existing research on [topic]. Build on it, or start fresh?"
4. Gather context: brief, standards, item ITEM.md (if item-specific)
5. Spawn research agent with methodology (references/research.md) + all context inlined
6. Write results to appropriate location
7. Update ITEM.md status to "researching", add log entry
**Guard:** Always check for existing research first.
**Command:** `/flow:research [topic]`

### Planning

**When:** User says "plan this" / "how should we approach X" / "break this down" / "let's plan X," OR research just completed and user wants to proceed.
**Then:**
1. Check for existing research on the topic
2. Ask: "Should I research [topic] before planning?" (skip if research already exists)
3. If yes: run Research trigger first, then continue
4. Spawn planning agent with methodology (references/planning.md) + research + brief + standards inlined
5. Write plan to items/<name>/plan.md
6. Update ITEM.md status to "planning", add log entry
7. Present plan summary for approval
**Guard:** Check existing plan.md first. If found, ask "revise existing plan or start fresh?"

### Execution

**When:** User says "go ahead" / "build it" / "execute" / "implement this" / "let's do it," OR plan was just approved.
**Then:**
1. Confirm which item and plan: "Executing [item] plan — [N] steps. Go?"
2. Spawn execution agent with methodology (references/execution.md) + plan + brief + standards inlined
3. On return: update ITEM.md progress (check off completed steps), add log entries
4. Report: completed steps, any deviations, remaining issues
**Guard:** If no plan exists, suggest planning first. If plan exists but no research, mention it.

### Verification

**When:** User says "check if it works" / "verify" / "test this" / "does it pass," OR execution just completed.
**Then:**
1. Spawn verification agent with methodology (references/verification.md) + plan (for acceptance criteria) + ITEM.md inlined
2. On return: report results (pass/fail per criterion, gaps, test results)
3. If all pass: suggest marking item complete
4. If gaps: list specific fixes needed
**Guard:** If no plan with acceptance criteria exists, ask what to verify against.

### Status Check

**When:** User says "where are we" / "status" / "what's the progress" / "what should I work on next."
**Then:**
1. Read brief.md, state.md, all items' ITEM.md files, last 5 log entries, ideas count
2. Present formatted: project name, tempo, items table (name/status/progress), recent activity, ideas count, suggested next action
**Guard:** If .work/ doesn't exist, say so and suggest /flow:init.
**Command:** `/flow:status`

### Quick Capture

**When:** User mentions something for later — a tangent, idea, follow-up. Key phrases: "remind me to" / "idea:" / "we should eventually" / "later we could."
**Then:**
1. Append to `.work/ideas.md` with date and brief description
2. Confirm: "Captured in ideas."
3. Continue current conversation without interruption
**Guard:** Don't capture if user is actively working on it (that's an item, not an idea).

### Item Completion

**When:** User says "X is done" / "mark X complete" / "finished with X," OR verification passes all criteria.
**Then:**
1. Update ITEM.md status to "done"
2. Update state.md (clear active item if it was this one)
3. Log completion
4. Ask: "What's next?" or suggest the next item based on state
**Guard:** If item has unchecked progress steps, mention them before completing.

### Idea Promotion

**When:** User says "let's make that idea a real item" / "promote [idea] to an item" / references an idea and wants to start working on it.
**Then:**
1. Read ideas.md, find the relevant idea
2. Create item from it (follow Item Creation)
3. Remove from ideas.md
4. Set as active item

### Quick Task

**When:** User wants something small done without the full lifecycle — "just do X" / "quick task" / trivial scope.
**Then:**
1. Create minimal .work/ if it doesn't exist (just log.md + ideas.md)
2. Do the work directly in main context — no agent delegation
3. Log to .work/log.md: "YYYY-MM-DD: Quick — [description]"
4. If scope grows: "This might be worth a full item. Captured in ideas."
**Command:** `/flow:quick [task]`

## Delegation Decision Tree

### Handle directly (no agent)
Discussion, clarification, shaping. Status checks. Quick capture. Item state management. Switching items. Quick tasks. Any single-file edit or simple question.

### Delegate to agent
Research requiring web search or deep comparison. Planning from research. Multi-step execution (>3 files or >100 lines of changes). Systematic verification against acceptance criteria.

### Heuristic for gray area
If the task touches >5 files, will produce >100 lines of changes, or requires comparing multiple options → delegate. Otherwise handle directly.

### Agent Spawning Protocol

When delegating:
1. Read the item's ITEM.md for its Context Files list
2. Read ALL listed context files
3. Read the relevant methodology from `references/` (research.md, planning.md, execution.md, or verification.md)
4. Inline EVERYTHING into the Task() prompt — @ syntax doesn't work across Task boundaries
5. Use `subagent_type = "general-purpose"`, description = "<stage>: <item name>"

### Agent Return Protocol

Agents end with structured headers: `## RESEARCH COMPLETE`, `## PLAN COMPLETE`, `## EXECUTION COMPLETE`, `## VERIFICATION COMPLETE`.

On return, always:
1. Write output to the appropriate file (research.md, plan.md, or update ITEM.md progress)
2. Update the item's ITEM.md (status, progress checkboxes, log entry)
3. Update state.md if the active item changed status
4. Append to log.md

## .work/ Structure

```
.work/
  brief.md          # What, why, constraints, decisions
  state.md          # Active items, tempo, overall progress
  log.md            # Append-only work log
  ideas.md          # Quick capture for later
  standards/        # User-maintained conventions (read-only for Claude)
  research/         # Standalone research (not tied to an item)
  items/
    <name>/
      ITEM.md       # Bootstrap manifest
      research.md   # Research findings
      plan.md       # Execution plan
      iterations/   # Creative tempo versions
```

## ITEM.md Format

Lifecycle: Create → Research → Plan → Execute → Verify → Done (any step skippable or revisitable).

```markdown
# <Item Name>
Created: YYYY-MM-DD

## Context Files
- .work/brief.md
- .work/items/<name>/research.md
- .work/standards/coding.md

## Goal
<What and why — 2-3 sentences>

## Status: not_started | researching | planning | in_progress | blocked | done

## Progress
- [ ] Research completed
- [ ] Plan created
- [ ] Step 1: ...
- [ ] Step 2: ...

## Log
- YYYY-MM-DD: Created item
```

## Tempo System

Set in state.md, per-project. Can switch mid-session.

**Structured** (default): Larger chunks, task-oriented. Follow the full Research → Plan → Execute → Verify cycle. Verify via acceptance criteria.

**Creative**: Small iterations, show early, ask opinions. Save versions to `items/<name>/iterations/` (v01.md, v02.md). More discussion between steps. "Here's a rough version. What direction feels right?"

## Standards, Concurrency, Anti-patterns

**Standards:** Read `.work/standards/` before planning or executing. Include in agent context. Flag conflicts. Never modify — user-maintained.

**Parallel sessions:** brief.md, standards/, research files are shared read-only. ITEM.md is per-item (no conflicts). log.md is append-only. Always re-read from disk.

**Anti-patterns:**
- No elaborate scaffolding or boilerplate PM artifacts
- No sensitive data in .work/
- Don't create items for casual mentions — wait for clear intent, confirm first
- Don't auto-delegate when user is just thinking out loud — confirm first
- Don't research what's already researched or re-plan what's already planned
- Don't skip the research check before planning

## Commands

Explicit shortcuts for the conversation triggers above. Both natural conversation and commands work.

- `/flow:init` — Project Initialization trigger
- `/flow:research [topic]` — Research trigger
- `/flow:status` — Status Check trigger
- `/flow:quick [task]` — Quick Task trigger
