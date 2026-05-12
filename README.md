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
# Clone wherever you want.
git clone <repo-url> /path/of/your/choice
/path/of/your/choice/bin/dotagents install
```

After pulling updates:

```sh
dotagents install
```

The install command is idempotent. It (1) runs `git pull --ff-only` (skip with `--no-pull`), (2) ensures `~/.dotagents` is a symlink to the repo, (3) for each top-level entry under `home/`, creates symlinks at `~/<entry>/<item>` pointing back into the repo. Existing real files at the destination are left alone and reported as conflicts.

### `~/.dotagents` symlink

Committed files (e.g. `home/.claude/settings.json` hook commands) reference the repo via `$HOME/.dotagents/...`. The install command creates `~/.dotagents` -> the actual clone path on each machine, so the repo can live anywhere while the access path stays canonical. Reliable regardless of shell env state.

### memsearch bootstrap (per machine)

`home/.claude/settings.json` enables the memsearch plugin and wires a SessionStart hook that runs `patches/memsearch/apply.sh` (idempotent, fast no-op once patched). To make memsearch actually function on a fresh machine, run once:

```sh
~/.dotagents/patches/memsearch/bootstrap.sh
```

It (a) installs `memsearch` via `uv tool install`, (b) writes `~/.memsearch/standalone/docker-compose.yml` (Milvus + etcd, relative volumes), (c) brings the stack up via `docker compose up -d`. Idempotent; safe to re-run.

Requirements: `uv` (https://docs.astral.sh/uv/), running Docker daemon, `flock` (Linux: built-in; macOS: `brew install flock`). After bootstrap, restart Claude Code so the SessionStart hook applies the python-side flush patch (memsearch upstream bug #534).

## Local overrides

Anything machine-specific lives at the destination as a real file (never symlinked, never managed):

- `~/.claude/settings.local.json` — per-machine Claude permissions, hooks, env vars
- Files matching `*.local.*`, `.env*` anywhere under `~/` — left alone by install

### Marketplace overrides

`home/.claude/settings.json` declares marketplaces as `github` sources for portability. If you are actively developing one of those repos locally and want Claude Code to pick up uncommitted changes, override that marketplace in `~/.claude/settings.local.json` with a `directory` source pointing at your local clone. Example:

```json
{
  "extraKnownMarketplaces": {
    "kzarzycki-agent-skills": {
      "source": { "source": "directory", "path": "/Users/you/dev/agent-skills" }
    }
  }
}
```

The same applies to any marketplace with no public remote (e.g. local-only knowledge bases) — declare it in `settings.local.json` and enable its plugins there too.

## Adding an agent

1. Create `home/<dotdir>/` (e.g. `home/.codex/`).
2. Populate it with the agent's expected files.
3. For agents that have a per-user behavioral instruction file, make it an in-repo symlink to `../.agents/AGENTS.md`.
4. `dotagents install`.

No script change required.
