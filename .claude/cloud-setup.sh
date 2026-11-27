#!/bin/bash
# Setup script of the dotagents Claude cloud environment: it installs mise and the tools mise.toml pins, so
# `mise run check` (the repo's gate) runs in a cloud session (#216), and the gh-quota shim. A failed step is logged as FAILED in
# /tmp/cloud-setup.log (its output in /tmp/cloud-setup.log.out) and the script still exits 0,
# since a non-zero exit fails the whole cloud session.
set -u
log=${CLOUD_SETUP_LOG:-/tmp/cloud-setup.log}
export PATH="$HOME/.local/bin:$PATH"
t0=$(date +%s)
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
# The proxy refuses mise.run, mise-versions.jdx.dev and api.github.com for other repos, but github.com's release
# downloads pass, so each tool is a release asset checked against its release's checksum list, laid out where mise
# looks for an install. With mise preferring offline, a tool there counts as installed and `mise run` puts it on PATH.
# fetch <url> <checksum-list url> <dest> [strip]: a .tar.gz unpacked into <dest> less <strip> leading path parts.
fetch() {
  local a="${1##*/}" d; a=${a//%2B/+}; d=$(mktemp -d)  # %2B: a "+" in a release asset's URL
  curl -fsSL -o "$d/$a" "$1" && curl -fsSL -o "$d/sums" "$2" \
    && (cd "$d" && awk -v a="$a" '$2 == a || $2 == "*" a || $2 == "./" a' sums | sha256sum -c -) || return 1
  mkdir -p "$3" && tar -xzf "$d/$a" -C "$3" --strip-components="${4:-0}"
}
# ponytail: x86_64 Linux assets only, the cloud image's platform; the versions below move with a new pin
gh=${CLOUD_SETUP_RELEASES:-https://github.com}
repo=${CLOUD_SETUP_REPO:-/home/user/dotagents}
mise_v=v2026.11.14 uv_v=0.13.10 py_v=3.14.10 pbs=20261124 gl_v=8.30.1 pc_v=4.7.0
pc_sum=393488513aed286d7a5a978a1fe79b2f5a8802927242a2d241ff10c1a8e8c885
apm_v=$(sed -n 's/^"github:microsoft\/apm" *= *"\(.*\)"/\1/p' "$repo/mise.toml" 2>/dev/null)
command -v mise >/dev/null || { a=$gh/jdx/mise/releases/download/$mise_v
  step mise fetch "$a/mise-$mise_v-linux-x64.tar.gz" "$a/SHASUMS256.txt" "$HOME/.local" 1; }
cd "$repo" 2>/dev/null || { echo "FAILED: no checkout at $repo" >> "$log"; exit 0; }
step mise-trust mise trust -q --all
# global config, so every later mise call in the session, the gate's `mise run` included, uses it
step mise-offline mise settings set prefer_offline true
mi="$HOME/.local/share/mise/installs"
a=$gh/astral-sh/uv/releases/download/$uv_v/uv-x86_64-unknown-linux-gnu.tar.gz
step uv fetch "$a" "$a.sha256" "$HOME/.local/bin" 1
a=$gh/microsoft/apm/releases/download/v$apm_v/apm-linux-x86_64.tar.gz
step apm fetch "$a" "$a.sha256" "$mi/github-microsoft-apm/$apm_v" 1
a=$gh/astral-sh/python-build-standalone/releases/download/$pbs
step python fetch "$a/cpython-$py_v%2B$pbs-x86_64-unknown-linux-gnu-install_only.tar.gz" "$a/SHA256SUMS" "$mi/python/$py_v" 1
# uv is not a mise pin: mise runs pipx:pytest through the uv on PATH
# gitleaks and pre-commit: `mise run` installs every pin first, so the gate needs them too. mise names their install
# dirs by the pin (gitleaks/8, pre-commit/4). pre-commit ships a zipapp with no checksum list, so its sum is pinned here.
a=$gh/gitleaks/gitleaks/releases/download/v$gl_v
step gitleaks fetch "$a/gitleaks_${gl_v}_linux_x64.tar.gz" "$a/gitleaks_${gl_v}_checksums.txt" "$mi/gitleaks/8"
pre_commit() {
  local f="$mi/pre-commit/4/pre-commit"
  mkdir -p "${f%/*}" && curl -fsSL -o "$f" "$gh/pre-commit/pre-commit/releases/download/v$pc_v/pre-commit-$pc_v.pyz" \
    && echo "$pc_sum  $f" | sha256sum -c - && chmod 755 "$f"
}
step pre-commit pre_commit
step mise-install mise install
missing=""
for tool in python apm pytest; do mise which "$tool" >/dev/null 2>&1 || missing="$missing $tool"; done
command -v uv >/dev/null || missing="$missing uv"
[ -z "$missing" ] || echo "FAILED, missing:$missing" >> "$log"
echo "setup done $(date -u +%FT%TZ), $(( $(date +%s) - t0 )) s total" >> "$log"
exit 0
