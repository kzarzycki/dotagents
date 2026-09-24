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

if jq -e --arg name "$PLUGIN" --arg source "$SOURCE" \
  '.dependencies[$name] == $source' "$HOME/.omp/plugins/package.json" >/dev/null 2>&1 &&
  omp plugin list --json | jq -e --arg name "$PLUGIN" \
    '.npm[]? | select(.name == $name and .enabled == true)' >/dev/null; then
  echo "[omp-bootstrap] $SOURCE already installed and enabled"
else
  if omp plugin list --json | jq -e --arg name "$PLUGIN" \
    '.npm[]? | select(.name == $name)' >/dev/null; then
    omp plugin uninstall "$PLUGIN"
  fi
  omp plugin install "$SOURCE"
fi

echo "[omp-bootstrap] done"
