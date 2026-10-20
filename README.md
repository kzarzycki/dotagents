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
│   ├── dev-marketplace/← live-dev plugin linker + tracked marketplace.json
│   ├── pixelrag/       ← per-machine pixelshot binary bootstrap
│   ├── omp/             ← per-machine OMP plugin bootstrap
│   └── remote/          ← Claude Code on the web per-session dotagents pull
└── home/               ← install payload; 1:1 mirror of ~/
    ├── .agents/
    │   ├── AGENTS.md   ← canonical user behavioral spec, including Ponytail
    │   └── env.sh      ← shell extensions for managed tools (PATH, tool env)
    ├── .claude/
    │   ├── CLAUDE.md            ← in-repo symlink → ../.agents/AGENTS.md
    │   ├── settings.shared.json ← config common to every machine
    │   ├── settings.<profile>.json
    │   ├── statusline.sh
    │   └── commands/
    ├── .codex/
    │   └── AGENTS.md             ← in-repo symlink → ../.agents/AGENTS.md
    ├── .gemini/
    │   └── GEMINI.md             ← in-repo symlink → ../.agents/AGENTS.md
```

Every direct child of `home/` becomes a `~/`-level entry of the same name. The directory tree IS the manifest — there's no manifest file.

The installed user baseline enables no capability plugins globally. Ponytail is a section of `home/.agents/AGENTS.md`, the shared behavioral spec, not a Claude Code plugin. Capability -- tools, MCP servers, domain knowledge -- stays with the project that needs it. `find-skills`, when present under `~/.agents/skills/`, is an independently installed universal discovery skill; dotagents does not install or update it. Repository skills and MCPs come from each project's APM manifest.

OMP (oh-my-pi) is a first-class payload under `home/.omp/`: its config, rules,
and extensions install with the normal command just like Claude and Codex
payloads. OMP's databases, credentials, caches, plugin registries, and binaries
remain machine-local. Run `patches/omp/bootstrap.sh` after installing OMP to
install the pinned `kzarzycki/pi-automode` fork.

## Repository development agent layer

The repository root is an APM consumer for work on dotagents itself. Run:

```sh
mise run agent-sync
```

The task installs the locked `engineering` capability pack and compiles project configuration for the supported coding agents, currently Claude Code and Codex. Pass `-- --refresh` to resolve a newer compatible release or `-- --frozen` to verify committed state. For each future coding agent, add its target in `apm.yml`, then add its native-output validation and generated-output paths to both frozen checks in `mise.toml`. Root project files stay in this repository; `home/` remains the payload installed under `~/`.

MCPs and project skills belong in `apm.yml`, not user-global agent configuration. `agent-sync` compiles only the dependencies declared by the repository. Codex plugins are user-global in the current Codex release and cannot be disabled reliably by project configuration; keep only genuinely universal plugins installed globally. Package project capabilities for APM, or use an isolated `CODEX_HOME` when a plugin cannot be represented as project files.

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

The install command is idempotent. It (1) resolves the machine profile (see Profiles), (2) runs `git pull --ff-only` (skip with `--no-pull`), (3) ensures `~/.dotagents` resolves to the repo, (4) for each top-level entry under `home/`, creates symlinks at `~/<entry>/<item>` pointing back into the repo (also removing skill symlinks left by older dotagents versions), (5) appends a one-time source line for `~/.agents/env.sh` to existing `~/.bashrc`/`~/.zshrc` — the rc files stay machine-owned, only the snippet is managed; `env.sh` carries shell extensions the managed tools need (PATH and tool-specific environment), not general shell config, (6) generates `~/.claude/settings.json` by deep-merging `settings.shared.json` + the profile overlay, (7) validates: settings must parse as JSON, no dangling symlinks in managed dotdirs. Existing real files at destinations are left alone and reported as conflicts. `--dry-run` prints actions without changing anything. Requires `jq`.

To install only selected top-level payloads, pass `--only` once per entry:

```sh
dotagents install --only omp --no-pull
dotagents install --only claude --only codex --no-pull
```

The value names a directory under `home/`, with or without its leading dot.
Subset installs mirror only the selected payload directories. They skip git
pull, repository hooks, and pre-commit setup. Profile/settings generation runs
when `.claude` is selected; shell startup setup runs when `.agents` is selected.
The `~/.dotagents` link is created when `.claude` is selected because Claude
hooks reference it. The default install with no `--only` remains the complete
machine setup.

### OMP plugin bootstrap

```sh
patches/omp/bootstrap.sh
```

This checks for the pinned `kzarzycki/pi-automode` commit and replaces a
different installed source before installing it. OMP owns the generated
package and lock files; they are not symlinked into dotagents.

### `~/.dotagents` symlink

Committed files (e.g. `home/.claude/settings.shared.json` hook commands) reference the repo via `$HOME/.dotagents/...`. The install command creates `~/.dotagents` -> the actual clone path on each machine, so the repo can live anywhere while the access path stays canonical. Reliable regardless of shell env state. Cloning the repo directly at `~/.dotagents` (typical on a VPS) also works — install detects it and skips the symlink.

### Profiles (`~/.dotagents-profile`)

Some configuration is machine-class-specific, such as environment variables, local marketplace locations, UI preferences, and remote constraints. To handle this without per-machine repo forks, dotagents uses profiles:

- `home/.claude/settings.shared.json` — config common to every machine.
- `home/.claude/settings.<profile>.json` — per-profile overlay (e.g. `mac`, `vps`, `remote`).
- `~/.dotagents-profile` — single line naming the profile for this machine. Per-machine, not committed.

`bin/dotagents install` resolves the profile in this order: `--profile <name>` flag, existing `~/.dotagents-profile`, interactive prompt (TTY only). The resolved value is written to `~/.dotagents-profile` so subsequent runs need no flag. Install deep-merges shared + profile (profile wins per key; nested objects merge, arrays replace — so profiles must not define `hooks`; install warns if one does) and writes the result to `~/.claude/settings.json` — Claude Code's only user-scope settings file (user-level `settings.local.json` is not read by CC). Regenerated on every install, diff printed when it changes. To change managed config: edit the repo files and re-run `dotagents install`, never the generated file. Add new profiles by creating new `home/.claude/settings.<name>.json` files; no install-script change needed.

Between installs Claude Code persists runtime preferences (`/model`, `/effort`, don't-ask-again flags) into the same generated file. They stay machine-local and never dirty the repo; the next `dotagents install` resets the file to repo state, and the printed diff shows what got dropped.

OpenTelemetry export is on for Claude Code and Codex: metrics and logs go over OTLP/HTTP to the homelab APM Collector at `http://cc-experiments.taile39822.ts.net:4318` (tailnet only), tagged `service.namespace=agents`. Prompt, tool-detail, tool-content, raw-body and response logging stay off, and so do traces and the account UUID. The `remote` profile turns telemetry off, since the web has no tailnet. Settings `env` values are literal, so install appends `host.name=$(hostname)` to `OTEL_RESOURCE_ATTRIBUTES`; Codex reports the same value itself. Codex reads OTel only from `~/.codex/config.toml`, so when `~/.codex/` exists install keeps a marked `[otel]` block at the end of that file, built from the merged `OTEL_EXPORTER_OTLP_ENDPOINT`, and removes it when telemetry is off. An `[otel]` table outside the markers is left alone with a warning.

