# Loop facts

The `engineering-loop` skill reads this file at every step but the gate.

## Settings

```yaml
loop:
  ci: false

risk:
  verifier: true
```

## Owner

`kzarzycki`

## Proof on a branch

Run from the branch, never against the real `$HOME`:

- Install: `HOME=$(mktemp -d) bin/dotagents install --no-pull`, then check the expected files land at the right `~/`-paths.
- Git hooks: `HOME=$(mktemp -d) bin/dotagents arm-hooks --root <dir>`, then clone or commit through the sandbox template.
- Everything else: `mise run check:all`.

## Acceptance references

1. The real tools' behaviour (git, bash, zsh, Claude Code, Codex, pre-commit) in a sandbox `HOME`.
2. The tools' own documentation.

## Approvals

Only people approve. There is no spec policy, so every spec waits for the owner. There
is no CI, so the merge proof is `approvals.py local-ci`: a recorded run of
`mise run check:all` on the PR head. `risk.verifier: true` lets the verifier decide what is
high risk: a pass on the head whose `Risk:` line says anything but `low` holds the merge for
the owner's `approved:merge`, and so does a `risk:high` label.

## In use

Only the owner and their agents, on their Macs and a Linux VPS, each running
`bin/dotagents install` from a checkout. A finding is judged by what a machine running
install, or an agent shell it configures, hits. The repo is public: nothing on GitHub
names a host, a path or a session. There is deliberately no `docs/agents/issue-tracker.md`,
since its label checks would need labels this repo doesn't use; this paragraph holds its
Never on GitHub rule.

## Worktree

`git worktree add ../dotagents-worktrees/<branch> -b <branch> origin/main`, then in it
`mise trust` and `mise run setup:dev`, which installs the gitignored skills the loop's
tasks call. Remove it with `git worktree remove`.

## Ledger

`docs/agents/limitations.md`

## Verifier checklist

- Run install and `arm-hooks` only in a sandbox `HOME`.
