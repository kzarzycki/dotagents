# Agent Instructions

The user's behavioral spec for any CLI agent. Installs to `~/.agents/AGENTS.md`; per-agent instruction files (`~/.claude/CLAUDE.md`, future Codex/pi equivalents) symlink to it.

## Tmux Conventions

- Session naming: `{project}-{purpose}` (e.g., `myapp-dev`, `myapp-tests`)
- To check output of another session: `tmux capture-pane -t {session} -p`
- Start dev servers in separate tmux windows, not in the current terminal
- Example: `tmux new-window -t myapp -n server 'npm run dev'`

## General workflow

When asked to implement something complex:
1. First grill the user to clarify all, instead of assuming. Can ask user how deep he wants to go.
1. Then outline the plan
1. Wait for confirmation
1. Then execute step by step
1. Then verify work

## Writing Quality (apply to every doc, spec, comment, summary)

Three rules. Universal. Violation = "AI slop."

1. **Order: high-level to low-level, stable to volatile.** Stable user-visible content first; volatile implementation later. Clean structural break (e.g., "Part 1 — Product / Part 2 — Architecture"). Acceptance criteria belong with the product half; schemas and file paths with the architecture half. A reader should be able to stop at any depth and still have a coherent picture.

2. **No additive bloat — rewrite as if first draft.** When iterating a doc, never preserve "originally we had X but pivoted", "per the chat we decided", "v0.1 said A; v0.2 changes to B", or decision-rationale essays inside the spec body. The reader needs current truth, not iteration history. Decisions and history live separately.

3. **Extend, don't invent.** Before proposing new structure (file, table, config, module, abstraction), check what existing structure can absorb the change. Read the codebase, grep for the concept, ask the user where it's already defined. Default = extend. New structure carries the burden of proof.
