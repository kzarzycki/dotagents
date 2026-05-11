Show current project status.

Read all .work/ state and present a concise overview:

1. Read .work/brief.md for project name
2. Read .work/state.md for tempo and active item
3. Scan .work/items/ — for each item directory, read its ITEM.md
4. Read .work/log.md (last 5 entries)
5. Read .work/ideas.md (count items)

Present in this format:

```
## [Project Name]
Tempo: [structured/creative]
Active: [item name or "none"]

## Items
| Item | Status | Progress |
|------|--------|----------|
| auth | in_progress | 3/5 steps |
| data-model | not_started | — |

## Recent Activity
- [last 3-5 log entries]

## Ideas Backlog
[N] ideas captured

## Suggested Next
[What makes sense to work on next, based on status and dependencies]
```

If .work/ doesn't exist, say: "No Flow workspace found. Run /flow:init to set one up."
