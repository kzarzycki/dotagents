---
name: product-discovery
description: Structured grilling to clarify a vague product/feature need before any implementation. Invoke only on /product-discovery. Produces a discovery log + the artifact the user requests (PRD, RFC, design note, message, or just chat clarity).
---

# Product Discovery

Turn a vague feature idea into a clean spec by interrogating the user with structured, batched questions, while keeping them firmly in the driver's seat.

## When to fire

Only on explicit `/product-discovery`. Never auto-trigger on conversational cues.

Typical context: the user has an idea but no clear spec, and explicitly wants to design/specify before implementing.

## Lifecycle

`discovery → draft → independent review → triage → iterate (≤ 3 review passes) → sign off`

The discovery log is written alongside throughout. The independent-review step is the difference between a draft you're proud of and a doc ready to hand to implementation — do not skip it unless the user explicitly says so.

## Opening protocol

Before any grilling, in this order:

1. **Ask the desired output** (one short AskUserQuestion). What artifact ends this session — PRD, RFC, design note, slack-message-length summary, just chat clarity? Should the discovery couple with Flow (`.work/` work item) if `.work/` exists?
2. **State your read of the need** — ≤ 4 bullets, in your own words. Catches misreads early.
3. **Begin Round 1.**

## Grilling

### Cadence
- 3-4 questions per AskUserQuestion call. 3-5 rounds total.
- End each round with a one-sentence pacing note ("Round 2 — 2 more after this").
- Hard stop at round 5. If you're still confused, switch to focused open-ended questions; don't run round 6.

### Question design
- Every question must reshape the artifact. If the answer doesn't change what you write, drop it.
- Each option carries a label *and* a description that exposes the tradeoff. Not just labels.
- 3-4 options per question. More than 4 → split into two questions.
- Multi-select for legitimate "and" answers (use cases, denominations); single-select for mutually exclusive (architecture choice, primary lens).
- Always include an escape hatch: "Defer to V2", "I want a recommendation", or rely on "Other" being injected automatically.

### Round ordering — shape-changing first
1. **Foundational** — primary use case, scope, definition of "the thing"
2. **Math / semantics** — what numbers mean, how things are measured
3. **UX / structure** — views, slicings, layouts, naming
4. **Architecture / data** — where it lives, where data comes from
5. **Sanity** — why custom, why now, comparison to existing tools

### Synthesis between rounds
After each result, give 1-3 bullets recapping what sharpened. The user must feel you're listening and converging, not just collecting answers.

### When to stop grilling and draft
- User starts giving narrative answers ("I don't know yet", "let's start with X then iterate") instead of picking options → you have enough.
- 5 rounds reached.
- Diminishing returns: latest round didn't change much.

## Drafting the artifact

Three rules apply to whatever you write — PRD, RFC, design note, even a chat summary. They are non-negotiable. They also apply to this skill file itself.

### Rule 1 — Order: high-level to low-level, stable to volatile

Stable, user-visible content first. Volatile, implementation-specific content later. Clean structural break between them.

For a spec, this typically means:

```
Vision → Problem → Users → Use cases → Behavior / what is shown → Acceptance criteria
   ── break (Part 1: Product / Part 2: Architecture) ──
Architecture → Data dependencies → Code structure → Open questions → Risks
   ── break (Part 3: Roadmap) ──
V2+ items
```

Acceptance criteria belong with the product half (stable). Schemas, file paths, code surfaces belong with the architecture half (volatile). A reader should be able to stop at any depth and still have a coherent picture.

### Rule 2 — No additive bloat (rewrite as if first draft)

When iterating a doc, rewrite cleanly. Never preserve in the doc body:
- "Originally we had X but pivoted to Y"
- "Per discussion in chat, we decided..."
- "v0.1 said A; this version changes to B"
- Decision rationale ("chose X over Y because Z") inside the spec

Decisions and history live in a separate `discovery.md` or in commit messages — never inline in the spec.

Before each revision, ask each sentence: "if this were the first draft, would this sentence be here?" If no, delete. The reader needs current truth, not iteration history.

### Rule 3 — Extend, don't invent

Before proposing new structure (a new file, table, config, module, abstraction), check what existing structure can absorb the change. Read the codebase. Grep for the concept. Ask the user "where do we already define X?" if unclear.

Default = extend. New structure carries the burden of proof — you must articulate why the existing place genuinely doesn't fit.

Concrete trap: writing "we'll add a new `<thing>_config.py`" without first verifying whether `<thing>` is already configured somewhere.

## Output skeleton — PRD-shaped

When the user asks for a PRD or spec:

