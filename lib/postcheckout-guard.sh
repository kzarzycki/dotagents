#!/usr/bin/env bash
# dotagents-postcheckout-guard v1
# Deployed by `dotagents arm-hooks` into the global git template dir as
# hooks/post-checkout, replacing pre-commit's generated one. Two differences:
#   (1) Opt-in only. pre-commit runs every hook WITHOUT `stages:` at every hook
#       type installed, so a template-wide post-checkout makes each clone of any
#       pre-commit repo install its linter envs — including clones tools make
#       for you (SwiftPM, submodules). Delegate only when the repo's config
#       names post-checkout itself (a hook's `stages:` or
#       `default_install_hook_types`).
#   (2) Never fails the checkout. git turns a post-checkout exit status into the
#       checkout's status, although the checkout already happened; a failing
#       hook only breaks the tool that ran git. Warn and exit 0.
# Deliberately no `set -e`.

cfg=.pre-commit-config.yaml
[ -f "$cfg" ] || exit 0
grep -Eq '(^|[^[:alnum:]_-])post-checkout([^[:alnum:]_-]|$)' "$cfg" || exit 0
command -v pre-commit >/dev/null 2>&1 || {
  echo "WARN: $cfg wants post-checkout hooks but pre-commit is not on PATH; skipped" >&2
  exit 0
}
HERE="$(cd "$(dirname "$0")" && pwd)"
pre-commit hook-impl --config="$cfg" --hook-type=post-checkout --hook-dir "$HERE" -- "$@" ||
  echo "WARN: post-checkout hooks failed (exit $?); checkout itself is fine" >&2
exit 0
