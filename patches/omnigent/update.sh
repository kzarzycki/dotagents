#!/usr/bin/env bash
# Bring this workspace machine to the head of the kzarzycki/omnigent fork's
# `mine` branch. Run daily by an Omnigent scheduled task on each host; the
# fork itself is rebased onto upstream elsewhere (audit-sync on the work Mac).
#
#   host CLI  reinstalled from git when its commit differs from `mine`
#   server    only where ~/services/omnigent/compose.yaml exists: the deploy
#             checkout is reset to `mine` and the image rebuilt
#
# Nothing is touched while another session was active in the last 10 minutes
# on what a restart would kill (this host; for the server, every host): the
# script exits "deferred" and the next firing retries. The restart itself is
# scheduled 20s out, detached, so the session running this can report first.
#
#   omnigent-update           update if needed
#   omnigent-update --check   report only
set -euo pipefail

REPO_URL="${OMNIGENT_REPO_URL:-https://github.com/kzarzycki/omnigent}"
BRANCH="${OMNIGENT_BRANCH:-mine}"
SERVER_DIR="$HOME/services/omnigent"
CONFIG="$HOME/.omnigent/config.yaml"
CHECK=0; [ "${1:-}" = "--check" ] && CHECK=1

log() { echo "[omnigent-update] $*"; }
die() { log "ERROR: $*" >&2; exit 1; }

server_url=$(sed -n 's/^server: *//p' "$CONFIG" | tail -1)
host_id=$(sed -n 's/^  host_id: *//p' "$CONFIG" | tail -1)
[ -n "$server_url" ] && [ -n "$host_id" ] || die "no server/host_id in $CONFIG"

# Exit 0 when a session other than the caller's was active in the last 10
# minutes (on host $1, or anywhere when $1 is empty). Fails closed: an
# unreachable server or missing token counts as busy.
busy() {
  python3 - "$server_url" "$1" "${OMNIGENT_RUNNER_PRIMARY_SESSION_ID:-}" <<'PY'
import json, os, sys, time, urllib.request
url, host, me = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3]
try:
    tokens = json.load(open(os.path.expanduser("~/.omnigent/auth_tokens.json")))
    req = urllib.request.Request(f"{url}/v1/sessions?limit=1000",
        headers={"Authorization": f"Bearer {tokens[url]['token']}"})
    sessions = json.load(urllib.request.urlopen(req, timeout=10))["data"]
except Exception as exc:
    print(f"cannot list sessions ({exc.__class__.__name__}) — treating as busy")
    sys.exit(0)
now = time.time()
active = [s["title"] or s["id"] for s in sessions
          if s["id"] != me and (not host or s.get("host_id") == host)
          and now - (s.get("updated_at") or 0) < 600]
if active:
    print(f"{len(active)} active: {', '.join(active[:5])}")
sys.exit(0 if active else 1)
PY
}

head=$(git ls-remote "$REPO_URL" "refs/heads/$BRANCH" | cut -f1)
[ -n "$head" ] || die "cannot read $BRANCH from $REPO_URL"

if [ -f "$SERVER_DIR/compose.yaml" ]; then
  # Server machine: the host runs from the deploy checkout's .venv, so the
  # checkout's commit is what both the server image and the host run.
  src="$SERVER_DIR/source"
  git -C "$src" fetch -q origin "$BRANCH"
  current=$(git -C "$src" rev-parse HEAD)
  log "server+host at ${current:0:9}, $BRANCH at ${head:0:9}"
  [ "$current" = "$head" ] && { log "up to date"; exit 0; }
  [ "$CHECK" = 1 ] && { log "update available"; exit 0; }
  [ -z "$(git -C "$src" status --porcelain --untracked-files=no)" ] \
    || die "$src has uncommitted changes — commit them into $BRANCH first"
  # Never reset away a commit that exists nowhere else: every commit must be
  # on some origin branch (normally mine; a pushed backup branch also counts).
  git -C "$src" fetch -q origin
  local_only=$(git -C "$src" rev-list --count HEAD --not --remotes=origin)
  [ "$local_only" = 0 ] \
    || die "$src has $local_only commit(s) on no origin branch — land them in $BRANCH first"
  if busy ""; then log "deferred — sessions active; next firing retries"; exit 0; fi
  git -C "$src" checkout -q "$BRANCH"
  git -C "$src" reset -q --hard "origin/$BRANCH"
  (cd "$src" && uv sync -q --frozen && uv tool install -q --force --python 3.12 .)
  (cd "$SERVER_DIR" && docker compose build -q omnigent)
  systemd-run --user -q --on-active=20 --unit="omnigent-update-restart-$(date +%s)" \
    sh -c "cd '$SERVER_DIR' && docker compose up -d omnigent && systemctl --user restart omnigent-host"
  log "updated to ${head:0:9}; server and host restart in 20s"
  exit 0
fi

# Host-only machine: the CLI is a uv tool installed from git.
current=$(omnigent --version | sed -n 's/.*(\([0-9a-f]*\),.*/\1/p')
log "host at ${current:-unknown}, $BRANCH at ${head:0:9}"
case "$head" in "$current"?*) log "up to date"; exit 0 ;; esac
[ "$CHECK" = 1 ] && { log "update available"; exit 0; }
if busy "$host_id"; then log "deferred — sessions active on this host; next firing retries"; exit 0; fi
uv tool install -q --reinstall "omnigent @ git+$REPO_URL@$BRANCH"
case "$(uname -s)" in
  Darwin) restart="launchctl kickstart -k gui/$(id -u)/ai.omnigent.host" ;;
  *)      restart="systemctl --user restart omnigent-host" ;;
esac
nohup sh -c "sleep 20; $restart" >/dev/null 2>&1 &
log "updated to ${head:0:9}; host restarts in 20s"
