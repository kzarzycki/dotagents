#!/usr/bin/env bash
# Per-session refresh of the dotagents checkout, for Claude Code on the web.
#
# The cloud setup script that runs `dotagents install` is cached: it re-runs
# only when the environment is edited or the ~7-day snapshot expires, and never
# on resume. Without this hook, edits pushed to dotagents (AGENTS.md, slash
# commands, preloaded skill lists, statusline) wouldn't reach a running
# container until a rebuild. A fast `git pull --ff-only` here keeps the
# symlinked content live — those files resolve through the repo, so a pull is
# enough.
#
# Deliberately does NOT re-run `dotagents install`: the generated
# ~/.claude/settings.json was already read at launch, and plugin / settings
# changes don't hot-load mid-session (they need a container rebuild) — so
# regenerating it would be churn with no effect.
#
# Remote-only and fail-safe: silent no-op off-cloud, when the checkout is
# absent, or on any git error (offline, non-fast-forward, detached HEAD).
set -uo pipefail

[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0

DOTAGENTS="$HOME/.dotagents"
[ -d "$DOTAGENTS/.git" ] || exit 0

git -C "$DOTAGENTS" pull --ff-only --quiet 2>/dev/null || true
