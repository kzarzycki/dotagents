#!/usr/bin/env bash
# Per-machine pixelrag bootstrap. Idempotent. Run once per machine after
# dotagents install. Requires: uv.
#
# Installs the `pixelshot` binary that the pixelbrowse@pixelrag-plugins skill
# shells out to, into an isolated uv tool env (not the README's global
# `pip install pixelrag`, which pollutes the system Python).
#
# Browser: pixelshot's default cdp backend launches its own headless browser
# from $CHROME_PATH. Its bundled auto-download is linux-x64 only, so on macOS
# env.sh points CHROME_PATH at an installed Brave/Chrome; on linux-x64 it
# self-provisions on first run. The `playwright` backend is not wired (the
# playwright python pkg isn't a pixelrag dependency), so no browser download here.
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  echo "[pixelrag-bootstrap] uv not found — install from https://docs.astral.sh/uv/ first" >&2
  exit 1
fi

if ! uv tool list 2>/dev/null | grep -q '^pixelrag '; then
  echo "[pixelrag-bootstrap] installing pixelrag via uv..."
  uv tool install pixelrag
else
  echo "[pixelrag-bootstrap] pixelrag already installed via uv"
fi

echo "[pixelrag-bootstrap] done. pixelshot: $(command -v pixelshot 2>/dev/null || echo 'not on PATH — check ~/.local/bin')"
if [ "$(uname -s)" = "Darwin" ] && [ -z "${CHROME_PATH:-}" ]; then
  echo "[pixelrag-bootstrap] note: macOS needs CHROME_PATH set (env.sh handles this; open a new shell)." >&2
fi