```sh
# first install on a new machine
dotagents install --profile mac
# subsequent runs pick up profile from ~/.dotagents-profile
dotagents install
```

### Per-directory config homes (`CLAUDE_CONFIG_DIR`)

Orthogonal to machine Profiles above (those overlay one `~/.claude`; this picks *which* config home). `home/.agents/env.sh` exports `CLAUDE_CONFIG_DIR` from the cwd, so every tool that honors it — claude, omnigent, oh-my-pi — shares one config home (plugins, MCP, history, settings) per project group. Under `~/knowledge/*` it points at `~/.claude-knowledge`; everywhere else it's unset, so tools fall back to their own default `~/.claude` — the dev profile. A forgotten group dir, a GUI/Dock launch, and a daemon started without the var therefore all land on dev.

The dev profile *is* `~/.claude` — the tool's own hardcoded fallback — so it needs no var and no setup; that's why a forgotten var lands there. `~/.claude-dev` exists as a symlink onto it, so the name `.claude-dev` is available for explicit references (e.g. a daemon plist) and resolves to the same dev config.

Add a group: one `case` line in `env.sh` plus `mkdir ~/.claude-<group>` (a config home is created lazily; `{}` in `settings.json` is enough to start). The fallback (dev) needs nothing.

Auto-started daemons have no cwd or shell, so pin the var in the launcher instead. launchd:

