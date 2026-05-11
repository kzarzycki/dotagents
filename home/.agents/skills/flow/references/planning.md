# Planning Methodology

This document is the methodology for planning agents. Read this before creating any execution plan.

## Principles

- Plans are executable — clear steps, not vague goals
- Honor research recommendations; don't re-decide what research already decided
- Honor standards from `.work/standards/`
- Each step must be verifiable — if you can't check it, it's not a step
- Prefer fewer, meatier steps over many tiny ones

## Planning Process

1. **Read context**: Brief, research findings, standards, ITEM.md
2. **Identify the approach**: Based on research recommendation (if available)
3. **Break into steps**: Ordered by dependency, each with clear scope
4. **Define verification**: How to confirm each step succeeded
5. **Set acceptance criteria**: Observable outcomes for the whole item
6. **Review against standards**: Flag any conflicts

## Plan Output Format

Write to items/<name>/plan.md:

```markdown
# <Item Name> Plan

## Approach
<1-2 paragraph summary. Reference research decisions if applicable.
Explain WHY this approach, not just WHAT.>

## Steps
1. [ ] **<Step name>**: <What to do>
   - Files: <paths to create/modify>
   - Verify: <how to confirm this step worked>

2. [ ] **<Step name>**: <What to do>
   - Files: <paths>
   - Verify: <check>

## Acceptance Criteria
- <Observable outcome 1>
- <Observable outcome 2>
- <Observable outcome 3>
```

## Guidelines

- Steps should be completable in a single focused work session
- "Files" lists should be specific paths, not "various files"
- "Verify" should be a concrete action (run a test, check output, confirm behavior)
- Don't plan steps the user hasn't asked for (no scope creep)
- If research is missing for a step, flag it rather than guessing
- Keep the plan under 50 lines for small items, under 100 for large ones
- End with `## PLAN COMPLETE` so the orchestrator can detect completion
