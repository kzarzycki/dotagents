# Research Methodology

This document is the methodology for research agents. Read this before conducting any research task.

## Principles

- Treat Claude's training knowledge as a hypothesis — verify before asserting
- Prioritize accuracy over speed; wrong research compounds into wrong plans
- Structure findings for the downstream planner, not for a human report
- Be honest about confidence and gaps

## Confidence Levels

Tag every finding:
- **HIGH**: Verified against official docs, confirmed via web search, or tested
- **MEDIUM**: Consistent with training knowledge, not yet verified
- **LOW**: Uncertain, conflicting sources, or extrapolated

## Source Hierarchy

1. Official documentation (highest trust)
2. Verified web search results (check date, authority)
3. Training knowledge (useful starting point, must verify critical claims)
4. Community content (Stack Overflow, blogs — corroborate before relying on)

## Research Process

1. **Frame the question**: What exactly do we need to know? What decision does this inform?
2. **Survey the landscape**: Identify the main options/approaches. Don't go deep yet.
3. **Deep dive on contenders**: For the 2-4 most promising options, gather specifics.
4. **Compare**: Build a comparison table with consistent criteria.
5. **Recommend**: Pick one with clear rationale. State trade-offs honestly.
6. **Capture pitfalls**: What commonly goes wrong? What should the planner avoid?
7. **Flag unknowns**: What couldn't be determined? What needs user input?

## Research Output Format

Write findings to the appropriate location (items/<name>/research.md or .work/research/<slug>.md):

```markdown
# <Topic> Research

## Question
<What we need to know and what decision this informs>

## Findings

| Option | Pros | Cons | Confidence |
|--------|------|------|------------|
| ...    | ...  | ...  | HIGH       |

## Recommendation
<Clear recommendation with rationale. State the trade-offs.>

## Key Patterns
<Code patterns, architecture decisions, or implementation details the planner should use>

## Pitfalls
<Common mistakes to avoid. Things that look right but aren't.>

## Open Questions
<What we still don't know. Be honest — don't pretend certainty.>

## Sources
<URLs or references with confidence tags>
```

## Guidelines

- Compare at least 2 options for any significant decision
- Include version numbers and dates for libraries/tools
- If the research is for a specific item, stay focused on what that item needs
- If standalone research, be broader but still actionable
- Don't pad findings — shorter and accurate beats long and vague
- End with `## RESEARCH COMPLETE` so the orchestrator can detect completion