```xml
<key>EnvironmentVariables</key>
<dict><key>CLAUDE_CONFIG_DIR</key><string>/Users/you/.claude-knowledge</string></dict>
```

Omit it (or point at `~/.claude-dev`) to get dev. Shell coverage is bash/zsh (env.sh is POSIX, same as the rest of the repo).

### Shared agent memory

Hindsight runs once on the VPS. After client bootstrap, Claude Code, Codex, OMP and Omnigent's native Claude/Codex sessions on the Mac and VPS point at the same per-repository bank. The database and OpenAI Codex OAuth extraction stay on the VPS; the Mac installs client hooks only. A Tailscale outage leaves Mac agents usable without memory, not with a divergent local database.

On each workspace machine, install dotagents and run:

```sh
~/.dotagents/patches/hindsight/bootstrap.sh
```

The bootstrap reads `~/.dotagents-profile` (`mac` or `vps`), pins `@vectorize-io/hindsight-coding-agents@0.6.1`, installs its Codex hooks in self-hosted mode, and updates private `~/.hindsight/coding-agent.json` and `~/.omp/agent/.env` without dropping unrelated settings. The Mac points at the tailnet HTTPS endpoint; the VPS uses its own loopback API even when Tailscale is down. Claude hooks already live in `home/.claude/settings.shared.json`, so running the official Claude installer would duplicate them. Trust the changed Codex hooks once when Codex asks. The bootstrap does nothing in remote Claude Code containers. It never starts a server on the Mac.

OMP's tracked `home/.omp/agent/config.yml` defaults to `http://127.0.0.1:9077`, `coding-agent` with `per-project` scoping, and five-second automatic recall/request deadlines. The bootstrap sets a machine-local `HINDSIGHT_API_URL` override in OMP's private `.env`; on the Mac it selects `https://cc-experiments.taile39822.ts.net:9077`. The coding-agents hooks use `coding-agent-{gitProject}`; both integrations resolve Trinity to `coding-agent-trinity`. OMP's three seeded mental models are disabled until their stale content and failed refreshes are repaired. Claude/Codex automatic hook calls still have host deadlines of 30 seconds at startup/prompt and 60 seconds at stop; an unreachable server can delay a prompt, but must not stop the agent. A failed OMP retain is not a durable offline queue: re-submit important unsaved memories after service returns.

Every LLM call Hindsight makes bills the ChatGPT plan the coding agents use, so the server runs on the same model they do, `gpt-6.1-sol`, and each bank refreshes a mental model at most hourly: `mental_model_min_refresh_interval_seconds` is 3600, set per bank with `PATCH /v1/default/banks/<bank>/config`. At the default of 0 a busy bank refreshed on every retain and drained the plan.

On the VPS only, the private `~/.hindsight/profiles/coding-agent.env` configures the pinned local API:

```sh
HINDSIGHT_API_LLM_PROVIDER=openai-codex
HINDSIGHT_API_LLM_MODEL=gpt-6.1-sol
HINDSIGHT_API_RERANKER_PROVIDER=rrf
HINDSIGHT_API_WORKER_MAX_SLOTS=2
HINDSIGHT_API_WORKER_CONSOLIDATION_RESERVED_SLOTS=1
HINDSIGHT_API_RETAIN_MEMORY_BUDGET_MB=64
HINDSIGHT_API_DB_POOL_MIN_SIZE=2
HINDSIGHT_API_DB_POOL_MAX_SIZE=20
OMP_NUM_THREADS=2
OPENBLAS_NUM_THREADS=2
MKL_NUM_THREADS=2
NUMEXPR_NUM_THREADS=2
HINDSIGHT_API_DATABASE_URL=pg0://hindsight-embed-coding-agent
```

