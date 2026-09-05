#!/usr/bin/env bash
# Per-machine omnigent bootstrap. Idempotent. Run once per WORKSPACE machine
# (mac/vps) after dotagents install. Requires: uv. Recommends: python3.12+,
# node 22+/npm, tmux (and bwrap on Linux) for the claude/codex/pi harnesses.
#
# Workspaces only — NOT for remote Claude Code sessions (web / ephemeral
# containers). omnigent is a local agent runtime; remote sessions must have no
# footprint, so this no-ops when CLAUDE_CODE_REMOTE=true.
#
#   1. Install the `omnigent` CLI via `uv tool install` if not already on PATH.
#   2. Ensure ~/.omnigent/ (0700) and seed ~/.omnigent/config.yaml from
#      config.template.yaml ONLY if it's missing (omnigent owns the live file —
#      it rewrites host_id + providers at runtime, so we never overwrite it and
#      never symlink it into the repo).
#
# Never writes secrets or host_id. Idempotent; safe to re-run.
set -euo pipefail

# --- (0) Workspaces-only guard ---
if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ]; then
  echo "[omnigent-bootstrap] CLAUDE_CODE_REMOTE=true — omnigent is workspaces-only; skipping." >&2
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OMNIGENT_DIR="$HOME/.omnigent"
CONFIG_FILE="$OMNIGENT_DIR/config.yaml"
TEMPLATE="$SCRIPT_DIR/config.template.yaml"

# --- (1) omnigent CLI ---
if ! command -v uv >/dev/null 2>&1; then
  echo "[omnigent-bootstrap] uv not found — install from https://docs.astral.sh/uv/ first" >&2
  exit 1
fi

if ! command -v omnigent >/dev/null 2>&1; then
  echo "[omnigent-bootstrap] installing omnigent via uv..."
  uv tool install omnigent
else
  echo "[omnigent-bootstrap] omnigent already installed ($(command -v omnigent)) — not upgrading"
fi

# --- (2) Prereq report (warn, don't hard-fail; harnesses need these at run time) ---
check_prereq() {
  # $1 = command, $2 = human note
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[omnigent-bootstrap] missing: $1 — $2" >&2
  fi
}

if command -v python3.12 >/dev/null 2>&1; then
  :
elif command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 12) else 1)' 2>/dev/null; then
  :
else
  echo "[omnigent-bootstrap] missing: python 3.12+ — required by omnigent" >&2
fi

if command -v node >/dev/null 2>&1 && node -e 'process.exit(parseInt(process.versions.node) >= 22 ? 0 : 1)' 2>/dev/null; then
  :
else
  echo "[omnigent-bootstrap] missing: Node.js 22+ — needed for the claude/codex/pi harness CLIs" >&2
fi
check_prereq npm "needed alongside Node for the harness CLIs"
check_prereq tmux "needed by the native omnigent claude/codex wrappers"
if [ "$(uname -s)" = "Linux" ]; then
  check_prereq bwrap "Linux only — mandatory OS sandbox for harness terminals (apt install bubblewrap)"
fi

# --- (3) Seed config (never overwrite; omnigent owns the live file) ---
mkdir -p "$OMNIGENT_DIR"
chmod 0700 "$OMNIGENT_DIR"

if [ ! -f "$CONFIG_FILE" ]; then
  cp "$TEMPLATE" "$CONFIG_FILE"
  chmod 0600 "$CONFIG_FILE"
  echo "[omnigent-bootstrap] seeded $CONFIG_FILE from template"
else
  echo "[omnigent-bootstrap] $CONFIG_FILE exists — left untouched (omnigent owns it; may hold host_id/secrets)"
fi

# --- (4) Next steps ---
echo "[omnigent-bootstrap] done."
echo "[omnigent-bootstrap] next: run 'omnigent setup' to log in the claude/codex CLIs and populate keychain credentials."
echo "[omnigent-bootstrap] secrets stay machine-local (OS keychain / 'omnigent setup') and are never committed."
