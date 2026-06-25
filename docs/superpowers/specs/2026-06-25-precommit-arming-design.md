# Deterministic pre-commit arming across environments

## Problem

The pre-commit *framework* (each repo's `.pre-commit-config.yaml` — ruff-format,
gitleaks, etc.) only enforces on commit if that repo's `.git/hooks/pre-commit`
has been installed. Installation is local, per-clone, never committed. So
formatting/lint failures that the hook would catch instead surface at CI — the
late, annoying place. This was hit directly: a ruff-format-only failure on
omnigent PR #1153 that local `pytest` never saw.

dotagents already arms its *own* repo hook (`.githooks` via `core.hooksPath`,
section 1.5 of `bin/dotagents`), but nothing arms the pre-commit framework for
other repos. `init.templateDir` was set manually, but it only covers repos
cloned *after* it's set — it misses repos a container harness checks out
*before* setup runs.

## Goal

One dotagents-managed primitive that arms pre-commit framework hooks locally in
every environment — personal machines, Claude Code on the web, remote-agent
containers, and future runtimes dotagents will support — so a bad commit fails
locally (fail-then-correct) before reaching CI. It must **never override a
repo's own hooks**.

Non-goals: replacing CI enforcement (CI stays the backstop); adding
behavioral instructions to AGENTS.md (hooks enforce, instructions only hope);
arming repos on machines dotagents doesn't manage.

## Approach

Per-repo `pre-commit install` (native `.git/hooks`), never global
`core.hooksPath`. This is the only model that is both clone-timing-proof and
preserves each repo's own hooks. Rejected alternatives:

- **Global `core.hooksPath` → shared dispatcher.** One setting arms everything
  instantly, but replaces each repo's `.git/hooks` wholesale, bypassing any
  repo's own / multi-stage (`commit-msg`, `pre-push`) hooks. Violates the
  no-override requirement.
- **Per-runtime targeted install, no shared primitive.** Each runtime
  re-implements targeting and misses repos it doesn't know about. Doesn't scale
  to the planned new runtimes.

## The primitive

A single idempotent routine, exposed as a subcommand: **`dotagents arm-hooks
[--root PATH]...`** (`--root` repeatable; default `~/dev`). It does three
things:

1. **Ensure `pre-commit` is present.** If not on PATH, `uv tool install
   pre-commit`. Best-effort: if it can't be installed, print a warning and
   skip — never hard-fail the bootstrap. CI remains the backstop.
2. **Future clones.** Set global `init.templateDir = ~/.config/git/template`
   and `pre-commit init-templatedir` there. Any repo cloned/init'd afterward
   auto-arms. (Folds in the `init.templateDir` setup currently inline in
   section 1.6 of `bin/dotagents`.)
3. **Existing-repo sweep.** For each `--root`, find git repos containing a
   `.pre-commit-config.yaml` (depth-limited, ~maxdepth 4, to stay fast and
   avoid `node_modules`/large trees) and run `pre-commit install` in each.
   Catches repos cloned *before* setup — the container gap.

`pre-commit install` honors each repo's `default_install_hook_types`, so
`commit-msg`/`pre-push`/multi-stage hooks are installed too — installed, never
overridden.

## Wiring

- `dotagents install` calls `arm-hooks` with the default `~/dev` root
  (machines). Replaces the inline section-1.6 block.
- `remote-setup.sh` calls `arm-hooks --root <its workspace checkout path>`
  after `install` — each runtime contributes the path *it* knows (containers
  drop repos "wherever the harness decides", not necessarily `~/dev`).
- Future runtimes call `dotagents arm-hooks --root <their path>` directly,
  without running a full `install`.

## Safety / boundaries

- Never sets global `core.hooksPath`. Per-repo `pre-commit install` only.
- dotagents' own repo keeps its local `core.hooksPath=.githooks` (section 1.5),
  untouched; it has no `.pre-commit-config.yaml` so the sweep skips it.
- Best-effort everywhere: a constrained runtime that can't install pre-commit
  gets a warning and continues; CI backstops.
- Idempotent: re-running `install`/`arm-hooks` when already armed is a no-op
  (guards on existing `init.templateDir` value and on already-installed repo
  hooks).
- Dry-run: respects the existing `run`/`DRY_RUN` wrapper in `bin/dotagents`.

## Cold-start

`pre-commit install` is instant (writes the hook script). The first
`pre-commit run` in a fresh container builds hook environments (tens of
seconds). Default is **lazy** — do not pre-warm during setup, keep setup fast,
the first commit pays the cost once. Optional `--install-hooks` flag pre-warms
(`pre-commit install --install-hooks`) for a runtime that prefers it.

## Success criteria

1. **Machine:** after `dotagents install`, a misformatted commit in a repo with
   a `.pre-commit-config.yaml` is blocked, files are rewritten by the hook, and
   a re-commit succeeds.
2. **Container:** after `remote-setup.sh`, an already-checked-out work repo has
   a firing `.git/hooks/pre-commit`.
3. **No override:** a repo with its own `commit-msg` hook still runs it after
   arming.
4. **Idempotent:** a second `install`/`arm-hooks` makes no changes.
5. **Best-effort:** with `pre-commit` uninstallable, setup completes with a
   warning rather than failing.

## Testing

dotagents is bash with no test framework, so keep it minimal and in-style:

- `bash -n bin/dotagents` + `shellcheck bin/dotagents` clean.
- One scripted smoke check: create a throwaway git repo with a trivial
  `.pre-commit-config.yaml`, run `dotagents arm-hooks --root <tmp>`, assert
  `.git/hooks/pre-commit` exists, assert a violating commit fails and a clean
  one passes. No framework, no fixtures.
