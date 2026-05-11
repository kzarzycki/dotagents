#!/usr/bin/env bash
# Idempotent overlay: adds a PreCompact subscription to the memsearch plugin.
#
# Safe to run repeatedly. Fast no-op when already patched (single grep).
# Intended to be wired into user-level SessionStart so plugin updates
# self-heal on next session. Remove this patch once upstream merges
# PreCompact support — at which point the grep guard will short-circuit
# against the upstream "PreCompact" entry and this becomes a true no-op.
set -euo pipefail

PATCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CACHE_BASE="$HOME/.claude/plugins/cache/memsearch-plugins/memsearch"

[ -d "$CACHE_BASE" ] || exit 0

shopt -s nullglob
APPLIED=0
for VERSION_DIR in "$CACHE_BASE"/*/; do
  HOOKS_DIR="${VERSION_DIR}hooks"
  HOOKS_JSON="$HOOKS_DIR/hooks.json"
  HOOK_SCRIPT="$HOOKS_DIR/pre-compact.sh"

  [ -f "$HOOKS_JSON" ] || continue

  if grep -q '"PreCompact"' "$HOOKS_JSON"; then
    continue
  fi

  cp "$PATCH_DIR/pre-compact.sh" "$HOOK_SCRIPT"
  chmod +x "$HOOK_SCRIPT"

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

  APPLIED=1
done

if [ "$APPLIED" -eq 1 ]; then
  printf '[memsearch-precompact-patch] applied to %s\n' "$CACHE_BASE"/*/ >&2
fi
