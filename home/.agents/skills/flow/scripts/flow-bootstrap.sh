#!/bin/bash
# Flow session bootstrap hook
# Reads .work/ state and injects it as additionalContext on session start.
# Installed by /flow:init into .claude/hooks/

WORK_DIR=".work"

if [ ! -d "$WORK_DIR" ]; then
  exit 0
fi

# Read stdin JSON to extract session_id
HOOK_INPUT=$(cat)
SESSION_ID=$(echo "$HOOK_INPUT" | python3 -c \
  'import sys,json; print(json.load(sys.stdin).get("session_id",""))' 2>/dev/null)

CONTEXT=""

# Read brief (first 10 lines for summary)
if [ -f "$WORK_DIR/brief.md" ]; then
  BRIEF=$(head -20 "$WORK_DIR/brief.md")
  CONTEXT="## Project Brief\n$BRIEF\n\n"
fi

# Read state
if [ -f "$WORK_DIR/state.md" ]; then
  STATE=$(cat "$WORK_DIR/state.md")
  CONTEXT="${CONTEXT}## Current State\n$STATE\n\n"
fi

# Extract global active item from state.md
ACTIVE="none"
if [ -f "$WORK_DIR/state.md" ]; then
  ACTIVE=$(grep -i "^Active Item:" "$WORK_DIR/state.md" | sed 's/Active Item: *//' | tr -d '[:space:]')
fi
if [ -z "$ACTIVE" ]; then
  ACTIVE="none"
fi

# Override with per-session item if mapped
if [ -n "$SESSION_ID" ] && [ -f "$WORK_DIR/sessions" ]; then
  SESSION_ITEM=$(grep "^$SESSION_ID " "$WORK_DIR/sessions" | awk '{print $2}')
  if [ -n "$SESSION_ITEM" ]; then
    ACTIVE="$SESSION_ITEM"
  fi
fi

# Read active item's ITEM.md
if [ -n "$ACTIVE" ] && [ "$ACTIVE" != "none" ] && [ -f "$WORK_DIR/items/$ACTIVE/ITEM.md" ]; then
  ITEM=$(cat "$WORK_DIR/items/$ACTIVE/ITEM.md")
  CONTEXT="${CONTEXT}## Active Item: $ACTIVE\n$ITEM\n\n"
fi

# Read last 5 log entries
if [ -f "$WORK_DIR/log.md" ]; then
  LOG=$(tail -6 "$WORK_DIR/log.md")
  CONTEXT="${CONTEXT}## Recent Log\n$LOG\n\n"
fi

if [ -z "$CONTEXT" ]; then
  exit 0
fi

# Extract project name from brief.md (first heading) or fall back to directory name
PROJECT_NAME=$(head -1 "$WORK_DIR/brief.md" 2>/dev/null | sed 's/^#* *//')
if [ -z "$PROJECT_NAME" ]; then
  PROJECT_NAME=$(basename "$(pwd)")
fi

# Inject session ID so Claude can write session mappings
if [ -n "$SESSION_ID" ]; then
  CONTEXT="${CONTEXT}## Session\nSession ID: $SESSION_ID\n\n"
fi

# Generate behavioral directives based on current state
if [ -n "$ACTIVE" ] && [ "$ACTIVE" != "none" ]; then
  # Read status from ITEM.md if available
  ITEM_STATUS=$(grep -i "^Status:" "$WORK_DIR/items/$ACTIVE/ITEM.md" 2>/dev/null | sed 's/Status: *//')
  if [ -z "$ITEM_STATUS" ]; then
    ITEM_STATUS="unknown"
  fi
  CONTEXT="${CONTEXT}## Flow Instructions\nThis project uses Flow for workflow orchestration. On session start, briefly acknowledge: \"Flow: ${PROJECT_NAME}, active: ${ACTIVE} (${ITEM_STATUS}).\"\n- Read the active item's ITEM.md before doing work on it.\n- Follow the item lifecycle: Research -> Plan -> Execute -> Verify.\n- Invoke the Flow skill for lifecycle transitions (research, planning, verification).\n- Log all significant work to .work/log.md."
else
  CONTEXT="${CONTEXT}## Flow Instructions\nThis project uses Flow for workflow orchestration. On session start, briefly acknowledge: \"Flow: ${PROJECT_NAME}, no active item.\"\n- If user requests non-trivial work (multi-step implementation, research, feature), invoke the Flow skill to create a work item before starting.\n- For trivial tasks (single-line fix, quick question), proceed directly and log to .work/log.md.\n- Log all significant work to .work/log.md."
fi

# Output plain text — SessionStart hooks don't support hookSpecificOutput JSON
printf '%b' "$CONTEXT"
