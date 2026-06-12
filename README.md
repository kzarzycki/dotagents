# dotagents

A git repo holding the canonical configuration for any CLI agent the user runs (Claude Code today; Codex, pi, others later). One source of truth, one install command, identical state across every machine.

## Layout

```
dotagents/
├── README.md
├── AGENTS.md           ← meta: instructions for agents working on THIS repo
├── bin/
│   ├── dotagents       ← the install command
│   └── remote-setup.sh ← Claude Code on the web bootstrap (clone/find + install --profile remote)
├── patches/            ← overlay scripts run by SessionStart hooks
│   ├── memsearch/      ← memsearch plugin patches + per-machine bootstrap
│   └── dev-marketplace/← live-dev plugin linker + tracked marketplace.json
└── home/               ← install payload; 1:1 mirror of ~/
    ├── .agents/
    │   ├── AGENTS.md   ← canonical user behavioral spec
    │   └── env.sh      ← shell extensions for managed tools (PATH, MEMSEARCH_DIR)
    └── .claude/
        ├── CLAUDE.md            ← in-repo symlink → ../.agents/AGENTS.md
        ├── settings.shared.json ← config common to every machine
        ├── settings.<profile>.json
        ├── statusline.sh
        ├── commands/
        ├── hooks/
        │   └── preload-skills.py ← SessionStart skill preloader
        └── preload-skills.txt    ← list of skills to preload every session
```

Every direct child of `home/` becomes a `~/`-level entry of the same name. The directory tree IS the manifest — there's no manifest file.

Skills are not vendored here. Claude skills come from plugins and marketplaces declared in `home/.claude/settings.shared.json` and profile overlays.

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

The install command is idempotent. It (1) resolves the machine profile (see Profiles), (2) runs `git pull --ff-only` (skip with `--no-pull`), (3) ensures `~/.dotagents` resolves to the repo, (4) for each top-level entry under `home/`, creates symlinks at `~/<entry>/<item>` pointing back into the repo (also removing skill symlinks left by older dotagents versions), (5) appends a one-time source line for `~/.agents/env.sh` to existing `~/.bashrc`/`~/.zshrc` — the rc files stay machine-owned, only the snippet is managed; `env.sh` carries shell extensions the managed tools need (PATH, `MEMSEARCH_DIR`), not general shell config, (6) generates `~/.claude/settings.json` by deep-merging `settings.shared.json` + the profile overlay, (7) validates: settings must parse as JSON, no dangling symlinks in managed dotdirs. Existing real files at destinations are left alone and reported as conflicts. `--dry-run` prints actions without changing anything. Requires `jq`.

### `~/.dotagents` symlink

Committed files (e.g. `home/.claude/settings.shared.json` hook commands) reference the repo via `$HOME/.dotagents/...`. The install command creates `~/.dotagents` -> the actual clone path on each machine, so the repo can live anywhere while the access path stays canonical. Reliable regardless of shell env state. Cloning the repo directly at `~/.dotagents` (typical on a VPS) also works — install detects it and skips the symlink.

### Profiles (`~/.dotagents-profile`)

Some configuration is machine-class-specific (xebia-only marketplaces and plugins on Mac and on xebia worker machines; nothing extra on a personal VPS). To handle this without per-machine repo forks, dotagents uses profiles:

- `home/.claude/settings.shared.json` — config common to every machine.
- `home/.claude/settings.<profile>.json` — per-profile overlay (e.g. `mac`, `vps`, `xebia-remote`).
- `~/.dotagents-profile` — single line naming the profile for this machine. Per-machine, not committed.

`bin/dotagents install` resolves the profile in this order: `--profile <name>` flag, existing `~/.dotagents-profile`, interactive prompt (TTY only). The resolved value is written to `~/.dotagents-profile` so subsequent runs need no flag. Install deep-merges shared + profile (profile wins per key; nested objects merge, arrays replace — so profiles must not define `hooks`; install warns if one does) and writes the result to `~/.claude/settings.json` — Claude Code's only user-scope settings file (user-level `settings.local.json` is not read by CC). Regenerated on every install, diff printed when it changes. To change managed config: edit the repo files and re-run `dotagents install`, never the generated file. Add new profiles by creating new `home/.claude/settings.<name>.json` files; no install-script change needed.

