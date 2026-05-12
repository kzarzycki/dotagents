---
allowed-tools: Bash(tmux:*), Bash(python3:*), Bash(sleep:*), AskUserQuestion
description: Fork current Claude session into a new tmux window
argument-hint: [rewind-turns]
---

## Context
- TMUX: !`echo ${TMUX:-NOT_IN_TMUX}`

## Task

Fork the current Claude Code session into a new tmux window using `--fork-session`, optionally rewinding to an earlier conversation point.

If TMUX context shows NOT_IN_TMUX, tell the user this command requires tmux and stop.

## Steps

### 1. Determine fork point

If an argument was provided (a number), use it as the number of turns to rewind. Skip to step 3.

If no argument was provided:
- List the last 5-8 user prompts from this conversation (from your context memory — actual user messages, not tool results). Number them 1 = most recent, 2 = second most recent, etc. Show ~80 characters of each.
- Ask: "Fork from which point? (N = rewind N turns, 0 or Enter = full conversation)"

### 2. Wait for user response

Use AskUserQuestion to get their choice. Parse 0 or empty as "no rewind".

### 3. Fork the session

Run a single bash command that:
1. Gets the session ID from `~/.claude/history.jsonl` — find the last entry where `project` matches the current working directory
2. Creates a new tmux window: `tmux new-window -c "$(pwd)" -P -F '#{pane_id}'` to capture the pane ID
3. Sends the claude command to that pane: `tmux send-keys -t <PANE_ID> 'claude --resume <SESSION_ID> --fork-session' Enter`

Example:
```bash
SESSION_ID=$(python3 -c "
import json, os
cwd = os.getcwd()
sid = None
with open(os.path.expanduser('~/.claude/history.jsonl')) as f:
    for line in f:
        try:
            obj = json.loads(line)
            if obj.get('project') == cwd: sid = obj['sessionId']
        except: pass
print(sid or '')
") && \
PANE_ID=$(tmux new-window -c "$(pwd)" -P -F '#{pane_id}') && \
tmux send-keys -t "$PANE_ID" "claude --resume $SESSION_ID --fork-session" Enter
```

If SESSION_ID is empty, tell the user the session ID could not be found and stop.

### 4. Rewind (if turns > 0)

If the user chose to rewind N turns:
```bash
sleep 7 && tmux send-keys -t "$PANE_ID" "/rewind" Enter
```
Tell the user: "Forked session opening. A /rewind will be sent after Claude starts — pick the right checkpoint in the new window."

Note: PANE_ID won't persist between bash calls. Combine the sleep+send-keys in the same bash call as step 3, or re-derive the pane ID.

### 5. Confirm

Tell the user the forked session is ready in the adjacent tmux window.
