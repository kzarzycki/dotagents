#!/usr/bin/env bash
# Idempotent overlay for memsearch:
#   1. Subscribe the plugin to PreCompact (capture pre-compaction transcript)
#   2. Wrap markdown writes in stop.sh + session-start.sh with flock
#      (parallel sessions can interleave appends to the daily-log file)
#   3. Wrap pre-compact.sh writes with flock (baked into our overlay copy)
#   4. Patch MilvusStore.upsert in the memsearch venv to call flush()
#      after upsert (upstream bug zilliztech/memsearch#534 — writes are not
#      durable on remote Milvus 2.5+ without an explicit flush)
#
# Each step is gated by an idempotency check, so safe to run on every
# SessionStart. Fast no-op (~10ms) when everything is in place.
#
# Remove individual patches once upstream lands them.
set -euo pipefail

PATCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ============================================================================
# Plugin cache patches
# ============================================================================
CACHE_BASE="$HOME/.claude/plugins/cache/memsearch-plugins/memsearch"
if [ -d "$CACHE_BASE" ]; then
  shopt -s nullglob
  for VERSION_DIR in "$CACHE_BASE"/*/; do
    HOOKS_DIR="${VERSION_DIR}hooks"
    HOOKS_JSON="$HOOKS_DIR/hooks.json"
    STOP_SH="$HOOKS_DIR/stop.sh"
    SESSION_START_SH="$HOOKS_DIR/session-start.sh"
    PRECOMPACT_SH="$HOOKS_DIR/pre-compact.sh"

    [ -f "$HOOKS_JSON" ] || continue

    # --- (1) PreCompact subscription in hooks.json ---
    if ! grep -q '"PreCompact"' "$HOOKS_JSON"; then
      python3 - "$HOOKS_JSON" <<'PY'
import json, sys
path = sys.argv[1]
with open(path) as f:
    data = json.load(f)
hooks = data.setdefault("hooks", {})
hooks["PreCompact"] = [{
    "hooks": [{
        "type": "command",
        "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/pre-compact.sh",
        "async": True,
        "timeout": 120,
    }]
}]
desired = ["SessionStart", "UserPromptSubmit", "Stop", "PreCompact", "SessionEnd"]
ordered = {k: hooks[k] for k in desired if k in hooks}
for k, v in hooks.items():
    ordered.setdefault(k, v)
data["hooks"] = ordered
with open(path, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY
      echo "[memsearch-overlay] added PreCompact subscription to $HOOKS_JSON" >&2
    fi

    # --- (2) Refresh pre-compact.sh from overlay (always; idempotent if bytes match) ---
    cp "$PATCH_DIR/pre-compact.sh" "$PRECOMPACT_SH"
    chmod +x "$PRECOMPACT_SH"

    # --- (3) Wrap stop.sh's MEMORY_FILE write in flock ---
    if [ -f "$STOP_SH" ] && ! grep -q 'flock' "$STOP_SH"; then
      python3 - "$STOP_SH" <<'PY'
import sys
path = sys.argv[1]
with open(path) as f:
    lines = f.read().split('\n')
out, i, patched = [], 0, False
while i < len(lines):
    line = lines[i]
    if line.rstrip() == '{' and not patched:
        j = i + 1
        while j < len(lines):
            if lines[j].rstrip() == '} >> "$MEMORY_FILE"':
                out.append('(')
                out.append('  flock -x 200')
                for k in range(i, j + 1):
                    out.append('  ' + lines[k])
                out.append(') 200>"$MEMORY_DIR/.write.lock"')
                i = j + 1
                patched = True
                break
            j += 1
        else:
            out.append(line); i += 1
        continue
    out.append(line); i += 1
if patched:
    with open(path, 'w') as f:
        f.write('\n'.join(out))
PY
      if grep -q 'flock' "$STOP_SH"; then
        echo "[memsearch-overlay] flock-wrapped $STOP_SH" >&2
      fi
    fi

    # --- (4) Wrap session-start.sh's heading echo in flock ---
    if [ -f "$SESSION_START_SH" ] && ! grep -q 'flock' "$SESSION_START_SH"; then
      python3 - "$SESSION_START_SH" <<'PY'
import sys
path = sys.argv[1]
with open(path) as f:
    src = f.read()
old = '  echo -e "\\n## Session $NOW\\n" >> "$MEMORY_FILE"'
new = '''  (
    flock -x 200
    echo -e "\\n## Session $NOW\\n" >> "$MEMORY_FILE"
  ) 200>"$MEMORY_DIR/.write.lock"'''
if old in src:
    with open(path, 'w') as f:
        f.write(src.replace(old, new))
PY
      if grep -q 'flock' "$SESSION_START_SH"; then
        echo "[memsearch-overlay] flock-wrapped $SESSION_START_SH" >&2
      fi
    fi
  done
fi

# ============================================================================
# Memsearch Python package patches (uv tool install)
# ============================================================================
# Bug zilliztech/memsearch#534: MilvusStore.upsert() on remote Milvus 2.5+
# reports success but does not flush, so search returns 0 rows until next flush.
for STORE_PY in "$HOME/.local/share/uv/tools/memsearch/lib"/python*/site-packages/memsearch/store.py; do
  [ -f "$STORE_PY" ] || continue
  if ! grep -q 'self._client.flush(self._collection)' "$STORE_PY"; then
    python3 - "$STORE_PY" <<'PY'
import sys
path = sys.argv[1]
with open(path) as f:
    src = f.read()
old = '''        result = self._client.upsert(
            collection_name=self._collection,
            data=chunks,
        )
        return result.get'''
new = '''        result = self._client.upsert(
            collection_name=self._collection,
            data=chunks,
        )
        self._client.flush(self._collection)
        return result.get'''
if old in src:
    with open(path, 'w') as f:
        f.write(src.replace(old, new))
PY
    if grep -q 'self._client.flush(self._collection)' "$STORE_PY"; then
      echo "[memsearch-overlay] flush-patched $STORE_PY (bug #534)" >&2
    fi
  fi
done

# ============================================================================
# Milvus standalone compose: generate per-machine .env
# ============================================================================
# docker compose runs may be invoked with sudo, which clobbers $HOME. Resolve
# the host data dir from this script's invocation context (always user-level
# via SessionStart hook) and bake it into a gitignored .env beside the compose.
STANDALONE_DIR="$PATCH_DIR/standalone"
if [ -d "$STANDALONE_DIR" ]; then
  ENV_FILE="$STANDALONE_DIR/.env"
  DESIRED="MEMSEARCH_DATA_DIR=$HOME/.memsearch/standalone/volumes"
  if [ ! -f "$ENV_FILE" ] || ! grep -qxF "$DESIRED" "$ENV_FILE"; then
    echo "$DESIRED" > "$ENV_FILE"
    mkdir -p "$HOME/.memsearch/standalone/volumes/etcd" "$HOME/.memsearch/standalone/volumes/milvus"
    echo "[memsearch-overlay] wrote $ENV_FILE" >&2
  fi
fi