Run `uvx hindsight-api@0.10.1 --host 127.0.0.1 --port 9077` in the foreground under a Linux user systemd service with `EnvironmentFile=%h/.hindsight/profiles/coding-agent.env`. The VPS unit limits the API and its PostgreSQL child together: `MemoryMax=2G`, `MemorySwapMax=0`, `CPUQuota=150%`, `Restart=on-failure`, `RestartSec=10`, `StartLimitIntervalSec=300`, `StartLimitBurst=3`. The RRF reranker avoids loading a second local model; preserve the existing embedding model so stored vectors stay comparable.

The VPS exposes that loopback API through Tailscale **Serve** (not public Funnel): `sudo tailscale serve --bg --https=9077 http://127.0.0.1:9077`. Serve encrypts traffic inside the tailnet. The owner chose tailnet access alone, without a Hindsight API key, to keep existing agent sessions working. The tailnet policy could not be inspected from the VPS, so **every device currently allowed to reach port 9077 can read, change, or delete the memory bank**; restrict the grant to the Mac when policy access is available. If application authentication is added later, stage its key in every running client *before* requiring it on the server; changing the server first rejects in-flight retains. Keep keys, OAuth state, database, and generated hooks machine-local, never in dotagents.

### pixelrag bootstrap (per machine)

`settings.shared.json` declares the optional `pixelrag-plugins` marketplace but leaves `pixelbrowse@pixelrag-plugins` disabled globally. A project that enables it also needs the `pixelshot` binary installed once per machine:

```sh
~/.dotagents/patches/pixelrag/bootstrap.sh
```

It runs `uv tool install pixelrag` in an isolated environment. Idempotent; requires `uv`.

`pixelshot`'s default `cdp` backend launches its own headless browser from `$CHROME_PATH`; its bundled auto-download is linux-x64 only, so on macOS `home/.agents/env.sh` points `CHROME_PATH` at an installed Brave/Chrome (open a new shell after install), and on linux-x64 it self-provisions on first run.

### user-global skills bootstrap (per machine)

dotagents does not vendor skills (the install skip-list and a test forbid `home/.claude/skills`); capability stays with its source repo. The few *user-global* skills that should follow you everywhere are installed from their source repos via the `skills` CLI, so `skills update` keeps working. Run once per machine:

```sh
~/.dotagents/patches/skills/bootstrap.sh
```

Installs `herdr` (control the Herdr multiplexer; upstream `herdrdev/herdr`) and `orchestrating-agents` (Herdr vs SendMessage vs tmux decision guide; first-party, `kzarzycki/agent-skills` experimental pack). Idempotent; requires `npx`. Herdr's *config* travels separately: `home/.agents/herdr.toml` is tracked and `env.sh` points `HERDR_CONFIG_PATH` at it, so the prefix/UI settings are identical everywhere while `~/.config/herdr/` runtime stays machine-local. Project skills still come from each project's APM manifest, not here.

### Omnigent (per workspace machine)

Omnigent is a local agent runtime. Its configuration is versioned here as a template, but it runs only on workspace machines (mac/vps) — **not in remote Claude Code sessions** (web / ephemeral containers), which must keep no footprint. There is no plugin, marketplace entry, or SessionStart hook; install it once per workspace machine:

```sh
~/.dotagents/patches/omnigent/bootstrap.sh [--server https://<server>:6767]
```

It (a) installs the `omnigent` CLI from the `mine` branch of the `kzarzycki/omnigent` fork (override with `OMNIGENT_SOURCE`) if it isn't already on PATH (no silent upgrade; move to the branch head with `uv tool install --reinstall "omnigent @ git+https://github.com/kzarzycki/omnigent@mine"`), (b) ensures `~/.omnigent/` (0700) and seeds `~/.omnigent/config.yaml` from `patches/omnigent/config.template.yaml` only if it's missing. omnigent owns the live file — it rewrites the per-machine `host:` block (host_id + hostname) and providers at runtime — so the bootstrap never overwrites an existing config and the file is never symlinked back into the repo. The script no-ops when `CLAUDE_CODE_REMOTE=true`. Idempotent; safe to re-run.

