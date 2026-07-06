# dev/ refactor: ownership directories, stacked toolkits, APM packaging, copier hookup

## Model

Two orthogonal axes, encoded separately:

- **Ownership/audience** → directory placement. `personal/`, `xebia/`, `agents/`, `ext/`, `trading/`, `archive/`. Stable; a parent-level `.agents-toolkit` sets the group default.
- **Capability** → toolkit stack. `.agents-toolkit` holds one or more whitespace-separated toolkit names, merged left-to-right (lists union, later wins on scalars). A child repo needing a different profile writes its own file listing the **full stack** (e.g. `xebia playwright`) — child replaces parent, no walk-up accumulation.

Toolkit inventory after this work: ownership bases `personal`, `xebia`, `agents`, `base` (ext default) + capability overlays `dev`, `playwright`, `chat`, `research`. Existing `flowbench` toolkit stays as a per-repo override.

## Target layout

Non-dev work (chat-driven, documents, knowledge bases — no code) leaves `~/dev` entirely: personal non-dev to the existing `~/personal/`, Xebia non-dev to a new `~/xebia/`. Toolkit anchoring is walk-up, so those roots carry parent `.agents-toolkit` files too. `~/dev` keeps code repos only. Phase 2 classifies each entry dev vs non-dev (code manifests present vs mostly documents).

| Group | Toolkit default | Members |
|---|---|---|
| `~/xebia/` (non-dev) | `xebia` | `projects/`→`~/xebia/consulting/` (decks, presales, offerings), `kb/team-xebia-cee` |
| `dev/xebia/` | `xebia dev` | existing children (`feedbacks-app`, `flowbench-scenarios`, `flowbench-runs`), `xebia-ai-skills`, `xebia-rfp-toolkit` |
| `dev/agents/` | `agents` | `dotagents`, `agent-skills`, `agent-skills-private`, `project-templates`, `Auto-Claude`, `claude-kanban`, `CLI-Anything`, `codex-enhanced`, `spec-kit`, `simonc602-agentic-os`, `cloud-harness`, `flowbench` (override: `flowbench`), `mcp servers: outlook-mcp, powerpoint-mcp, akiflow-mcp, brave-browser-control` under `dev/agents/mcp/` |
| `~/personal/` (non-dev) | `personal` | existing `dev/personal/` content, `kb/personal`, `personal-finance`, `invoice-automation` (if non-dev per Phase 2) |
| `dev/personal/` | `personal dev` | `life-os`, `cookidoo-recipes(+mealplan)`, `OverKeys`, `xkb-lens`, `lego-sorter`, `computer`, `hetzner-vps` |
| `ext/` | `base` | unchanged (upstream clones) |
| `trading/` | `personal` | unchanged in place |
| `archive/` | none | + `ai-flink-app`, `claude-code-hooks-mastery`, `streaming-ai-demo` (top-level; likely duplicate of `projects/streaming-ai-demo` — Phase 2 confirms), `reversing`, `agentdesk`, `dotagents-omnigent-wt` |
| delete/relocate | — | stray `node_modules/`, `Visual Studio Code - Insiders.app`, `screenshots/` |

Final classification of each repo is confirmed in Phase 2 before any move (remote, dirty state, audience).

## APM packaging

- Each `toolkits/<name>/` in dotagents becomes an APM package: `apm.yml` beside `toolkit.json` declaring skills/instructions/MCP names (pattern spiked on `toolkits/flowbench`).
- dotagents remains the published home (roadmap Epic 2). Sharing-ready repos (`xebia/*` with external audience, `agent-skills`, `project-templates`) commit an `apm.yml` referencing the git-hosted toolkit package, so a colleague runs `apm install` without dotagents. MCP credentials stay `${env:VAR}` placeholders.
- Personal repos commit only `.agents-toolkit` (one line). All materialized output (`.mcp.json`, `.claude/settings.local.json`, skills symlinks, `.codex/config.toml`) stays gitignored and machine-local.

## Copier

`project-templates` (existing copier repo) gains `.agents-toolkit` templating and optional `apm.yml` for shared projects. Existing adopters (`flowbench`, `cloud-harness`, `xebia/flowbench-scenarios`) get the new files via `copier update`; their `.copier-answers.yml` `_src_path` is rewritten to the template repo's new location.

## Reference migration (moves rewrite these)

- `~/.claude.json` project entries keyed by absolute path (193 entries)
- Claude plugin dev-marketplace registrations pointing at `agent-skills` working tree
- dotagents symlinks under `~/` and hook command paths — dotagents moves **last**, then `bin/dotagents install` + `doctor` re-anchor everything
- `.copier-answers.yml` `_src_path` in the three adopters
- memsearch collections derived from repo paths
- tmux session cwds, cron/launchd entries, shell rc references — grep sweep for `/Users/zarz/dev/<old-name>` across `~/.claude*`, `~/.agents`, `~/.codex`, `~/Library/LaunchAgents`, crontab, rc files

Verification after Phase 3: full-sweep grep for every old path returns nothing; `dotagents doctor` clean; V1 in one repo per group.

## Execution phases and model delegation

1. **Materializer + toolkits** (dotagents; multi-name pointers, overlays, apm.yml, tests) — sonnet agent, verify V3 + V1.
2. **Classification sweep** — haiku fan-out per repo: remote, dirty, audience; output move manifest. Cheap, parallel.
3. **Moves + reference migration** — main agent, scripted, not delegated (destructive); verify as above.
4. **Per-repo binding + shared apm.yml** — sonnet fan-out, one agent per group dir; V1 per group.
5. **Copier template + `copier update` adopters** — sonnet; verify generated files + `git diff` in adopters.

Each phase gates the next on its verification passing.
