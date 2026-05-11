# Verification Methodology

This document is the methodology for verifier agents. Read this before verifying any completed work.

## Principles

- Goal-backward: start from acceptance criteria, verify each one
- Check existence, reality, and wiring — not just that code was written
- Run tests if they exist
- Report gaps with specific fix suggestions

## Verification Process

1. **Read acceptance criteria** from the item's plan.md
2. **For each criterion**, verify three things:
   - **Exists**: Is the code/feature/file actually there?
   - **Real**: Is it a real implementation (not a stub, placeholder, or TODO)?
   - **Wired**: Is it connected and used (imported, called, routed, rendered)?
3. **Run tests** if the project has them (and they're relevant to this item)
4. **Check for regressions**: Did the work break anything that was working before?
5. **Report findings**

## Verification Checks

For each acceptance criterion:

```
Criterion: "<the expected outcome>"
- Exists: YES/NO — <where it is>
- Real: YES/NO — <is it a real implementation or placeholder>
- Wired: YES/NO — <is it connected to the rest of the system>
- Verdict: PASS/FAIL
- Fix (if FAIL): <specific action to fix>
```

## Return Format

```markdown
## VERIFICATION COMPLETE

### Results
| Criterion | Exists | Real | Wired | Verdict |
|-----------|--------|------|-------|---------|
| ...       | YES    | YES  | YES   | PASS    |
| ...       | YES    | YES  | NO    | FAIL    |

### Gaps
- <Gap description>: <Specific fix suggestion>

### Tests
- Ran: <test command>
- Result: <pass/fail with details>

### Overall: PASS / FAIL
<Summary and recommended next steps if FAIL>
```
