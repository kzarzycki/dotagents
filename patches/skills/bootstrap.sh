#!/usr/bin/env bash
# Per-machine user-global skills. Idempotent. Run once per machine after
# dotagents install. Requires: node/npx.
#
# dotagents does NOT vendor skill files into its home/ payload (see the install
# skip-list + the test forbidding home/.claude/skills) -- capability stays with
# its source repo. This bootstrap is the sanctioned cross-machine path for the
# handful of *user-global* skills that should follow you everywhere, installed
# from their source repos via the `skills` CLI so `skills update` keeps working.
#
#   herdr               -- control the Herdr multiplexer (upstream: herdrdev/herdr)
#   orchestrating-agents-- Herdr vs SendMessage vs tmux decision guide
#                          (first-party: kzarzycki/agent-skills, experimental pack)
#
# Project skills still come from each project's APM manifest, not here.
set -euo pipefail

if ! command -v npx >/dev/null 2>&1; then
  echo "[skills-bootstrap] npx not found -- install Node.js first" >&2
  exit 1
fi

echo "[skills-bootstrap] installing user-global skills..."

# One unavailable skill must not abort the rest: `skills add` exits non-zero when
# a --skill name is missing upstream (unmerged, renamed, moved), and under set -e
# that would skip every later install. Warn and continue instead.
add() {
  npx --yes skills add "$@" -g -y ||
    echo "[skills-bootstrap] WARN: skipped 'skills add $*' -- not available upstream" >&2
}

add herdrdev/herdr --skill herdr
add kzarzycki/agent-skills --skill orchestrating-agents --full-depth

echo "[skills-bootstrap] done. Installed global skills:"
npx --yes skills list -g 2>/dev/null || true
