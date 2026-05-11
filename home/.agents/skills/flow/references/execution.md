# Execution Methodology

This document is the methodology for executor agents. Read this before executing any plan.

## Principles

- Follow the plan step by step — it was reviewed and approved
- Verify each step before moving to the next
- Fix bugs and blockers autonomously; escalate architecture changes
- Commit atomically per logical unit
- Update ITEM.md progress as you go

## Execution Process

1. **Read the plan**: Understand all steps and their verification criteria
2. **For each step**:
   a. Implement the step
   b. Run the verification check
   c. If verification passes: mark step complete in ITEM.md, continue
   d. If verification fails: debug and fix. If fix requires changing the plan's approach, stop and report.
3. **After all steps**: Run acceptance criteria checks
4. **Report results**: Completed steps, any deviations, remaining issues

## Deviation Handling

**Auto-fix** (no escalation needed):
- Typos, syntax errors, import issues
- Minor API differences from what research expected
- Test failures with obvious fixes
- Missing directories or files that need creating

**Escalate** (stop and report):
- Approach doesn't work as planned — need a different strategy
- Missing dependency or capability not identified in research
- Standards conflict discovered during implementation
- User input needed for a decision

## Commit Discipline

- Commit after each logical unit of work (usually 1-3 plan steps)
- Commit message references the item: "flow(<item>): <what was done>"
- Don't bundle unrelated changes
- Don't commit broken states — verify before committing

## Progress Updates

After each step, update the item's ITEM.md:
- Check off completed progress items
- Add log entry with date and what was done
- Update status if it changed (e.g., in_progress -> blocked)

## Return Format

When execution is complete, return:

```markdown
## EXECUTION COMPLETE

### Completed Steps
- Step 1: <name> — done
- Step 2: <name> — done

### Deviations
- <Any differences from the plan, with rationale>

### Issues
- <Any unresolved problems or follow-ups needed>

### Acceptance Criteria Status
- [x] <Criteria 1>
- [ ] <Criteria 2 — why not met>
```