Between installs Claude Code persists runtime preferences (`/model`, `/effort`, don't-ask-again flags) into the same generated file. They stay machine-local and never dirty the repo; the next `dotagents install` resets the file to repo state, and the printed diff shows what got dropped.

```sh
# first install on a new machine
dotagents install --profile mac
# subsequent runs pick up profile from ~/.dotagents-profile
dotagents install
```

### memsearch bootstrap (per machine)

`home/.claude/settings.shared.json` enables the memsearch plugin and wires a SessionStart hook that runs `patches/memsearch/apply.sh` (idempotent, fast no-op once patched). The hook patches the installed plugin: PreCompact transcript capture, flock-guarded markdown writes, and a Milvus flush fix (upstream bug #534). To make memsearch actually function on a fresh machine, run once:

```sh
~/.dotagents/patches/memsearch/bootstrap.sh
```

It (a) installs `memsearch` via `uv tool install`, (b) writes `~/.memsearch/standalone/docker-compose.yml` (Milvus + etcd, relative volumes), (c) brings the stack up via `docker compose up -d`. Idempotent; safe to re-run.

Requirements: `uv` (https://docs.astral.sh/uv/), running Docker daemon, `python3`, `flock` (Linux: built-in; macOS: `brew install flock`). After bootstrap, restart Claude Code so the SessionStart hook applies the patches.

### dev marketplace (live local plugins)

`home/.claude/settings.shared.json` declares a `dev` directory marketplace at `~/dev` and wires a SessionStart hook that runs `patches/dev-marketplace/apply.sh`, which:

1. Symlinks `~/dev/.claude-plugin/marketplace.json` to the repo-tracked copy at `patches/dev-marketplace/marketplace.json` — the marketplace definition is versioned here, not a loose machine-local file.
2. For every installed `<name>@dev` plugin with a local `./repo/plugin` source, symlinks its plugin-cache install dir to the working tree under `~/dev` — editing the plugin source plus `/reload-plugins` is enough, no re-copy or push.

To add a plugin: add its `./repo/plugin` entry to `patches/dev-marketplace/marketplace.json`, enable `<name>@dev` in the profile overlay. The hook is a silent no-op on machines without `~/dev` or without the plugin's source repo.

### Skill preloading (always-on skills)

Claude Code loads a skill's full SKILL.md only when the model decides to invoke it — there is no native "always load" flag. For skills that must be active from turn 1 in every session (e.g. `communicating-in-html`), `home/.claude/settings.shared.json` wires a SessionStart hook (matcher `startup|resume|clear|compact`, so content is re-injected after `/clear` and compaction) that runs `home/.claude/hooks/preload-skills.py`. The script reads `home/.claude/preload-skills.txt` (installed as `~/.claude/preload-skills.txt`), resolves each entry to a SKILL.md, and injects the contents as `additionalContext`, marked as active skills with their base directory — so progressive disclosure is preserved: only SKILL.md enters context, `references/` and `assets/` are read on demand.

Entry forms in `preload-skills.txt`: bare skill name (searched in `~/.claude/skills/` and all plugin marketplaces + cache, newest copy by mtime wins), `plugin:skill-name`, or an absolute/`~` path to a skill dir. Duplicate names load once — first entry wins, so list a machine-specific dev checkout before a portable fallback name. Fail-safe: entries that don't resolve on a machine are skipped, and every session start prints a `preload-skills: loaded: ... / NOT FOUND (skipped): ...` note. Keep total preloaded content under ~9.5KB; Claude Code diverts hook output above 10KB to a file instead of context (the script warns when exceeded).

### Remote sessions (Claude Code on the web)

Cloud sessions run in an ephemeral container that's reclaimed after use, so dotagents has to re-apply itself on every container build. The `remote` profile plus `bin/remote-setup.sh` make a fresh container come up fully configured — plugins, hooks, statusline, env — with no manual steps.

How it fits together:

- **Generation, not symlink-to-running.** The harness starts Claude Code *after* the container's setup script runs. `bin/remote-setup.sh` runs `dotagents install --profile remote` during that setup step, which writes `~/.claude/settings.json` *before* Claude Code reads it. Claude Code then auto-installs every `enabledPlugins` entry from the declared `extraKnownMarketplaces` on session start (declarative — no `claude plugin install` calls needed), wires the SessionStart skill-preloader + `patches/*` hooks, and applies the statusline and `env`.
- **Coexists with the harness's own hooks.** Claude Code *merges* `hooks` across settings layers rather than overriding, so the remote launcher's git-identity / stop-gate hooks and dotagents' hooks all run. dotagents only writes user-scope `~/.claude/settings.json`, which the harness leaves for us.
- **The `remote` profile (`settings.remote.json`) disables only what can't run in a container:** `memsearch` (needs Docker + Milvus + `uv`) and `experimental@dev` / any `*@dev` plugin (no `~/dev` live-dev tree). It enables `experimental@kzarzycki-agent-skills` (public source for the same skills, e.g. `communicating-in-html`) and sets `CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1` so marketplace clones use HTTPS, not SSH. Private marketplaces stay enabled — the remote environment has credentials for them. The shared `patches/memsearch` and `patches/dev-marketplace` SessionStart hooks stay wired but self-guard to a silent no-op when their infra is absent.

Setup: in the environment's **Setup script** field (Claude Code on the web → environment settings), paste one of —

```sh
# A) dotagents added as a workspace source repo (cloned via the harness git
#    proxy; preferred under a GitHub-scoped network policy — no extra egress):
bash "$(ls -d "$HOME"/*/dotagents/bin/remote-setup.sh /home/*/dotagents/bin/remote-setup.sh 2>/dev/null | head -1)"

# B) fetch + run directly (needs raw.githubusercontent.com egress):
curl -fsSL https://raw.githubusercontent.com/kzarzycki/dotagents/main/bin/remote-setup.sh | bash
```

`remote-setup.sh` is idempotent: it ensures `jq`, finds an existing checkout (workspace source repo or `~/.dotagents`) or clones one, then runs `dotagents install --profile remote`. Container state is cached after the setup script, so later sessions start instantly.

**Network policy.** Auto-installing plugins (and option B's fetch) needs outbound access to the marketplace hosts — set the environment's network policy to one that permits GitHub (and `raw.githubusercontent.com` for option B). Under a repo-scoped policy, add `kzarzycki/dotagents` as a workspace source repo and use option A so the repo arrives via the harness proxy; public marketplace plugins still need GitHub egress to install.

## Local overrides

Machine-class config belongs in the committed profile overlay (`home/.claude/settings.<profile>.json`); `~/.claude/settings.json` is generated from the repo, not a free local file. Truly per-machine state, never committed:

- `~/.dotagents-profile` — single line naming this machine's profile
- Runtime prefs Claude writes into `~/.claude/settings.json` — machine-local until the next install resets them
- Files matching `*.local.*`, `.env*` under managed dotdirs — left alone by install

### Marketplace overrides

`home/.claude/settings.shared.json` declares shared marketplaces. Prefer `github` sources for portable repos. For shared local marketplaces that are expected to exist on every machine, use `~` paths rather than absolute user paths; Claude resolves `~/...` at runtime.

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
