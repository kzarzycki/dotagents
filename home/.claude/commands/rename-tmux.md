---
description: /rename unnamed Claude sessions in tmux, then refresh all tmux window names from the session titles
argument-hint: "[--force]"
---

Run the tmux window renamer and report what changed.

Two phases, always in this order:
1. For every tmux window running `claude`, if its session has no
   `custom-title` yet (i.e. it's never been titled), dispatch `/rename`
   into that pane so Claude generates one. `--force` dispatches to every
   session regardless.
2. Always re-rename every tmux window from the session's latest
   `custom-title` — tmux names go stale fast, so this step doesn't gate
   on anything.

```bash
python3 ~/.claude/scripts/tmux-rename-claude.py --apply $ARGUMENTS
```

If the user passes `--dry-run`, drop `--apply` from the command above.
