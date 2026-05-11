#!/usr/bin/env bash
# Claude Code status line script
# Displays: project ██░░░░░░░░ 28% | model | last prompt
# Bar color: green <50%, yellow 50-75%, red >75%

input=$(cat)

# ANSI colors
GREEN=$'\033[32m'
YELLOW=$'\033[33m'
RED=$'\033[31m'
DIM=$'\033[2m'
RESET=$'\033[0m'

# --- Project name (current dir) ---
project_dir=$(echo "$input" | jq -r '.workspace.project_dir // .cwd // empty')
if [ -n "$project_dir" ]; then
  project=$(basename "$project_dir")
else
  project="~"
fi

# --- Context window progress bar ---
used_pct=$(echo "$input" | jq -r '.context_window.used_percentage // empty')

BAR_LEN=10
if [ -n "$used_pct" ]; then
  used_int=$(printf "%.0f" "$used_pct")

  # Pick color based on usage
  if [ "$used_int" -lt 50 ]; then
    COLOR="$GREEN"
  elif [ "$used_int" -lt 75 ]; then
    COLOR="$YELLOW"
  else
    COLOR="$RED"
  fi

  filled=$(( (used_int * BAR_LEN + 50) / 100 ))
  [ "$filled" -gt "$BAR_LEN" ] && filled=$BAR_LEN
  empty=$(( BAR_LEN - filled ))

  filled_bar=""
  empty_bar=""
  for ((i=0; i<filled; i++)); do filled_bar+="█"; done
  for ((i=0; i<empty; i++)); do empty_bar+="░"; done

  context_str="${COLOR}${filled_bar}${DIM}${empty_bar}${RESET} ${COLOR}${used_int}%${RESET}"
else
  empty_bar=""
  for ((i=0; i<BAR_LEN; i++)); do empty_bar+="░"; done
  context_str="${DIM}${empty_bar} --%${RESET}"
fi

# --- Model ---
model=$(echo "$input" | jq -r '.model.display_name // .model.id // "?"')

# --- Last prompt snippet ---
# Transcript is JSONL. User prompts are type:"user" with .message.content as a string.
transcript=$(echo "$input" | jq -r '.transcript_path // empty')
last_prompt=""
if [ -n "$transcript" ] && [ -f "$transcript" ]; then
  last_prompt=$(grep '"type":"user"' "$transcript" | jq -r 'select(.message.content | type == "string") | .message.content' 2>/dev/null | tail -1)
fi

if [ -n "$last_prompt" ]; then
  # Collapse whitespace and truncate
  last_prompt=$(echo "$last_prompt" | tr '\n' ' ' | sed 's/  */ /g')
  if [ "${#last_prompt}" -gt 40 ]; then
    last_prompt="${last_prompt:0:40}..."
  fi
  prompt_str="${DIM}${last_prompt}${RESET}"
else
  prompt_str=""
fi

# --- Orchestrator mode indicator ---
ORCH=""
if [ -n "$project_dir" ] && [ -f "$project_dir/.claude/orchestrator-mode" ]; then
  ORCH="${YELLOW}[ORCH]${RESET} "
fi

# --- Assemble status line ---
line="${ORCH}${project} ${context_str} ${DIM}|${RESET} ${model}"
if [ -n "$prompt_str" ]; then
  line="${line} ${DIM}|${RESET} ${prompt_str}"
fi
printf "%s" "$line"
