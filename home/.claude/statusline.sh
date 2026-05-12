#!/usr/bin/env bash
# Claude Code status line — full dashboard
# ~/.claude/statusline.sh

input=$(cat)

# ── ANSI helpers ─────────────────────────────────────────────────────────────
RESET='\033[0m'
BOLD='\033[1m'
DIM='\033[2m'
RED='\033[31m'
GREEN='\033[32m'
YELLOW='\033[33m'
CYAN='\033[36m'
MAGENTA='\033[35m'

# ── Parse JSON fields ─────────────────────────────────────────────────────────
model=$(echo "$input" | jq -r '.model.display_name // "unknown"')
session_id=$(echo "$input" | jq -r '.session_id // ""')
cwd=$(echo "$input" | jq -r '.workspace.current_dir // .cwd // ""')
used_pct=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
total_in=$(echo "$input" | jq -r '.context_window.total_input_tokens // 0')
total_out=$(echo "$input" | jq -r '.context_window.total_output_tokens // 0')
ctx_size=$(echo "$input" | jq -r '.context_window.context_window_size // 0')
vim_mode=$(echo "$input" | jq -r '.vim.mode // empty')
agent_name=$(echo "$input" | jq -r '.agent.name // empty')
worktree_name=$(echo "$input" | jq -r '.worktree.name // empty')
worktree_branch=$(echo "$input" | jq -r '.worktree.branch // empty')
five_pct=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
five_reset=$(echo "$input" | jq -r '.rate_limits.five_hour.resets_at // empty')
week_pct=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty')
week_reset=$(echo "$input" | jq -r '.rate_limits.seven_day.resets_at // empty')
version=$(echo "$input" | jq -r '.version // ""')
session_name=$(echo "$input" | jq -r '.session_name // empty')
transcript=$(echo "$input" | jq -r '.transcript_path // empty')

# ── Derived values ────────────────────────────────────────────────────────────

# Short session ID (first 8 chars)
short_id=""
[ -n "$session_id" ] && short_id="${session_id:0:8}"

# Current dir basename
dir_base=""
[ -n "$cwd" ] && dir_base=$(basename "$cwd")

# Git branch (skip optional locks)
git_branch=""
[ -n "$cwd" ] && git_branch=$(git -C "$cwd" --no-optional-locks rev-parse --abbrev-ref HEAD 2>/dev/null)

# Context bar (20 chars wide)
bar="" bar_color="$GREEN"
if [ -n "$used_pct" ]; then
  pct_int=$(printf "%.0f" "$used_pct")
  filled=$(( pct_int * 20 / 100 ))
  [ $filled -gt 20 ] && filled=20
  empty=$(( 20 - filled ))
  bar=$(python3 -c "print('\u2588'*$filled+'\u2591'*$empty,end='')")
  [ "$pct_int" -ge 80 ] && bar_color="$RED"
  [ "$pct_int" -ge 60 ] && [ "$pct_int" -lt 80 ] && bar_color="$YELLOW"
fi

# Session duration from transcript birth time vs now
duration_str=""
if [ -n "$transcript" ] && [ -f "$transcript" ]; then
  mtime=$(stat -f "%B" "$transcript" 2>/dev/null)
  now=$(date +%s)
  if [ -n "$mtime" ] && [ "$mtime" -gt 0 ] 2>/dev/null; then
    elapsed=$(( now - mtime ))
    h=$(( elapsed / 3600 ))
    m=$(( (elapsed % 3600) / 60 ))
    if [ $h -gt 0 ]; then
      duration_str=$(printf "%dh%02dm" $h $m)
    else
      duration_str=$(printf "%dm%02ds" $m $(( elapsed % 60 )))
    fi
  fi
fi

# Lines added/removed (git diff HEAD)
lines_added=0 lines_removed=0 show_diff=0
if [ -n "$cwd" ]; then
  diff_stat=$(git -C "$cwd" --no-optional-locks diff --numstat HEAD 2>/dev/null)
  if [ -n "$diff_stat" ]; then
    lines_added=$(echo "$diff_stat" | awk '{a+=$1} END{print a+0}')
    lines_removed=$(echo "$diff_stat" | awk '{r+=$2} END{print r+0}')
    ( [ "$lines_added" -gt 0 ] || [ "$lines_removed" -gt 0 ] ) && show_diff=1
  fi
fi

# Token counts in k
tok_in_k=$(python3 -c "print(f'{$total_in/1000:.0f}')" 2>/dev/null)
tok_out_k=$(python3 -c "print(f'{$total_out/1000:.0f}')" 2>/dev/null)
ctx_k=$(python3 -c "print(f'{$ctx_size/1000:.0f}')" 2>/dev/null)

