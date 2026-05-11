# dotagents

A git repo holding the canonical configuration for any CLI agent the user runs (Claude Code today; Codex, pi, others later). One source of truth, one install command, identical state across every machine.

## Layout

```
dotagents/
├── README.md
├── AGENTS.md           ← meta: instructions for agents working on THIS repo
├── bin/
│   └── dotagents       ← the install command
└── home/               ← install payload; 1:1 mirror of ~/
    ├── .agents/
    │   ├── AGENTS.md   ← canonical user behavioral spec
    │   ├── .skill-lock.json
    │   └── skills/     ← agent-neutral skill content
    └── .claude/
        ├── CLAUDE.md   ← in-repo symlink → ../.agents/AGENTS.md
        ├── settings.json
        ├── statusline-command.sh
        └── skills/<name> → ../../.agents/skills/<name>   (in-repo symlinks)
```

Every direct child of `home/` becomes a `~/`-level entry of the same name. The directory tree IS the manifest — there's no manifest file.

## Install

First time on a machine:

```sh
git clone <repo-url> "${DOTAGENTS:-$HOME/.dotagents}"
"${DOTAGENTS:-$HOME/.dotagents}/bin/dotagents" install
```

After pulling updates:

```sh
dotagents install
```

The install command is idempotent. It runs `git pull --ff-only` (skip with `--no-pull`), then for each top-level entry under `home/`, ensures the matching `~/<entry>/` directory exists and creates symlinks for every item inside that points back into the repo. Existing real files at the destination are left alone and reported as conflicts.

## Local overrides

Anything machine-specific lives at the destination as a real file (never symlinked, never managed):

- `~/.claude/settings.local.json` — per-machine Claude permissions, hooks, env vars
- Files matching `*.local.*`, `.env*` anywhere under `~/` — left alone by install

## Adding an agent

1. Create `home/<dotdir>/` (e.g. `home/.codex/`).
2. Populate it with the agent's expected files.
3. For agents that have a per-user behavioral instruction file, make it an in-repo symlink to `../.agents/AGENTS.md`.
4. `dotagents install`.

No script change required.