```
# <Feature Name>
Status: Draft v0.x — YYYY-MM-DD

## Vision (1 paragraph)
## Problem
## Users

# Part 1 — Product
## Use cases (V1)
## Where it lives
## What is shown / behavior
## Semantics (math, definitions, edge cases)
## Out of scope (V1)
## Acceptance criteria

# Part 2 — Architecture
## Data dependencies (what's already available; what's missing)
## Code structure / surfaces touched
## Open questions
## Risks / limitations

# Part 3 — Roadmap (V2+)
```

The break between Parts 1 and 2 is load-bearing — don't blur it. Adjust the section list to topic, but preserve the stable→volatile gradient.

## Output skeleton — lighter shapes

For an RFC: same backbone, condense to one section per Part.
For a design note: drop Part 3, keep Parts 1 and 2.
For a slack-message summary: 5-7 bullets total, ordered Vision → Behavior → Architecture → Open questions.
For chat-only clarity: end with a 3-bullet recap; no file written.

## Independent review

After drafting, spawn an independent reviewer to find problems with the artifact. This catches what the drafter cannot see: math errors, schema fields that don't exist, invented abstractions, leaks between Part 1 and Part 2, decision-rationale fossils, contradictions between sections. One Agent call buys substantial confidence.

### Setup

- Spawn a fresh `general-purpose` Agent. Do NOT show prior reviews or your own framing of the artifact — independence is the entire point.
- Use the verbatim template in `references/reviewer-prompt.md`. Fill the `<...>` slots with paths and one-liners specific to this artifact.
- Inputs the reviewer must read:
  - The writing-quality rules (Rules 1, 2, 3) — to judge doc-quality
  - The current artifact
  - The existing structure the artifact extends or replaces (if any)
  - Codebase / schema / config files needed to verify factual assertions in the artifact
- Charter the reviewer explicitly: "find problems, not approval." Reviewers default to politeness; counter that.

### Triage

Each finding falls into one of three buckets:

1. **Autonomous fix** — clear correction needing no user input (wrong schema field, missing fee arithmetic in worked example, decision-rationale fossil to remove, layout spec to add). Apply directly, do not bother the user.
2. **User-decision fix** — a product call only the user can make (denominator semantics, headline framing, scope expansion, naming). Surface via AskUserQuestion in batched rounds, same shape as discovery grilling.
3. **Reviewer-was-wrong** — defend with reasoning. Reviewers sometimes overshoot or misread. Verify their critique against the codebase before bowing. State the disagreement to the user when surfacing the review summary, so they can override your defense if they want.

Reviewers are independent, not authoritative. Both rubber-stamping their findings and silently ignoring them are failure modes.

### Iteration loop

Revise the artifact (apply autonomous fixes; resolve user-decision fixes via grilling), then re-review with a fresh agent.

Stop when one of these is true:
- Verdict is READY.
- Verdict is READY WITH CAVEATS and the remaining caveats are items the user has explicitly accepted as not-blocking.
- A re-review surfaces only nitpicks (no Top Problems).

**Hard cap: 3 review passes.** If still NOT READY after 3, the artifact's approach is wrong — escalate to the user, do not loop further.

### Surfacing the review to the user

After each review, present:
- The verdict in one line
- A short list of "what I'll fix autonomously" (the bucket-1 items)
- The user-decision items as AskUserQuestion (the bucket-2 items)
- Any reviewer-was-wrong items with your defense

The user can always override your triage. Don't hide the review's text behind your summary.

## Discovery log (companion artifact, always)

Whatever the main artifact is, also write a `discovery.md` capturing:
- The user's stated need (verbatim where useful)
- Decisions made (one bullet each, no rationale-essays)
- Defaults proposed for unanswered details
- Open items still pending

This is where iteration history and rationale live. Keeping it separate from the main artifact is what enables Rule 2.

## Anti-patterns

- One question per round (always batch 3-4)
- Questions whose answer doesn't change the artifact
- Drafting before round 3 unless the user is converging fast
- Grilling past round 5 — switch to open-ended
- Skipping between-round synthesis
- Options without escape hatches
- Mixing user-visible and implementation content in the same section (violates Rule 1)
- Iterating a doc by accretion (violates Rule 2)
- Proposing new files/configs without exploring existing structure (violates Rule 3)
- Skipping independent review on "the draft is good enough"
- Showing the reviewer prior reviews or your framing (kills independence)
- Accepting reviewer findings uncritically (some are wrong; defend when warranted)
- Hiding the reviewer's text behind your own summary (the user must see the review)
- Looping past 3 review passes (escalate instead — the approach is wrong)
