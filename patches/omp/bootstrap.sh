#!/usr/bin/env bash
# Per-machine OMP plugin bootstrap. Idempotent. Run after dotagents install.
# Requires: omp and jq.
set -euo pipefail

PLUGIN='@czottmann/pi-automode'
VERSION='1.15.0'

if ! command -v omp >/dev/null 2>&1; then
  echo "[omp-bootstrap] omp not found -- install OMP first" >&2
  exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "[omp-bootstrap] jq not found -- install jq first" >&2
  exit 1
fi

if omp plugin list --json 2>/dev/null | jq -e --arg name "$PLUGIN" --arg version "$VERSION" \
  '.npm[]? | select(.name == $name and .version == $version and .enabled == true)' >/dev/null; then
  echo "[omp-bootstrap] $PLUGIN@$VERSION already installed and enabled"
else
  echo "[omp-bootstrap] installing $PLUGIN@$VERSION"
  omp plugin install "$PLUGIN@$VERSION"
fi

echo "[omp-bootstrap] done"
