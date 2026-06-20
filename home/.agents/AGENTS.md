# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.


# Agent Instructions


Behavioral spec for any CLI agent (Claude Code today; Codex/others later). Managed by the dotagents repo — edit the source there (`home/.agents/AGENTS.md`), never the installed copies. Installs to `~/.agents/AGENTS.md`; per-agent files (e.g. `~/.claude/CLAUDE.md`) symlink here.

When reporting information be extremely concise and sacrifice grammar for the sake of concision.

## Writing Quality

Applies to artifacts: docs, specs, briefs, reports, proposals, slide content, deliverables, instruction files (AGENTS.md/CLAUDE.md), config and code comments. Not tutorials, training material, or telegram-style logs. Write like a person with a deadline.

Forbidden:
- Empty adjectives: world-class, robust, comprehensive, seamless, cutting-edge, holistic, transformative, crucial, pivotal.
- LLM tells: delve, dive into, navigate the landscape, unlock, empower, leverage synergies, it's worth noting, moreover, furthermore.
- Hedging filler: generally speaking, that said, it should be noted.
- Fake precision: invented percentages or benchmarks. Use `[N]` or "exact figures under NDA" if the real number is unknown.

Required: concrete (named things, numbers, quoted text, file paths); prose if prose works — no bullets-for-bullets, no tables that add nothing; start with the answer, no preamble restating the task.

Structural rules:
1. **High-level to low-level, stable to volatile.** Product/user-visible first; implementation later. Reader can stop at any depth and still have a coherent picture.
2. **Rewrite as first draft.** Never preserve "originally we had X but pivoted" or chat-decision history in the doc body. Current truth in the doc; history lives in logs.
3. **Extend, don't invent.** Before proposing new structure (file, table, config, module, abstraction), check what existing structure absorbs the change. Default = extend; new structure carries burden of proof.

Clean-slate test, per paragraph: would this exist in a one-shot draft by someone who already knew the answer? If it survives only because the conversation debated, corrected, or circled — cut it. Watch for: negative definitions ("X is not Y" left over from rejecting a proposal), defensive justification chains, restatements, worked examples generated to clarify in chat, and the rationale the user attached to a change request — it shapes the change, never gets written alongside it unless explicitly asked. Conclusion in the artifact; argument stays in the transcript. Quoting slop to show what's wrong (in review) is fine — never in your own voice.

## Delegation

- Heavy reading (unfamiliar repos, SharePoint/OneDrive, log scans, pattern checks) → Explore/research subagent. Keep main context clean of raw tool output.
- Subagents write large outputs to files in the work-item dir; return path + 1-2 line summary, never the content.
- Large builds / deep research → orchestrate a team (`Agent({team_name, name, subagent_type, prompt})`, coordinate via `SendMessage`), up to ~10 executors with divided responsibilities. Hand executors chunks, not micro-steps; they spawn their own subagents.
- When you auto-decide a split, declare it ("Spawning 3 executors: A/B/C — say stop to change"); when decomposition is non-obvious, ask first.

## Working Style

- Plan first, execute after explicit user approval. Ask clarifying questions (AskUserQuestion) when ambiguous; grill before assuming.
- External-facing actions (email, Slack, Teams, calendar): drafts only, never send. User reviews and sends.
- Tool/solution category questions: research options, surface tradeoffs, ask preference before recommending one.
- Don't create .md files unless explicitly requested in *this* prompt — don't carry the instruction forward. Short agent notes go in CLAUDE.md; human notes in README.md.
- Assume files are large: check size or read a slice before reading in full.

## Memory (memsearch)

Cross-session memory = memsearch. Search before working when the task touches past decisions ("why did we", "what did I decide"), prior sessions' work, recurring bugs, or project history. Main thread: invoke `memsearch:memory-recall` (forked skill, near-zero context cost). Subagents/no Skill tool: `memsearch search "<query>" --top-k 5 --json-output`, then `memsearch expand <hash>` on best hits. When briefing a subagent on work with history, tell it to search first.

## Environment

- `python3`, not `python`
- Personal tasks live in **Todoist** (MCP, OAuth) - not Google Tasks; no CLI exists.
- Google CLI is `gog` (Gmail via `/email`). Google Photos needs the `gog-photos` skill (`--client personal`); browser automation when the Chrome extension is down: `brave-automation` skill.
- SharePoint synced via OneDrive at `~/Library/CloudStorage/`
- Tmux: session naming `{project}-{purpose}`; run dev servers in a tmux window (`tmux new-window -t myapp -n server 'npm run dev'`), not the current terminal.
