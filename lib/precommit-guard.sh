#!/usr/bin/env bash
# dotagents-hook-guard v1
# Deployed verbatim by `dotagents arm-hooks` into each repo's
# .git/hooks/pre-commit and into the global git template dir, so neither you nor
# an agent can commit past:
#   (1) maintainer hooks the repo SHIPS but that are NOT active in this clone
#       (husky/.husky or a tracked .githooks, before the repo's setup has run) —
#       the commit is BLOCKED with how-to-fix. Bypass once with --no-verify.
#   (2) the pre-commit framework (.pre-commit-config.yaml), delegated below
#       exactly as pre-commit's own generated hook would.
# Self-contained: copied as-is, depends only on git + (for pre-commit repos)
# pre-commit on PATH. Deliberately no `set -e` — a hook must exit on its own
# terms, not abort on an unchecked subshell.

# (1) Shipped-but-inactive maintainer hooks. Only meaningful when core.hooksPath
# is unset: with it set, git runs THAT dir and this hook would not execute, so a
# present-but-inactive dir means the repo's own hook mechanism is not wired up.
if [ -z "$(git config --get core.hooksPath 2>/dev/null || true)" ]; then
  for _d in .husky .githooks; do
    if [ -d "$_d" ] && [ -n "$(ls -A "$_d" 2>/dev/null)" ]; then
      {
        echo "commit blocked by dotagents hook-guard:"
        echo "  ./$_d ships git hooks that are NOT active in this clone."
        echo "  run the repo's setup first, e.g.:"
        echo "    npm install                       # husky"
        echo "    git config core.hooksPath $_d     # plain tracked hooks dir"
        echo "  (or the repo's documented bootstrap), then retry."
        echo "  to bypass once: git commit --no-verify"
      } >&2
      exit 1
    fi
  done
fi

# (2) pre-commit framework delegation (mirrors pre-commit's generated hook).
# Not when pre-commit's own hook is the one that called us: `pre-commit install`
# over this guard parks it as pre-commit.legacy and runs it with
# PRE_COMMIT_RUNNING_LEGACY=1 before its own delegation; delegating again from
# here would recurse and pre-commit aborts the commit ("installed in migration
# mode"). Section (1) has run; the framework is pre-commit's job in that case.
if [ -f .pre-commit-config.yaml ] && [ -z "${PRE_COMMIT_RUNNING_LEGACY:-}" ]; then
  ARGS=(hook-impl --config=.pre-commit-config.yaml --hook-type=pre-commit)
  HERE="$(cd "$(dirname "$0")" && pwd)"
  ARGS+=(--hook-dir "$HERE" -- "$@")
  if command -v pre-commit >/dev/null 2>&1; then
    exec pre-commit "${ARGS[@]}"
  fi
  echo "WARN: .pre-commit-config.yaml present but pre-commit not on PATH; commit not checked" >&2
fi
exit 0
