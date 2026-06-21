#!/usr/bin/env bash
# Live-dev linker for the `dev` directory marketplace.
#
# The dev marketplace (~/dev/.claude-plugin/marketplace.json) registers plugins
# from working trees under ~/dev via local "./repo/plugin" sources. For each such
# plugin that Claude has installed, this symlinks its cache install dir -> the
# working tree, so editing the plugin + /reload-plugins is enough (no re-copy,
# no GitHub push).
#
# Repo-agnostic: driven entirely by the marketplace's local sources. Add a plugin
# to ~/dev/.claude-plugin/marketplace.json (from ANY repo under ~/dev) and enable
# it (<name>@dev) in your Claude settings — it goes live on the next session, no
# edit here. Each plugin links to ITS OWN declared source, so same-named plugins
# from different repos never collide.
#
# Idempotent; safe on every SessionStart. Silent no-op when ~/dev or the
# marketplace/installed files are absent.
set -uo pipefail

DEV_ROOT="$HOME/dev"
MARKETFILE="$DEV_ROOT/.claude-plugin/marketplace.json"
INSTALLED="$HOME/.claude/plugins/installed_plugins.json"
TRACKED_MARKET="$HOME/.dotagents/patches/dev-marketplace/marketplace.json"

# Ensure the dev marketplace.json exists by symlinking the dotagents-tracked
# copy into ~/dev/.claude-plugin/. This is the reproducible source of truth —
# without it the file is a loose, machine-local single point of failure. Each
# machine resolves only the plugins whose source repos it actually has.
if [ -f "$TRACKED_MARKET" ]; then
  mkdir -p "$DEV_ROOT/.claude-plugin"
  if [ ! -L "$MARKETFILE" ] || [ "$(readlink "$MARKETFILE")" != "$TRACKED_MARKET" ]; then
    rm -f "$MARKETFILE"
    ln -s "$TRACKED_MARKET" "$MARKETFILE"
    echo "[dev-marketplace] linked marketplace.json -> $TRACKED_MARKET" >&2
  fi
fi

[ -f "$MARKETFILE" ] || exit 0
[ -f "$INSTALLED" ] || exit 0

# Emit "name<TAB>installPath<TAB>srcdir" for every dev plugin with a local source
# that Claude has actually installed (cache-backed). installPath is read verbatim
# — the version subdir is not guessable.
while IFS=$'\t' read -r name target srcdir; do
  [ -n "$target" ] && [ -n "$srcdir" ] || continue
  [ -f "$srcdir/.claude-plugin/plugin.json" ] || continue
  # Remove the stray self-referential symlink (<plugin>/<plugin> -> <plugin>)
  # that marketplace refreshes occasionally drop inside the working tree. Guarded
  # to a symlink pointing at its own parent — never touches a real dir.
  selflink="$srcdir/$(basename "$srcdir")"
  if [ -L "$selflink" ] && [ "$(readlink "$selflink")" = "$srcdir" ]; then
    rm -f "$selflink"
    echo "[dev-marketplace] removed stray self-link $selflink" >&2
  fi
  if [ -L "$target" ] && [ "$(readlink "$target")" = "$srcdir" ]; then
    continue  # already live
  fi
  mkdir -p "$(dirname "$target")"
  rm -rf "$target"
  ln -s "$srcdir" "$target"
  echo "[dev-marketplace] linked $name -> $srcdir" >&2
done < <(python3 - "$MARKETFILE" "$INSTALLED" "$DEV_ROOT" <<'PY'
import json, os, sys
marketfile, installed, dev_root = sys.argv[1], sys.argv[2], sys.argv[3]
market = json.load(open(marketfile))
plugins = json.load(open(installed)).get("plugins", {})
for p in market.get("plugins", []):
    name, src = p.get("name"), p.get("source")
    # local directory sources only ("./repo/plugin"); skip github/object sources
    if not name or not isinstance(src, str) or not src.startswith("./"):
        continue
    srcdir = os.path.normpath(os.path.join(dev_root, src))
    recs = plugins.get(f"{name}@dev")
    if not recs:
        continue  # not installed yet — Claude installs it on next launch
    installpath = recs[0].get("installPath", "")
    if "/plugins/cache/" in installpath:
        print(f"{name}\t{installpath}\t{srcdir}")
PY
)

exit 0
