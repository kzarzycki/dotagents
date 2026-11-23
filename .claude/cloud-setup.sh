#!/bin/bash
# Setup script of the dotagents Claude cloud environment. A failed step is logged as FAILED in
# /tmp/cloud-setup.log (its output in /tmp/cloud-setup.log.out) and the script still exits 0,
# since a non-zero exit fails the whole cloud session.
set -u
log=${CLOUD_SETUP_LOG:-/tmp/cloud-setup.log}
export PATH="$HOME/.local/bin:$PATH"
step() {  # step <name> <command...>: run it, log its seconds and exit code
  local s=$(date +%s); "${@:2}" >>"$log.out" 2>&1; local rc=$?
  echo "$1: exit $rc, $(( $(date +%s) - s )) s" >> "$log"
  [ "$rc" = 0 ] || echo "FAILED: $1" >> "$log"
}
# gh-quota's logging shim (github/skills/gh-quota) ahead of the image's gh, so every later session logs its gh calls
# by caller with no step of its own: the skill's two files from the public pack at a pinned commit (the github-v0.1.1
# release; move the commit and both sums with a new one), checked against their sums and kept in ~/.local/share/gh-quota,
# where `gh_quota.py counts` runs, then `install` copies the shim to ~/.local/bin, which a session's PATH puts ahead
# of /usr/local/bin's gh. $HOME is in the environment's snapshot, as mise's installs are.
ghq=c08d02c488c50fc5aa6dce31b59471e7cb41a6ae
ghq_src=${CLOUD_SETUP_GH_QUOTA:-https://raw.githubusercontent.com/kzarzycki/agent-skills/$ghq/github/skills/gh-quota/scripts}
gh_quota() {
  local d="$HOME/.local/share/gh-quota" t f; t=$(mktemp -d)
  for f in gh gh_quota.py; do curl -fsSL -o "$t/$f" "$ghq_src/$f" || return 1; done
  (cd "$t" && sha256sum -c -) <<'SUMS' || return 1
31c9eeae51cf1fc772ccdea078384e6219d2d67f608e86d771a7de8130ff2a65  gh
2f2b0d4b5adb627ef3087765e76cbe411cd19ffdb6e099a76dd8af2d8ae16417  gh_quota.py
SUMS
  mkdir -p "$d" && cp "$t/gh" "$t/gh_quota.py" "$d/" && python3 "$d/gh_quota.py" install
}
step gh-quota gh_quota
exit 0
