#!/usr/bin/env bash
# remote-setup.sh — bootstrap dotagents inside a Claude Code on the web
# (cloud / remote) container so every session comes up fully configured:
# user-scope ~/.claude/settings.json (plugins, marketplaces, hooks, statusline,
# env) is generated, and Claude Code auto-installs the enabled plugins at
# session start.
#
# Idempotent and non-interactive — intended as the environment "Setup script".
# Container state is cached after it runs, so subsequent sessions are instant.
#
# Usage (paste ONE of these into the environment's Setup script field):
#
#   # A) dotagents added as a workspace source repo (no external egress needed
#   #    for the repo itself; preferred under a GitHub-scoped network policy):
#   bash "$(ls -d "$HOME"/*/dotagents/bin/remote-setup.sh /home/*/dotagents/bin/remote-setup.sh 2>/dev/null | head -1)"
#
#   # B) fetch + run directly (needs raw.githubusercontent.com egress):
#   curl -fsSL https://raw.githubusercontent.com/kzarzycki/dotagents/main/bin/remote-setup.sh | bash
#
# Override defaults via env: DOTAGENTS_PROFILE (default: remote),
# DOTAGENTS_REPO_URL (default: the public GitHub repo).
set -euo pipefail

REPO_URL="${DOTAGENTS_REPO_URL:-https://github.com/kzarzycki/dotagents}"
PROFILE="${DOTAGENTS_PROFILE:-remote}"
DEST="$HOME/.dotagents"

log() { printf '[dotagents-remote] %s\n' "$*" >&2; }

# The install script needs jq to generate settings.json. Best-effort install;
# in most CC containers jq is already present.
if ! command -v jq >/dev/null 2>&1; then
  log "jq missing — attempting install"
  if command -v apt-get >/dev/null 2>&1; then
    (sudo apt-get update -qq && sudo apt-get install -y -qq jq) 2>/dev/null \
      || apt-get install -y -qq jq 2>/dev/null \
      || log "could not install jq automatically — settings generation may fail"
  fi
fi

# Find an existing dotagents checkout before cloning. When dotagents is added
# as a workspace source repo the harness clones it via its own git proxy, so we
# avoid needing external egress for the repo. Candidates cover the canonical
# install path and common workspace roots.
find_checkout() {
  local self_dir c
  # 1. This script's own repo (run from a checkout, not piped).
  self_dir="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
  if [ -n "$self_dir" ] && [ -f "$self_dir/dotagents" ] && [ -d "$self_dir/../home" ]; then
    (cd "$self_dir/.." && pwd); return 0
  fi
  # 2. Canonical path + common workspace locations.
  for c in "$DEST" /home/*/dotagents "$HOME"/*/dotagents "$PWD/dotagents" "$PWD/../dotagents"; do
    if [ -f "$c/bin/dotagents" ] && [ -d "$c/home" ]; then
      (cd "$c" && pwd); return 0
    fi
  done
  return 1
}

if SRC_REPO="$(find_checkout)"; then
  log "using checkout at $SRC_REPO"
  # If it's a git clone we control at the canonical path, fast-forward it.
  if [ "$SRC_REPO" = "$DEST" ] && [ -d "$DEST/.git" ]; then
    git -C "$DEST" pull --ff-only 2>/dev/null || log "pull skipped (offline or non-ff)"
  fi
  "$SRC_REPO/bin/dotagents" install --profile "$PROFILE" --no-pull
else
  log "no checkout found — cloning $REPO_URL -> $DEST"
  git clone --depth 1 "$REPO_URL" "$DEST"
  "$DEST/bin/dotagents" install --profile "$PROFILE" --no-pull
fi

log "ready: ~/.claude/settings.json generated (profile: $PROFILE). Claude Code will install enabled plugins on session start."
