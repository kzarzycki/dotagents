#!/usr/bin/env bash
# Wire the audited-upgrade gate in front of the installed omp binary.
#
#   lib/omp-upgrade/install.sh [--uninstall]
#
# Idempotent. The launcher and audit scripts are symlinked out of this repo, so
# `git pull` updates them. Machine-local state stays out of the repo:
#   ~/.local/lib/omp-upgrade/omp-real   the real binary (moved here on first run)
#   ~/.local/state/omp-upgrade/         manifest, audit report, upstream mirror
#   ~/.local/bin/omp                    shim that execs the launcher
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$HOME/.local/lib/omp-upgrade"
STATE="$HOME/.local/state/omp-upgrade"
SHIM="$HOME/.local/bin/omp"
PY=${PYTHON:-/usr/bin/python3}

if [ "${1:-}" = "--uninstall" ]; then
  [ -x "$LIB/omp-real" ] && mv "$LIB/omp-real" "$SHIM" || rm -f "$SHIM"
  rm -f "$LIB/launcher.py" "$LIB/audit.py"
  echo "omp-upgrade removed; state kept at $STATE"
  exit 0
fi

command -v "$PY" >/dev/null || { echo "need python3 at $PY (override with PYTHON=)" >&2; exit 1; }

mkdir -p "$LIB" "$STATE" "$(dirname "$SHIM")"
chmod 700 "$LIB" "$STATE"
ln -sfn "$REPO_DIR/launcher.py" "$LIB/launcher.py"
ln -sfn "$REPO_DIR/audit.py" "$LIB/audit.py"

# First run: adopt whatever omp is currently on PATH as the managed binary.
if [ ! -e "$LIB/omp-real" ]; then
  current=$(command -v omp || true)
  [ -n "$current" ] || { echo "no omp on PATH to adopt; install omp first" >&2; exit 1; }
  current=$(cd "$(dirname "$current")" && pwd)/$(basename "$current")
  [ "$current" = "$SHIM" ] && { echo "$SHIM is the shim but $LIB/omp-real is missing — restore the binary first" >&2; exit 1; }
  cp "$current" "$LIB/omp-real"
  chmod 700 "$LIB/omp-real"
  echo "adopted $current -> $LIB/omp-real"
fi

printf '#!/bin/sh\nexec %s -I %s/launcher.py "$@"\n' "$PY" "$LIB" > "$SHIM"
chmod 755 "$SHIM"

# Bootstrap the identity the audit diffs against: installed version, its source
# tag commit, and the binary's digest. Only written when absent — never on top
# of a manifest the launcher maintains.
"$PY" -I - "$LIB" "$STATE" <<'PY'
import hashlib, json, pathlib, subprocess, sys
lib, state = map(pathlib.Path, sys.argv[1:3])
target = state / "installed.json"
if target.exists():
    print(f"manifest present: {json.loads(target.read_text())['version']}")
    raise SystemExit(0)
sys.path.insert(0, str(lib))
import audit
raw = subprocess.run([str(lib / "omp-real"), "--version"], capture_output=True, text=True, timeout=60).stdout
version = raw.strip().split("/")[-1]
digest = hashlib.sha256((lib / "omp-real").read_bytes()).hexdigest()
manifest = {"version": version, "commit": audit.tag_commit(version), "sha256": digest}
audit.atomic_json(target, manifest)
print(f"bootstrapped manifest for omp {version}")
PY

echo "omp-upgrade installed. Try: omp --upgrade-status"
