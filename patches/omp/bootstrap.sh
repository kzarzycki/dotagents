#!/usr/bin/env bash
# Per-machine OMP plugin bootstrap. Idempotent. Run after dotagents install.
# Requires: omp and jq.
set -euo pipefail

PLUGIN='@czottmann/pi-automode'
# kzarzycki/pi-automode branch `kz`: upstream main + selected PRs.
# See docs/knowledge/omp.md "pi-automode fork".
SOURCE='github:kzarzycki/pi-automode#6c96a2199976991199bd591d9aa2c585aa1261e8'
MANIFEST="$HOME/.omp/plugins/package.json"

if ! command -v omp >/dev/null 2>&1; then
  echo "[omp-bootstrap] omp not found -- install OMP first" >&2
  exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "[omp-bootstrap] jq not found -- install jq first" >&2
  exit 1
fi

installed_source="$(jq -r --arg name "$PLUGIN" '.dependencies[$name] // empty' "$MANIFEST" 2>/dev/null || true)"
if [ "$installed_source" = "$SOURCE" ] && omp plugin list --json 2>/dev/null | jq -e --arg name "$PLUGIN" \
  '.npm[]? | select(.name == $name and .enabled == true)' >/dev/null; then
  echo "[omp-bootstrap] $PLUGIN from $SOURCE already installed and enabled"
else
  echo "[omp-bootstrap] installing $PLUGIN from $SOURCE"
  omp plugin install "$SOURCE"
fi

echo "[omp-bootstrap] done"