Requirements: `uv` (https://docs.astral.sh/uv/). For the claude/codex/pi harnesses: Python 3.12+, Node.js 22 LTS+ with `npm`, `tmux`, and `bwrap` on Linux (`apt install bubblewrap`) — the script warns about any that are missing rather than failing. After bootstrap, run `omnigent setup` to log in the `claude`/`codex` CLIs and populate credentials. Secrets stay machine-local (OS keychain / `omnigent setup`) and are never committed — the template carries no keys and no host_id.

`--server` also installs the host service (`omnigent host enable`). That command bakes the calling process's `PATH` into the launchd plist or systemd unit, so a run from ssh or a script leaves a host that is online but finds no harness. The script therefore adopts the login shell's `PATH` first (on macOS it adds Homebrew to `~/.zprofile` when missing, since a second macOS user shares `/opt/homebrew` without `brew shellenv`). On every run it checks that the installed service's `PATH` resolves `claude` and `tmux` (plus `bwrap` on Linux) and exits 1 naming what is missing.

It also installs `~/.local/bin/omnigent-update` (`patches/omnigent/update.sh`), which brings the machine to the head of the fork's `mine`: it installs nothing unless that head is signed by a key in `~/.config/omnigent/allowed_signers` (seeded once from `patches/omnigent/allowed_signers`, never overwritten), pins Python dependencies to the fork's `uv.lock`, reinstalls the host CLI from a local checkout and, on the server machine, starts root's `omnigent-deploy` unit to rebuild and restart the server. It changes nothing while another session was active in the last 10 minutes on what the restart would kill, refuses to reset away commits that are on no origin branch, and restarts detached 20s later so the session running it can report. `--check` only reports. Each machine runs it from an Omnigent scheduled task a few times a night; the fork itself is rebased onto upstream by the `audit-sync` scheduled task on the VPS (see the fork's `.claude/skills/audit-sync`).

The server's deploy belongs to root, so no agent needs the `docker` group, which is root-equivalent. Install it once with `sudo ~/.dotagents/patches/omnigent/server/install.sh`. It moves the compose file and `.env` (they hold the database password and cookie secret) to `/etc/omnigent/` with mode 0600, and installs `/usr/local/sbin/omnigent-deploy` with its oneshot unit. The script checks the signature of `mine`'s head against `/etc/omnigent/allowed_signers` in a root-owned checkout, `/srv/omnigent/source`, then builds and restarts the server. A sudoers line lets the agent user run exactly `sudo systemctl start omnigent-deploy.service`, and nothing else. Agents still write the code on `mine`. They can't touch the compose file, so a change to the code can't mount the host or run privileged.

Manual steps the script cannot do:

- Start `claude` once in a terminal and clear every first-run prompt. Native sessions run the CLI inside tmux and stall on any dialog they cannot answer.
- macOS: the service runs in the user's desktop session (`gui/<uid>`), so that user must stay logged in (switch users, don't log out; log in again after a reboot). CLI logins live in that session's keychain, which is why `claude auth status` over ssh reports logged out while the service works.

### dev marketplace (live local plugins)

`home/.claude/settings.shared.json` declares a `dev` directory marketplace at `~/dev` and wires a SessionStart hook that runs `patches/dev-marketplace/apply.sh`, which:

1. Symlinks `~/dev/.claude-plugin/marketplace.json` to the repo-tracked copy at `patches/dev-marketplace/marketplace.json` — the marketplace definition is versioned here, not a loose machine-local file.
2. For every installed `<name>@dev` plugin with a local `./agents/repo/plugin` source, symlinks its plugin-cache install dir to the working tree under `~/dev` — editing the plugin source plus `/reload-plugins` is enough, no re-copy or push.

