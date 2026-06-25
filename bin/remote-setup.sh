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
# Delivery: dotagents is private, so the sandbox can only clone it with the
# scoped credential the harness wires for repos added to the environment. Add
# `kzarzycki/dotagents` (and `kzarzycki/agent-skills-private` for the private
# marketplaces) to the environment's repositories; the harness checks them out
# into the workspace, and this script finds and installs from that checkout.
# A plain `git clone https://github.com/...` of a *private* repo fails in the
# sandbox — the clone fallback below only succeeds if the repo is public.
#
# Setup script field (paste this):
#   bash "$(ls -d "$HOME"/*/dotagents/bin/remote-setup.sh /home/*/dotagents/bin/remote-setup.sh 2>/dev/null | head -1)"
#
# Override defaults via env: DOTAGENTS_PROFILE (default: remote),
# DOTAGENTS_REPO_URL (clone fallback target; only works if dotagents is public).
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
  # Arm pre-commit in repos the harness checked out BEFORE this setup ran (so
  # init.templateDir misses them). They land beside the dotagents checkout or
  # in the work dir. Best-effort: never fail container setup over it.
  "$SRC_REPO/bin/dotagents" arm-hooks --root "$(dirname "$SRC_REPO")" --root "$PWD" || true
else
  log "no checkout found — trying to clone $REPO_URL -> $DEST"
  log "(this only works if dotagents is public; if private, add it as an environment repo instead)"
  if git clone --depth 1 "$REPO_URL" "$DEST" 2>&1; then
    "$DEST/bin/dotagents" install --profile "$PROFILE" --no-pull
    "$DEST/bin/dotagents" arm-hooks --root "$(dirname "$DEST")" --root "$PWD" || true
  else
    log "ERROR: could not obtain dotagents. Add kzarzycki/dotagents to the environment's repositories, or make it public." >&2
    exit 1
  fi
fi

log "ready: ~/.claude/settings.json generated (profile: $PROFILE). Claude Code will install enabled plugins on session start."
