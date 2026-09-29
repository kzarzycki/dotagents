#!/usr/bin/env bash
# Per-machine omnigent bootstrap. Idempotent. Run once per WORKSPACE machine
# (mac/vps) after dotagents install. Requires: uv. Recommends: python3.12+,
# node 22+/npm, tmux (and bwrap on Linux) for the claude/codex/pi harnesses.
#
# Workspaces only — NOT for remote Claude Code sessions (web / ephemeral
# containers). omnigent is a local agent runtime; remote sessions must have no
# footprint, so this no-ops when CLAUDE_CODE_REMOTE=true.
#
#   1. Install the `omnigent` CLI from the kzarzycki/omnigent fork (branch
#      `mine`, what the server runs) if not already on PATH.
#   2. Ensure ~/.omnigent/ (0700) and seed ~/.omnigent/config.yaml from
#      config.template.yaml ONLY if it's missing (omnigent owns the live file —
#      it rewrites host_id + providers at runtime, so we never overwrite it and
#      never symlink it into the repo).
#   3. With --server URL: install the host service (`omnigent host enable`).
#   4. Check the installed host service's PATH resolves claude and tmux.
#
# Never writes secrets or host_id. Idempotent; safe to re-run.
#
#   bootstrap.sh [--server https://<server>:6767]
set -euo pipefail

SERVER=""
while [ $# -gt 0 ]; do
  case "$1" in
    --server) SERVER="${2:?--server needs a URL}"; shift 2 ;;
    *) echo "usage: $0 [--server URL]" >&2; exit 2 ;;
  esac
done

# --- (0) Workspaces-only guard ---
if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ]; then
  echo "[omnigent-bootstrap] CLAUDE_CODE_REMOTE=true — omnigent is workspaces-only; skipping." >&2
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OMNIGENT_DIR="$HOME/.omnigent"
CONFIG_FILE="$OMNIGENT_DIR/config.yaml"
TEMPLATE="$SCRIPT_DIR/config.template.yaml"
# Git install: uv resolves the sibling omnigent-client/ui-sdk packages from the
# repo; the PyPI release cannot, as its ==dev pins are not published.
OMNIGENT_SOURCE="${OMNIGENT_SOURCE:-git+https://github.com/kzarzycki/omnigent@mine}"

# --- (0b) Use the login-shell PATH ---
# `omnigent host enable` bakes the CALLING process's PATH into the launchd plist
# / systemd unit. From ssh or a script that PATH lacks ~/.local/bin and
# Homebrew, and the host comes up online with no usable harness. Adopting the
# login shell's PATH makes every check below and the baked service PATH match
# what a terminal sees. A second macOS user shares /opt/homebrew but never ran
# `brew shellenv`, so add it to that user's login profile first.
if [ "$(uname -s)" = "Darwin" ] && [ -x /opt/homebrew/bin/brew ] \
    && ! grep -qs 'brew shellenv' "$HOME/.zprofile"; then
  echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> "$HOME/.zprofile"
  echo "[omnigent-bootstrap] added Homebrew to ~/.zprofile"
fi
LOGIN_PATH="$("${SHELL:-/bin/bash}" -lic 'echo "__PATH__=$PATH"' 2>/dev/null </dev/null \
  | sed -n 's/^__PATH__=//p' | tail -1 || true)"
[ -n "$LOGIN_PATH" ] && export PATH="$LOGIN_PATH"

# --- (1) omnigent CLI ---
if ! command -v uv >/dev/null 2>&1; then
  echo "[omnigent-bootstrap] uv not found — install from https://docs.astral.sh/uv/ first" >&2
  exit 1
fi

if ! command -v omnigent >/dev/null 2>&1; then
  echo "[omnigent-bootstrap] installing omnigent from $OMNIGENT_SOURCE..."
  uv tool install "omnigent @ $OMNIGENT_SOURCE"
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

# --- (3b) Updater, run daily by an Omnigent scheduled task ---
mkdir -p "$HOME/.local/bin"
install -m 0755 "$SCRIPT_DIR/update.sh" "$HOME/.local/bin/omnigent-update"
echo "[omnigent-bootstrap] installed ~/.local/bin/omnigent-update"

# --- (4) Host service ---
if [ -n "$SERVER" ]; then
  echo "[omnigent-bootstrap] enabling host service for $SERVER..."
  omnigent host enable --server "$SERVER" --non-interactive
fi

service_path() {
  case "$(uname -s)" in
    Darwin)
      local plist="$HOME/Library/LaunchAgents/ai.omnigent.host.plist"
      [ -f "$plist" ] && plutil -extract EnvironmentVariables.PATH raw "$plist" ;;
    Linux)
      local unit="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/omnigent-host.service"
      [ -f "$unit" ] && sed -n 's/^Environment="\{0,1\}PATH=\([^"]*\)"\{0,1\}$/\1/p' "$unit" ;;
  esac
}

SVC_PATH="$(service_path || true)"
if [ -n "$SVC_PATH" ]; then
  # tmux: native claude/codex terminals run in it. claude: the default harness.
  need="claude tmux"
  [ "$(uname -s)" = "Linux" ] && need="$need bwrap"
  missing=""
  for bin in $need; do
    PATH="$SVC_PATH" command -v "$bin" >/dev/null 2>&1 || missing="$missing $bin"
  done
  if [ -n "$missing" ]; then
    echo "[omnigent-bootstrap] host service PATH cannot find:$missing" >&2
    echo "[omnigent-bootstrap]   service PATH: $SVC_PATH" >&2
    echo "[omnigent-bootstrap]   fix: install them, then re-run with --server from a login shell" >&2
    exit 1
  fi
  echo "[omnigent-bootstrap] host service PATH resolves: $need"
elif [ -n "$SERVER" ]; then
  echo "[omnigent-bootstrap] host service file not found after enable" >&2
  exit 1
fi

# --- (5) Next steps ---
echo "[omnigent-bootstrap] done."
echo "[omnigent-bootstrap] next: run 'omnigent setup' to log in the claude/codex CLIs and populate keychain credentials."
echo "[omnigent-bootstrap] next: start 'claude' once in a terminal and clear every first-run prompt —"
echo "[omnigent-bootstrap]       a native session stalls on any dialog it cannot answer."
if [ "$(uname -s)" = "Darwin" ]; then
  echo "[omnigent-bootstrap] macOS: the service runs only while this user is logged in to the desktop"
  echo "[omnigent-bootstrap]       (switch users, don't log out); CLI logins live in its keychain."
fi
echo "[omnigent-bootstrap] secrets stay machine-local (OS keychain / 'omnigent setup') and are never committed."
