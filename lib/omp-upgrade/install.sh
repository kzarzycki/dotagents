#!/usr/bin/env bash
# Wire the audited-upgrade gate in front of the installed omp binary.
#
#   lib/omp-upgrade/install.sh [--adopt-release <version>] [--uninstall]
#
# With no arguments the omp already on PATH becomes the managed binary. Where
# that omp is not a release binary (a bun/npm install, say), --adopt-release
# <version> downloads that version's asset for this platform and verifies it
# against the SHA256 GitHub publishes. Adoption is the trust baseline, so adopt
# the version you already run and let the audit gate everything after it.
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
# The audit needs tomllib (3.11+), and the shim must keep working after a
# version manager moves on, so record the resolved real interpreter, not a shim.
pick_python() {
  local candidate resolved
  for candidate in ${PYTHON:-} python3.13 python3.12 python3.11 python3 /usr/bin/python3; do
    command -v "$candidate" >/dev/null 2>&1 || continue
    # tomllib for the audit, plus a populated CA store — a python.org framework
    # build without its certificate installer run fails every HTTPS fetch.
    resolved=$("$candidate" -c 'import ssl, sys, tomllib
assert ssl.create_default_context().cert_store_stats()["x509_ca"]
print(sys.executable)' 2>/dev/null) || continue
    [ -x "$resolved" ] && { printf '%s' "$resolved"; return 0; }
  done
  return 1
}
PY=$(pick_python) || { echo "need python 3.11+ (tomllib); set PYTHON=/path/to/python3" >&2; exit 1; }

ADOPT=""
case "${1:-}" in
  --adopt-release) ADOPT="${2:?--adopt-release needs a version, e.g. 18.0.0}" ;;
  --adopt-release=*) ADOPT="${1#--adopt-release=}" ;;
esac

if [ "${1:-}" = "--uninstall" ]; then
  [ -x "$LIB/omp-real" ] && mv "$LIB/omp-real" "$SHIM" || rm -f "$SHIM"
  rm -f "$LIB/launcher.py" "$LIB/audit.py"
  echo "omp-upgrade removed; state kept at $STATE"
  exit 0
fi

mkdir -p "$LIB" "$STATE" "$(dirname "$SHIM")"
chmod 700 "$LIB" "$STATE"
ln -sfn "$REPO_DIR/launcher.py" "$LIB/launcher.py"
ln -sfn "$REPO_DIR/audit.py" "$LIB/audit.py"

# Adopt a published release: download this platform's asset and check it against
# the digest in the release metadata before it is ever executed.
if [ -n "$ADOPT" ] && [ ! -e "$LIB/omp-real" ]; then
  "$PY" -I - "$LIB" "$STATE" "$ADOPT" <<'ADOPTPY'
import hashlib, pathlib, sys
lib, state, want = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
sys.path.insert(0, str(lib))
import audit
release = audit.release_identity(audit.api_json(f"/releases/tags/v{want}"))
print(f"downloading {release['asset_url']} ({release['size'] // 2**20} MiB)")
partial, digest, total = lib / "omp-real.partial", hashlib.sha256(), 0
with audit.open_public(release["asset_url"], asset=True) as source, open(partial, "wb") as sink:
    while chunk := source.read(1 << 20):
        total += len(chunk)
        audit.require(total <= release["size"], "Asset exceeds published size")
        digest.update(chunk)
        sink.write(chunk)
audit.require(total == release["size"] and digest.hexdigest() == release["sha256"],
              "Downloaded asset does not match the published size and SHA256")
partial.chmod(0o700)
partial.rename(lib / "omp-real")
audit.atomic_json(state / "installed.json",
                  {"version": release["version"], "commit": audit.tag_commit(release["version"]),
                   "sha256": release["sha256"]})
print(f"adopted verified omp {release['version']}")
ADOPTPY
fi

# First run without --adopt-release: adopt whatever omp is on PATH.
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
