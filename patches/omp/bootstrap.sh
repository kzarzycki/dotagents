#!/usr/bin/env bash
# Per-machine OMP plugin bootstrap. Idempotent. Run after dotagents install.
# Requires: omp and jq.
set -euo pipefail

PLUGIN='@czottmann/pi-automode'
SOURCE='github:kzarzycki/pi-automode#5a2e5a90d95ad8a9a6f26e7f0e6fce5c042e46aa'

if ! command -v omp >/dev/null 2>&1; then
  echo "[omp-bootstrap] omp not found -- install OMP first" >&2
  exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "[omp-bootstrap] jq not found -- install jq first" >&2
  exit 1
fi

plugin="$(omp plugin list --json | jq -c --arg name "$PLUGIN" '.npm[]? | select(.name == $name)')"
installed_path="$(jq -r '.path // empty' <<<"$plugin")"
manifest="${installed_path%%/node_modules/*}/package.json"
current="$(jq -r --arg name "$PLUGIN" '.dependencies[$name] // empty' "$manifest" 2>/dev/null || true)"
enabled="$(jq -r '.enabled // false' <<<"$plugin")"

if [ "$current" = "$SOURCE" ]; then
  if [ "$enabled" = true ]; then
    echo "[omp-bootstrap] $SOURCE already installed and enabled"
  else
    omp plugin enable "$PLUGIN"
  fi
else
  if [ -n "$installed_path" ]; then
    omp plugin uninstall "$PLUGIN"
  fi
  if omp plugin install "$SOURCE"; then
    :
  else
    rc=$?
    echo "[omp-bootstrap] install failed; restoring previous plugin" >&2
    if [ -n "$current" ]; then
      if omp plugin list --json | jq -e --arg name "$PLUGIN" \
        '.npm[]? | select(.name == $name)' >/dev/null; then
        omp plugin uninstall "$PLUGIN"
      fi
      if omp plugin install "$current"; then
        if [ "$enabled" = false ]; then
          omp plugin disable "$PLUGIN"
        fi
      else
        echo "[omp-bootstrap] restore failed: $current" >&2
      fi
    fi
    exit "$rc"
  fi
fi

echo "[omp-bootstrap] done"
