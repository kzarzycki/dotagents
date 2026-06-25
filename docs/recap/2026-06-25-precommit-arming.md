# Recap: deterministic pre-commit arming (`arm-hooks`)

Spec: [`docs/superpowers/specs/2026-06-25-precommit-arming-design.md`](../superpowers/specs/2026-06-25-precommit-arming-design.md).
Commits: `64cea47` (spec) → `10f3872` (primitive) → `8c102a6` (every-repo sweep) → `6ff790e` (guard).

Delta from the spec — what the design didn't pre-record:

## Divergences / decisions made during implementation

- **Plain `pre-commit install` → committed guard.** The spec's first cut armed
  only the pre-commit framework. That stays silent when a repo ships
  husky/`.githooks` that aren't active — the exact "forgot to run setup" gap.
  Replaced with `lib/precommit-guard.sh` deployed verbatim into each repo's
  `.git/hooks/pre-commit` + the git template. The guard blocks commits past
  inactive maintainer hooks, then delegates to the framework. (Spec rewritten to
  match.)
- **Sweep widened to every git repo**, not just ones with a config today — so a
  config added later runs without a re-sweep. Gated on maintainer-safe skips.
- **Idempotency is by content (`cmp -s`), not presence.** Lets a stale older
  guard self-update on re-run while a current guard is a true no-op. Foreign
  hooks (neither our guard nor pre-commit-generated) are detected by marker grep
  and left strictly alone.
- **Dropped the hardcoded `INSTALL_PYTHON` path** that pre-commit's generated
  hook bakes in — the guard uses `command -v pre-commit` only, so it's portable
  across machines/containers where that path differs.

## Live findings

- Re-armed ~25 repos under `~/dev`; second run = 0 changes (idempotent confirmed).
- dotagents' own repo correctly skipped (it uses `core.hooksPath=.githooks`, no
  `.pre-commit-config.yaml`).
- omnigent clone now carries the guard — the ruff-format failure that reached CI
  on omnigent PR #1153 (the trigger for this whole effort) now fails locally.
- 12/12 assertions in `scratchpad/smoke-guard.sh` pass.

## Deferred / not done

- No CI/automated run of the smoke test — it's a throwaway script, run by hand.
- Container path (`remote-setup.sh` → `arm-hooks --root`) is wired but only
  exercised on real machines, not yet validated in an actual CC-web container.
