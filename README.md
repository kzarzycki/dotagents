# dotagents

A git repo holding the canonical configuration for any CLI agent the user runs (Claude Code today; Codex, pi, others later). One source of truth, one install command, identical state across every machine.

## Layout

```
dotagents/
├── README.md
├── AGENTS.md           ← meta: instructions for agents working on THIS repo
├── bin/
│   └── dotagents       ← the install command
├── patches/            ← overlay scripts run by SessionStart hooks
│   ├── memsearch/      ← memsearch plugin patches + per-machine bootstrap
│   └── dev-marketplace/← live-dev plugin linker + tracked marketplace.json
└── home/               ← install payload; 1:1 mirror of ~/
    ├── .agents/
    │   └── AGENTS.md   ← canonical user behavioral spec
    └── .claude/
        ├── CLAUDE.md   ← in-repo symlink → ../.agents/AGENTS.md
        ├── settings.json
        ├── settings.<profile>.json
        ├── statusline.sh
        └── commands/
```

Every direct child of `home/` becomes a `~/`-level entry of the same name. The directory tree IS the manifest — there's no manifest file.

Skills are not vendored here. Claude skills come from plugins and marketplaces declared in `home/.claude/settings.json` and profile overlays.

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

The install command is idempotent. It (1) resolves the machine profile (see Profiles), (2) runs `git pull --ff-only` (skip with `--no-pull`), (3) ensures `~/.dotagents` resolves to the repo, (4) for each top-level entry under `home/`, creates symlinks at `~/<entry>/<item>` pointing back into the repo (also removing skill symlinks left by older dotagents versions), (5) symlinks `~/.claude/settings.local.json` to the resolved profile overlay, (6) validates: `~/.claude/settings.json` must parse as JSON, no dangling symlinks in managed dotdirs. Existing real files at destinations are left alone and reported as conflicts. `--dry-run` prints actions without changing anything.

### `~/.dotagents` symlink

Committed files (e.g. `home/.claude/settings.json` hook commands) reference the repo via `$HOME/.dotagents/...`. The install command creates `~/.dotagents` -> the actual clone path on each machine, so the repo can live anywhere while the access path stays canonical. Reliable regardless of shell env state. Cloning the repo directly at `~/.dotagents` (typical on a VPS) also works — install detects it and skips the symlink.

### Profiles (`~/.dotagents-profile`)

Some configuration is machine-class-specific (xebia-only marketplaces and plugins on Mac and on xebia worker machines; nothing extra on a personal VPS). To handle this without per-machine repo forks, dotagents uses profiles:

- `home/.claude/settings.json` — shared base linked to `~/.claude/settings.json` on every machine.
- `home/.claude/settings.<profile>.json` — per-profile overlay linked to `~/.claude/settings.local.json`. CC merges both files (committed base + profile overlay) at runtime.
- `~/.dotagents-profile` — single line naming the profile for this machine (e.g. `mac`, `vps`, `xebia-remote`). Per-machine, not committed.

`bin/dotagents install` resolves the profile in this order: `--profile <name>` flag, existing `~/.dotagents-profile`, interactive prompt (TTY only). The resolved value is written to `~/.dotagents-profile` so subsequent runs need no flag. The matching `settings.<profile>.json` is symlinked to `~/.claude/settings.local.json`. Editing through either symlink writes back into the repo. Add new profiles by creating new `home/.claude/settings.<name>.json` files; no install-script change needed.

```sh
# first install on a new machine
dotagents install --profile mac
# subsequent runs pick up profile from ~/.dotagents-profile
dotagents install
```

### memsearch bootstrap (per machine)

`home/.claude/settings.json` enables the memsearch plugin and wires a SessionStart hook that runs `patches/memsearch/apply.sh` (idempotent, fast no-op once patched). The hook patches the installed plugin: PreCompact transcript capture, flock-guarded markdown writes, and a Milvus flush fix (upstream bug #534). To make memsearch actually function on a fresh machine, run once:

```sh
~/.dotagents/patches/memsearch/bootstrap.sh
```

It (a) installs `memsearch` via `uv tool install`, (b) writes `~/.memsearch/standalone/docker-compose.yml` (Milvus + etcd, relative volumes), (c) brings the stack up via `docker compose up -d`. Idempotent; safe to re-run.

Requirements: `uv` (https://docs.astral.sh/uv/), running Docker daemon, `python3`, `flock` (Linux: built-in; macOS: `brew install flock`). After bootstrap, restart Claude Code so the SessionStart hook applies the patches.

### dev marketplace (live local plugins)

`home/.claude/settings.json` declares a `dev` directory marketplace at `~/dev`. The profile overlays wire a SessionStart hook that runs `patches/dev-marketplace/apply.sh`, which:

1. Symlinks `~/dev/.claude-plugin/marketplace.json` to the repo-tracked copy at `patches/dev-marketplace/marketplace.json` — the marketplace definition is versioned here, not a loose machine-local file.
2. For every installed `<name>@dev` plugin with a local `./repo/plugin` source, symlinks its plugin-cache install dir to the working tree under `~/dev` — editing the plugin source plus `/reload-plugins` is enough, no re-copy or push.

To add a plugin: add its `./repo/plugin` entry to `patches/dev-marketplace/marketplace.json`, enable `<name>@dev` in the profile overlay. The hook is a silent no-op on machines without `~/dev` or without the plugin's source repo.

## Local overrides

Machine-class config belongs in the committed profile overlay (`home/.claude/settings.<profile>.json`); `~/.claude/settings.local.json` is a managed symlink to it, not a free local file. Truly per-machine state, never committed and never touched by install:

- `~/.dotagents-profile` — single line naming this machine's profile
- Files matching `*.local.*`, `.env*` under managed dotdirs — left alone by install

### Marketplace overrides

`home/.claude/settings.json` declares shared marketplaces. Prefer `github` sources for portable repos. For shared local marketplaces that are expected to exist on every machine, use `~` paths rather than absolute user paths; Claude resolves `~/...` at runtime.

```json
{
  "extraKnownMarketplaces": {
    "dev": {
      "source": { "source": "directory", "path": "~/dev" }
    }
  }
}
```

Machine-specific marketplaces (e.g. absolute local paths) belong in the profile overlay (`home/.claude/settings.<profile>.json`).

## Adding an agent

1. Create `home/<dotdir>/` (e.g. `home/.codex/`).
2. Populate it with the agent's expected files.
3. For agents that have a per-user behavioral instruction file, make it an in-repo symlink to `../.agents/AGENTS.md`.
4. `dotagents install`.

No script change required.
