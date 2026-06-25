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

Never forget — me or an agent — to run the git hooks a repo's maintainers set
up (the pre-commit framework, or a shipped husky/`.githooks` dir). One
dotagents-managed primitive arms hooks locally in every environment — personal
machines, Claude Code on the web, remote-agent containers, and future runtimes
dotagents will support — so a commit that skips a repo's hooks **fails locally**
(fail-then-correct) before reaching CI. It must **never override a repo's own
hooks**.

Non-goals: replacing CI enforcement (CI stays the backstop); adding
behavioral instructions to AGENTS.md (hooks enforce, instructions only hope);
arming repos on machines dotagents doesn't manage.

## Approach

A single committed guard hook — `lib/precommit-guard.sh` — deployed verbatim
into each repo's native `.git/hooks/pre-commit` (and the global git template),
never via global `core.hooksPath`. The guard does two jobs at commit time:

1. **Block commits past shipped-but-inactive maintainer hooks.** If the repo
   ships a `.husky` or `.githooks` dir but `core.hooksPath` is unset (their hook
   mechanism isn't wired up in this clone), the commit is **blocked** with how
   to fix it (`npm install`, `git config core.hooksPath …`, or `--no-verify` to
   bypass once). This is the "never forget" guarantee — for me and for agents.
2. **Delegate to the pre-commit framework.** If `.pre-commit-config.yaml` is
   present, `exec pre-commit hook-impl …`, exactly as pre-commit's own generated
   hook would. No-ops when there's no config, so a config *added later* runs
   automatically without a re-sweep.

The guard is self-contained (git + pre-commit on PATH only), so it copies as-is
into containers. Rejected alternatives:

- **Global `core.hooksPath` → shared dispatcher.** One setting arms everything
  instantly, but replaces each repo's `.git/hooks` wholesale, bypassing any
  repo's own / multi-stage (`commit-msg`, `pre-push`) hooks. Violates the
  no-override requirement.
- **Plain `pre-commit install` only.** Arms the framework but stays silent when
  a repo ships husky/`.githooks` that aren't active — exactly the "forgot to run
  setup" gap we're closing.
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
2. **Future clones.** Set global `init.templateDir = ~/.config/git/template`,
   run `pre-commit init-templatedir` there, then overlay the guard onto the
   template's `hooks/pre-commit`. Any repo cloned/init'd afterward auto-arms.
3. **Existing-repo sweep.** For each `--root`, find *every* git repo
   (depth-limited, ~maxdepth 5, pruning `node_modules`/`.venv`) and deploy the
   guard — not only repos with a `.pre-commit-config.yaml` today. For repos that
   do have a config, run `pre-commit install` first (to wire up the *other* hook
   types — `commit-msg`/`pre-push` per `default_install_hook_types`), then copy
   the guard over `.git/hooks/pre-commit` so the pre-commit stage runs through
   the guard. Catches repos cloned *before* setup (the container gap) and makes
   "add a config later" work without a re-sweep.

   The sweep never touches a maintainer's own hook setup:
   - **Skip repos with `core.hooksPath` set** (husky, tracked `.githooks`, …) —
     git bypasses `.git/hooks` there, so their setup already runs; the guard
     would be dead. (The guard *itself* nudges to wire this up where it isn't.)
   - **Leave a foreign `.git/hooks/pre-commit` strictly alone** — a hook that is
     neither our guard nor a pre-commit-generated one is someone's own setup;
     never clobbered, never chained via `.legacy`.
   - **Idempotent by content:** a repo already carrying the current guard
     (`cmp -s`) is skipped; an older guard or a plain pre-commit-generated hook
     is safely replaced with the current guard.

## Wiring

- `dotagents install` calls `arm-hooks` with the default `~/dev` root
  (machines). Replaces the inline section-1.6 block.
- `remote-setup.sh` calls `arm-hooks --root <its workspace checkout path>`
  after `install` — each runtime contributes the path *it* knows (containers
  drop repos "wherever the harness decides", not necessarily `~/dev`).
- Future runtimes call `dotagents arm-hooks --root <their path>` directly,
  without running a full `install`.

## Safety / boundaries

- Never sets global `core.hooksPath`. Per-repo native `.git/hooks` only.
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
2. **Never-forget:** a repo shipping `.husky`/`.githooks` with `core.hooksPath`
   unset blocks the commit with how-to-fix; `--no-verify` bypasses once.
3. **Container:** after `remote-setup.sh`, an already-checked-out work repo has
   a firing `.git/hooks/pre-commit`.
4. **Add config later:** a repo with no config at sweep time still gets the
   guard; adding a config afterward runs it on the next commit.
5. **Maintainer-safe:** a repo using `core.hooksPath` is skipped (its setup
   untouched, not blocked); a foreign `.git/hooks/pre-commit` is left intact
   (no clobber, no `.legacy` chaining).
6. **Idempotent / self-updating:** a second `arm-hooks` makes no changes when
   the current guard is present; a stale older guard is replaced.
7. **Best-effort:** with `pre-commit` uninstallable, setup completes with a
   warning rather than failing.

## Testing

dotagents is bash with no test framework, so keep it minimal and in-style:

- `bash -n bin/dotagents` + `shellcheck bin/dotagents lib/precommit-guard.sh` clean.
- One scripted smoke check (`scratchpad/smoke-guard.sh`, 12 assertions) over
  throwaway repos init'd with an empty template to isolate from git templating:
  plain repo armed + commits; inactive husky/`.githooks` blocked (with message
  and `--no-verify` bypass); `core.hooksPath` repo skipped; foreign hook
  untouched; pre-commit framework still enforced through the guard; idempotent;
  stale guard self-updates. No framework, no fixtures.