To add a plugin: add its `./agents/repo/plugin` entry to `patches/dev-marketplace/marketplace.json`, then enable `<name>@dev` in the consuming project's Claude settings. The hook is a silent no-op on machines without `~/dev` or without the plugin's source repo.

### Remote sessions (Claude Code on the web)

Cloud sessions run in an ephemeral container, so dotagents re-applies the user baseline per container build. Project capabilities remain the repository's responsibility.

**How it fits together.** The harness runs the environment's setup script before Claude Code launches. `bin/remote-setup.sh` runs `dotagents install --profile remote`, writing user-scope settings and hooks. The repository setup installs and compiles its own APM dependencies. The harness keeps git-identity and stop-gate hooks in a separate layer; Claude Code merges hooks across layers.

**The `remote` profile (`settings.remote.json`)** disables local development plugins and sets `CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1`. Shared bootstrap hooks stay wired but self-guard to a silent no-op when their infrastructure is absent.

**Delivery — private repos need the harness credential.** A fresh container can clone *public* GitHub repos directly (the default **Trusted** network policy allowlists `github.com`), so public marketplace plugins install with no extra config. A *private* repo can only be cloned with the scoped credential the harness wires for repos **added to the environment** — a plain `git clone` or `raw.githubusercontent` fetch of a private repo fails in the sandbox. So:

- Add **`kzarzycki/dotagents`** to the environment's repositories — the harness checks it out into the workspace, and `remote-setup.sh` finds and installs from that checkout.
- Add any private capability repository referenced by the project's `apm.yml`.

Then paste this into the environment's **Setup script** field (Claude Code on the web → environment settings):

```sh
bash "$(ls -d "$HOME"/*/dotagents/bin/remote-setup.sh /home/*/dotagents/bin/remote-setup.sh 2>/dev/null | head -1)"
```

`remote-setup.sh` is idempotent: it ensures `jq`, finds the dotagents checkout, then runs `dotagents install --profile remote`. The setup script's filesystem is snapshotted and reused, so later sessions start instantly — but it only re-runs when you edit the environment or the snapshot expires (~7 days), never on resume.

**Per-session freshness.** Because the setup step is cached, a SessionStart hook (`patches/remote/refresh.sh`, gated on `$CLAUDE_CODE_REMOTE`) runs `git pull --ff-only` on `~/.dotagents` each session. User instruction and command changes resolve through symlinks; settings changes need a rebuild because Claude Code reads them at launch.

**Configure once.** Environments are reusable across sessions; set this one as the `--remote` default with `/remote-env` in your terminal.

## Local overrides

Machine-class config belongs in the committed profile overlay (`home/.claude/settings.<profile>.json`); `~/.claude/settings.json` is generated from the repo, not a free local file. Truly per-machine state, never committed:

- `~/.dotagents-profile` — single line naming this machine's profile
- Runtime prefs Claude writes into `~/.claude/settings.json` — machine-local until the next install resets them
- Files matching `*.local.*`, `.env*` under managed dotdirs — left alone by install

### Secret scanning

The repo ships a `.gitleaks.toml` (default ruleset, `useDefault = true`) so `gitleaks dir .` and `gitleaks git .` confirm no token, key, or credential ever lands in the tree or history — both scan clean today. Secrets belong in the machine-local `.env*` / `*.local.*` files install skips, never in committed config. The one ID-shaped value present, `BRANDFETCH_CLIENT_ID` in `settings.mac.json`, is a public client identifier (sent in client-side logo-API URLs), not a secret.

The scan runs automatically: `.githooks/pre-commit` blocks any commit that stages a secret (gitleaks), invalid JSON (would break `install`'s `jq` merge), or a dangling in-repo symlink (the class of bug that once shipped a broken `commands/flow` link) — the repo invariants previously left to a human to eyeball. `dotagents install` enables the hook by pointing `core.hooksPath` at `.githooks`; since that's per-clone local config, a fresh clone arms it on the first install. `gitleaks` is the only extra dependency (`brew install gitleaks`); the hook degrades to a warning if it's absent.

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
