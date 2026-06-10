# AGENTS.md — instructions for agents working on this repo

This file is for you, the agent helping the user maintain dotagents itself. It is **not** the user's behavioral spec. The user's spec is at `home/.agents/AGENTS.md` (which installs to `~/.agents/AGENTS.md`).

## What this repo is

A dotfiles-style repo whose `home/` directory mirrors what the user wants under `~/`. The install command (`bin/dotagents`) walks `home/` and creates symlinks at the matching `~/`-paths. Each agent's per-user instruction file (`home/.claude/CLAUDE.md`, future `home/.codex/AGENTS.md`) is an in-repo symlink to `home/.agents/AGENTS.md`, so a single edit propagates everywhere.

## Working rules

- **Never edit `home/.claude/CLAUDE.md` (or any per-agent instruction file) directly.** They're symlinks. Edit `home/.agents/AGENTS.md` instead — every agent's instruction file resolves to it.
- **The directory tree under `home/` IS the manifest.** There is no `manifest.toml`. To add an agent, create `home/<dotdir>/` and populate it. To remove one, delete the dir.
- **Machine-class config goes in profile overlays.** Shared config lives in `home/.claude/settings.json`; machine-class config in `home/.claude/settings.<profile>.json` (install symlinks `~/.claude/settings.local.json` to the active profile's file — edit the profile file, never a loose local one).
- **Local-overrides never enter the repo.** `*.local.*`, `.env*`, `settings.local.json`, and `projects/` are skipped by install and must not be committed. The `.gitignore` enforces this.
- **`patches/` scripts run on every SessionStart — keep them idempotent.** They overlay installed plugins (`memsearch/`) or link live-dev plugins (`dev-marketplace/`); the no-op pass must be fast and silent.
- **In-repo symlinks use relative paths.** E.g. `home/.claude/CLAUDE.md → ../.agents/AGENTS.md`. Keep them relative so they resolve correctly inside the repo regardless of where it's cloned.
- **Per-agent files that are agent-specific (settings, hooks, slash commands) live inside `home/<agent-dotdir>/`** — never lift them into `home/.agents/` unless they're genuinely shared across agents.
- **Do not vendor skill payloads or skill lockfiles in this repo.** Configure Claude plugins and marketplaces in `home/.claude/settings.json` or `home/.claude/settings.<profile>.json`; skills live in their source plugin/marketplace repos.

## When changing the install script

The install script lives at `bin/dotagents`. It must remain:

- Idempotent — safe to run repeatedly.
- Pure bash, no external deps beyond standard Linux/macOS tools (`git`, `ln`, `mkdir`, `jq` for validation).
- Conservative — never overwrite a real file at a destination; only replace existing symlinks. Report conflicts and continue.

Before committing changes to the install script, sandbox-test it with a fake `$HOME`:

```sh
HOME=/tmp/dotagents-test bin/dotagents install --no-pull
```

## When adding a new agent

1. Create the agent's dotdir under `home/`.
2. If the agent has a per-user behavioral file, make it an in-repo symlink to `../.agents/AGENTS.md` (adjust the `..` depth for nested locations).
3. Update `README.md` if the addition changes user-facing instructions.
4. Sandbox-test the install. Confirm the agent's expected files land at the right `~/`-paths.

## Out of scope for this repo

- Project-scoped agent state (per-project CLAUDE.md, per-project memories).
- Cloud / remote agent sessions (Claude Code remote, Codex remote). Those load only repo-committed `<project>/.claude/` config; bridging dotagents into them is a separate effort tracked outside V1.
- Skill payload vendoring. This repo records plugin and marketplace configuration, not copied skill content.