# Rate limit reset as human duration
format_reset() {
  local reset_ts="$1" now diff
  now=$(date +%s)
  diff=$(( reset_ts - now ))
  if [ $diff -le 0 ]; then echo "soon"
  elif [ $diff -lt 3600 ]; then printf "%dm" $(( diff / 60 ))
  else printf "%dh%02dm" $(( diff / 3600 )) $(( (diff % 3600) / 60 ))
  fi
}

# ── LINE 1: Model | dir | git | diff | vim | agent | worktree ────────────────
line1=$(printf "${CYAN}${BOLD}%s${RESET}" "$model")
[ -n "$version" ] && line1+=$(printf " ${DIM}v%s${RESET}" "$version")
line1+=$(printf "  ${DIM}│${RESET}  ${BOLD}%s${RESET}" "$dir_base")
[ -n "$git_branch" ] && [ "$git_branch" != "HEAD" ] && \
  line1+=$(printf "  ${MAGENTA} %s${RESET}" "$git_branch")
[ "$show_diff" -eq 1 ] && \
  line1+=$(printf "  ${GREEN}+%s${RESET}${RED}-%s${RESET}" "$lines_added" "$lines_removed")
if [ -n "$vim_mode" ]; then
  [ "$vim_mode" = "INSERT" ] && line1+=$(printf "  ${GREEN}[INSERT]${RESET}") \
                             || line1+=$(printf "  ${YELLOW}[NORMAL]${RESET}")
fi
[ -n "$agent_name" ] && line1+=$(printf "  ${CYAN}agent:%s${RESET}" "$agent_name")
if [ -n "$worktree_name" ]; then
  wt_label="$worktree_name"
  [ -n "$worktree_branch" ] && wt_label="$worktree_name ($worktree_branch)"
  line1+=$(printf "  ${MAGENTA}wt:%s${RESET}" "$wt_label")
fi
[ -n "$session_name" ] && line1+=$(printf "  ${DIM}\"%s\"${RESET}" "$session_name")

# ── LINE 2: Context bar | cost | duration | session ID ───────────────────────
line2=""
if [ -n "$used_pct" ]; then
  pct_display=$(printf "%.0f" "$used_pct")
  line2=$(printf "ctx ${bar_color}%s${RESET} ${bar_color}%3s%%${RESET}" "$bar" "$pct_display")
  line2+=$(printf " ${DIM}(%sk in · %sk out · %sk win)${RESET}" "$tok_in_k" "$tok_out_k" "$ctx_k")
fi
[ -n "$duration_str" ] && line2+=$(printf "  ${DIM}│${RESET}  ${DIM}%s${RESET}" "$duration_str")
[ -n "$short_id" ] && line2+=$(printf "  ${DIM}│${RESET}  ${DIM}id:%s${RESET}" "$short_id")

# ── LINE 3: Rate limits (only when present) ───────────────────────────────────
line3=""
if [ -n "$five_pct" ] || [ -n "$week_pct" ]; then
  line3=$(printf "${DIM}limits  ${RESET}")
  if [ -n "$five_pct" ]; then
    five_int=$(printf "%.0f" "$five_pct")
    rl_c="$GREEN"; [ "$five_int" -ge 80 ] && rl_c="$RED"; [ "$five_int" -ge 60 ] && [ "$five_int" -lt 80 ] && rl_c="$YELLOW"
    rl_reset=""; [ -n "$five_reset" ] && rl_reset=" resets $(format_reset "$five_reset")"
    line3+=$(printf "${rl_c}5h: %s%%${RESET}${DIM}%s${RESET}" "$five_int" "$rl_reset")
  fi
  [ -n "$five_pct" ] && [ -n "$week_pct" ] && line3+=$(printf "  ${DIM}│${RESET}  ")
  if [ -n "$week_pct" ]; then
    week_int=$(printf "%.0f" "$week_pct")
    rl_c="$GREEN"; [ "$week_int" -ge 80 ] && rl_c="$RED"; [ "$week_int" -ge 60 ] && [ "$week_int" -lt 80 ] && rl_c="$YELLOW"
    rl_reset=""; [ -n "$week_reset" ] && rl_reset=" resets $(format_reset "$week_reset")"
    line3+=$(printf "${rl_c}7d: %s%%${RESET}${DIM}%s${RESET}" "$week_int" "$rl_reset")
  fi
fi

# ── Output ────────────────────────────────────────────────────────────────────
printf "%b\n" "$line1"
printf "%b\n" "$line2"
[ -n "$line3" ] && printf "%b\n" "$line3"
