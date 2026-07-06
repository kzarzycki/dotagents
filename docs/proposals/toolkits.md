# Change proposal: Toolkits — per-project-group context bundles

## Problem

All context is global. Every session in every project loads all 11 MCP servers
(~/.claude.json), all enabled plugins/skills (settings.shared.json), and the full
CLAUDE.md. A quick chat in a scratch dir carries minecraft, cookidoo, playwright,
M365, PDLC workflow skills — ~50k tokens of tool schemas and skill headers it will
never use. Deferred tool loading softens the cost but the skill list, plugin
commands, and hooks still land in every context window.

## Goal

Group projects into **toolkits** (name chosen: a toolkit is what you carry to a
job). A toolkit bundles:

- MCP servers (definitions, incl. local-vs-remote and paths — machine facts)
- enabled plugins (→ skills, commands, agents)
- a CLAUDE.md fragment
- optionally: preloaded skills, env vars, permissions

A project declares *only a toolkit name*. Everything else — where the MCP runs,
which marketplace a plugin comes from — is resolved by the environment (dotagents
on this machine). The declaration is one committed line, so copier templates can
stamp it (`toolkit: minecraft`).

Example toolkits: `base` (always on: memsearch, statusline, core skills),
`personal` (todoist, gog, cookidoo), `minecraft`, `knowledge` (perplexity, tavily,
exa, research skills), `xebia-slides` (M365, powerpoint-mcp, content skills),
`xebia-skills-dev` (playwright, dev plugins), `chat` (nothing beyond base).

## Options

### A. Generated local overlay (recommended)

Toolkit definitions live in dotagents. A materializer writes **gitignored** files
into the project; Claude Code picks them up natively.

```
dotagents/
└── toolkits/
    ├── base/                    ← implicitly merged into every toolkit
    │   ├── toolkit.json         ← { mcpServers, enabledPlugins, env, permissions }
    │   └── CLAUDE.md
    ├── minecraft/
    │   ├── toolkit.json
    │   └── CLAUDE.md
    └── ...
```

Per-machine MCP variance (local vs remote, paths) is handled the same way profiles
already work: `toolkit.json` + optional `toolkit.<profile>.json` overlay.

In the project, committed:

```
.agents-toolkit        ← one line: "minecraft"
```

Materialization — `dotagents apply` (run in the project) or automatically by a
SessionStart hook that notices `.agents-toolkit` and a stale/missing overlay:

- `.claude/settings.local.json` ← enabledPlugins (base ∪ toolkit, everything else
  `false`), env, permissions. Already gitignored by Claude Code convention.
- `.mcp.json` ← toolkit MCP server definitions; added to `.git/info/exclude` by
  the materializer so machine facts never enter git.
- Toolkit CLAUDE.md fragment: NOT materialized as a file. The SessionStart
  hook reads `.agents-toolkit`, loads `toolkits/<name>/CLAUDE.md` live from
  dotagents, and injects it as additionalContext. Never stale, zero project
  files. (Global `~/.claude/CLAUDE.md` shrinks to the base spec; toolkit
  fragments layer on top per project.)
- Skill preloading folds into the same hook: `preloadSkills` in toolkit.json,
  inlined into the same additionalContext payload. `preload-skills.txt` +
  `preload-skills.py` are deleted; today's global preloads move to the base
  toolkit, and toolkits override (minecraft preloads minecraft-building,
  chat preloads nothing). One hook assembles the whole session context.

Global config shrinks: `~/.claude.json` mcpServers empties out (moved into
toolkits); `settings.shared.json` enabledPlugins keeps only base plugins.
Projects with no `.agents-toolkit` get `base` — the whole point is that the
default is lean.

Copier: template stamps `.agents-toolkit` with the project type's toolkit name.
Done — no paths, no server types in the template.

- **Pros**: uses only native Claude Code mechanics (project settings precedence,
  `.mcp.json`, local files); works from IDE, `claude` CLI, anything — no launcher
  wrapper; declaration is committable and copier-friendly; machine facts stay out
  of git; other agents (Codex) can get their own materializer later against the
  same toolkit.json.
- **Cons**: generated files can go stale after editing a toolkit (mitigated: hook
  compares a hash stamp and regenerates); first session in a project needs one
  materialization pass.

### B. Launcher wrapper with per-toolkit flags

A `claude` shell wrapper reads a dir→toolkit map (or `.agents-toolkit`) and
launches `claude --settings <toolkit-settings.json> --mcp-config <toolkit.mcp.json>`.
Zero files in the project tree beyond the declaration.

- **Pros**: nothing generated, nothing stale; purest "environment decides".
- **Cons**: only works through the wrapper — IDE extension, `claude -r`, web,
  subagent respawns bypass it; `--settings` merge semantics are less battle-tested
  than the settings hierarchy; silent fallback to full-global when bypassed defeats
  the purpose.

### C. Separate CLAUDE_CONFIG_DIR per toolkit

`cc minecraft` → `CLAUDE_CONFIG_DIR=~/.claude-toolkits/minecraft claude`. Total
isolation: history, plugins, MCPs, settings per toolkit.

- **Pros**: hard isolation, trivially reasoned about.
- **Cons**: N plugin installs, N credential stores, N histories; dotagents install
  becomes N-fold; memsearch/session continuity fragments; IDE launches need env
  plumbing. Heavy for what is a context-trimming problem.

### D. Commit full config per project

Commit `.mcp.json` + `.claude/settings.json` in each repo. Rejected by
requirement: hardcodes server locations/types in git.

## Recommendation

**A.** It is the only option that is simultaneously: native (no wrapper to
bypass), git-clean (machine facts in gitignored generated files), declarative
(one-line committed toolkit name), and copier-ready. B is attractive but the
IDE/resume bypass hole is real. C solves a different problem (isolation, not
context weight).

For the template/commercial frame, the **Synthesis** section below layers APM
on top of this: A's mechanics become the binding layer, APM owns packaging and
versioning. A stands alone as the no-APM degraded mode.

## Design details (Option A)

### toolkit.json shape

```json
{
  "extends": ["knowledge"],
  "mcpServers": { "minecraft": { "command": "...", "args": ["..."] } },
  "enabledPlugins": { "workflow@kzarzycki-agent-skills": true },
  "env": {},
  "permissions": { "allow": [] },
  "preloadSkills": []
}
```

`base` is always merged first; `extends` allows composition (e.g. `xebia-slides`
extends `office`). Keep nesting to one level — if extends chains grow, the
taxonomy is wrong.

### Disabling the global residue

Materialized `settings.local.json` must actively turn *off* plugins the shared
settings turn on, since project settings override user settings per key. The
materializer emits `"<plugin>": false` for every shared-enabled plugin not in the
toolkit. Global `~/.claude.json` mcpServers migrate into toolkits in one cutover
commit; anything left global stays loaded everywhere by definition (only
account-level claude.ai connectors — Drive, M365 — cannot be scoped this way;
scope those via claude.ai settings if needed).

### Staleness

Materializer writes a stamp (`sha256` of merged toolkit config) into the
generated file. SessionStart hook: read `.agents-toolkit`, hash current toolkit
def, compare, regenerate on mismatch. First session after a toolkit edit picks
up changes with zero manual steps; the hook is ~20 lines of python next to
`preload-skills.py`.

### Migration path

1. Add `toolkits/base/` = today's exact global config → behavior unchanged.
2. Carve out toolkits one at a time (minecraft first — most obviously scoped),
   moving MCP defs out of `~/.claude.json` and plugin enables out of shared
   settings as each toolkit absorbs them.
3. Drop `.agents-toolkit` files into existing project dirs as needed; no file =
   `base`.

### Codex support

The toolkit definition is agent-neutral (`toolkit.json` + CLAUDE.md fragment);
only the materializer is per-agent. Same `.agents-toolkit` byte drives both.

Codex reads **project-scoped `.codex/config.toml`** (trusted projects only;
walks project root → cwd, closest file wins), layered above user config
(developers.openai.com/codex/config-advanced, "Project config files"). So Codex
materializes symmetrically to Claude — a generated, gitignored project file:

- `.codex/config.toml` ← toolkit `[mcp_servers.<name>]` tables, plus
  `mcp_servers.<global>.enabled = false` for user-level servers not in the
  toolkit (dot-key disable is documented). Added to `.git/info/exclude`.
- Skills: Codex has a skills system (`docs/skills.md`, `[[skills.config]]`
  tables) — a toolkit skill dir can be registered per project the same way.
  Claude plugins that are skill-bundles can be dual-registered later; start
  Claude-only.
- Instructions: Codex reads repo `AGENTS.md`. Keep one neutral fragment per
  toolkit; for Claude it lands via the materializing hook, for Codex via
  generated `.codex/` instructions file (`model_instructions_file` resolves
  relative to the containing `.codex/`).
- Same no-hands freshness as Claude: Codex supports `SessionStart` hooks
  (user-level `~/.codex/hooks.json`, installed by dotagents — user-level so
  there's no bootstrap dependency on the generated project `.codex/` layer).
  The hook runs the same materializer: hash toolkit def, regenerate
  `.codex/config.toml` + instructions file on mismatch. Caveat both agents
  share: config files are read at startup, so a regeneration lands the
  *next* session — acceptable for a toolkit-edit event.

No wrapper, no `CODEX_HOME`, no profiles. (Codex "profiles" turn out to be
`~/.codex/<name>.config.toml` overlay files selected only by `--profile` —
project config is barred from selecting them — so they're the wrong tool here.)
Note: project `.codex/config.toml` cannot set provider/auth/notify keys — fine,
toolkits don't carry those.

Verified 2026-07-06 against openai/codex docs (config-advanced, config-reference);
independent deep-research report at `.work/claude-ai-toolkit-report.md` reaches
the same architecture (neutral manifest + per-agent transpilation at install
time) and details why APM's flatten-to-files approach breaks plugin identity
and lockfile integrity — reinforcing marketplace-pinning over vendoring.

### Version pinning per toolkit

Two toolkits may need different versions of the same MCP or plugin.

- **MCPs**: trivially solved by the design — each toolkit owns its full server
  definition, so `minecraft` can run `npx mc-mod@2.1.0` while `minecraft-beta`
  runs a local checkout. Nothing shared, nothing to coordinate. Machine variance
  stays in `toolkit.<profile>.json`.
- **Plugins/skills**: Claude Code pins plugins by *marketplace*, not by version
  string. The repo already exploits this (`workflow@dev` live tree vs
  `workflow@kzarzycki-agent-skills` published). Generalize: dotagents can
  register N marketplace checkouts at different refs (the dev-marketplace patch
  pattern — a checkout pinned to a sha is just another marketplace dir), and a
  toolkit enables `plugin@<that-marketplace>`. This keeps plugins as plugins —
  no flattening into vendored skill files (the Microsoft APM failure mode).
  Cost: one extra checkout per pinned ref, managed by a small
  `pinnedMarketplaces` section in the toolkit or a dotagents-level registry.

## Comparison with Microsoft APM

Frame: dotagents is a copyable template (copier-instantiable per person/team),
not just this machine's setup. APM commits `apm.yml` + lockfile per project
repo. The structural difference — **per-person environment vs per-repo
package** — drives every row; plugin flattening is treated as minor here.

| Dimension | dotagents template + toolkits | APM |
|---|---|---|
| Distribution unit | Environment per *person* (one install, all their projects) | Package set per *repo* (one install, all its contributors) |
| Onboarding a person | Clone template, `dotagents install` once → every project works | Nothing personal, but `apm install` in each repo |
| Onboarding a repo | One `.agents-toolkit` line | Author `apm.yml`, generate lockfile |
| Update propagation | One template commit → everyone, all projects, next session | Version bump + re-install per repo; N repos = N PRs |
| Drift model | Template copies diverge (copier-update problem) | Repos lockfile-exact but frozen — staleness, not divergence |
| Runtime freshness | Self-healing per session (hook rematerializes) | Static after install |
| Personal/machine facts (local vs remote MCP, auth, paths) | First-class (profiles, overlays) | Not modeled; must be parameterized out of committed manifests |
| Mixed-team reality (client staff you don't control) | High ask: every contributor must adopt your environment repo | Only needs the CLI; config rides the repo they already cloned |
| Governance | Convention + template code review | Enforced policy engine (tighten-only inheritance, transitive-MCP gating) |
| Compliance artifacts | Template git history | SHA lockfile, licenses, SBOM export |
| Security scanning | DIY | Built-in (payload scanning, trust prompts) |
| Local tinkering | Free — edit toolkit, next session has it | Breaks lockfile verification; override story unresolved |
| Agent coverage | Own materializers (Claude + Codex; you extend) | claude/codex/copilot, Microsoft-maintained |
| Ownership/vendor | Self-owned scripts | Young MS project's roadmap |
| Ecosystem afterlife | Client keeps a fork of your template | Client keeps a standard format with third-party tooling |

They compose rather than compete: template-instantiated environments for
people you staff; toolkit defs are a neutral manifest, so a `dotagents export`
could emit `apm.yml` (or plain committed `.mcp.json` + settings) for client
repos that outlive the engagement.

## Synthesis: APM-managed toolkits

Designed from scratch against the full requirement set (context scoping,
no machine facts in git, copier-stampable, Claude+Codex, per-toolkit versions,
team/commercial distribution). The result is three layers, each owning exactly
one concern the earlier options conflated:

```
┌─ Layer 3: Binding (environment; slim dotagents) ─────────────┐
│  project → toolkit; MCP name → machine implementation;       │
│  session-start hooks (Claude + Codex) materialize & refresh  │
├─ Layer 2: Toolkits = APM meta-packages ──────────────────────┤
│  one apm.yml + apm.lock.yaml per toolkit; pins versions of…  │
├─ Layer 1: Packages (APM) ────────────────────────────────────┤
│  skills, prompts/instructions, agents, MCP def templates,    │
│  plugins — versioned, locked, policy-governed, git-hosted    │
└──────────────────────────────────────────────────────────────┘
```

### Layer 1 — packages

Everything shareable becomes an APM package in a git repo: each skill bundle,
subagent def, instructions fragment, MCP definition template, plugin. APM owns
what it is good at: SHA-pinned lockfiles, transitive-trust gating, policy
enforcement, SBOM. Nothing here is machine-specific.

### Layer 2 — a toolkit is itself an APM package

A toolkit is an APM meta-package: an `apm.yml` whose dependencies are the
packages it composes, pinned per-toolkit (two toolkits pinning different SHAs
of the same skill = plain APM dependency resolution — requirement solved
natively), plus the toolkit's instructions fragment as a prompt package, with
`targets: [claude, codex]`. Each toolkit repo carries its own lockfile, so a
toolkit is reproducible and shareable as a unit — a colleague installs
`toolkit-xebia-slides` and gets byte-identical agent behavior.

MCP entries in a toolkit are declared **by name against an interface**, with an
optional portable default (`npx pkg@1.2.0`). The concrete implementation —
local command vs remote URL, paths, auth env — is *not* in the package.
That's Layer 3's job (dependency injection: packages declare needs,
environment provides implementations).

### Layer 3 — binding (what remains of dotagents)

Slim environment layer, still a copyable template:

- **Project→toolkit binding**, two modes, same toolkit package:
  - *environment-bound* (personal fleet): project commits one pointer line
    (`.agents-toolkit`); toolkits are installed centrally once
    (`~/.agents/toolkits/<name>/`, `apm install --frozen` there); the
    session-start hook materializes into the project. Project repo stays
    clean; N projects share one install.
  - *repo-bound* (client/team repos): project commits its own tiny `apm.yml`
    depending on one toolkit package. Teammates need only APM, not your
    environment. This is the committed-manifest column of the comparison
    table, opted into per repo.
- **MCP implementation registry** (`~/.agents/mcp-registry` + per-profile
  overlays): maps toolkit-declared MCP names to this machine's real
  definitions, overriding package defaults. Machine facts live only here.
- **Session-start hooks on both CLIs** (user-level, so no bootstrap
  dependency): compare lockfile/def hashes; re-run `apm install --frozen` and
  regenerate the gitignored runtime files (`.claude/settings.local.json`,
  `.mcp.json`, `.codex/config.toml`) only on mismatch; inject the toolkit
  instructions fragment as additionalContext. Self-healing on both agents,
  near-zero cost when nothing changed.
- **Copier**: stamps the binding — pointer file for environment-bound project
  types, apm.yml for repo-bound ones.

### Context scoping falls out for free

APM deploys toolkit content *into the project* (`.claude/`, `.codex/`), so a
session loads base + exactly its toolkit — the scoping the whole proposal is
for, achieved by locality instead of enable/disable gymnastics. Global config
shrinks to near-empty base; the hook's residue-disabling
(`enabledPlugins: false`) remains only for whatever must stay user-global.
Plugin flattening at deploy time is accepted as the known minor cost; plugins
remain plugins at authoring, packaging, and versioning time — only the
deployed form is files. If Claude grows project-scoped plugin installs, the
materializer switches to that and the cost disappears.

### What each side contributes

- APM: versioning, lockfiles, distribution, transitive trust, policy, SBOM —
  everything a consulting engagement needs to hand over.
- Toolkits: the grouping concept ("projects sharing a goal share a bundle"),
  machine-fact injection, session-start freshness, dual-CLI symmetry,
  one-line project declarations.

### Costs and risks

- Two systems to operate (APM + environment hooks) instead of one.
- APM maturity: young project; pin the APM version itself in the template and
  keep the Layer-3 materializer able to consume raw toolkit repos directly
  (git checkout + own transpile) as a degraded mode if APM breaks — the
  pre-synthesis Option A is exactly that fallback, so nothing is wasted.
- `apm install` latency at session start — mitigated by frozen installs gated
  on hash change.
- Open: whether APM's MCP primitives tolerate name-only declarations with
  environment-supplied definitions, or need a variable-substitution shim in
  the materializer.

### System-prompt shaping per toolkit

Supported today: `outputStyle` in generated `settings.local.json` — a toolkit
(e.g. `chat`) can ship a lean chat/research output style that replaces the
behavioral section of the system prompt. Full system-prompt replacement exists
only as a CLI flag (`--system-prompt`), which reintroduces the launcher-wrapper
bypass problem — deferred; revisit if Claude Code grows a settings-level knob.

## Open questions

- ~~Verify `enabledPlugins: false` in project `settings.local.json` suppresses
  a user-level `true`~~ — verified 2026-07-06: headless session in a dir with
  the override sees no superpowers skills; control dir does.
- ~~CLAUDE.md fragment carrier~~ — decided: hook additionalContext (live read,
  no staleness, no generated file).
- Should `.agents-toolkit` be a key inside committed `.claude/settings.json`
  instead of its own file? Own file keeps it agent-agnostic (Codex later reads
  the same byte).
- ~~Codex: do profiles scope `mcp_servers`?~~ — moot; project-scoped
  `.codex/config.toml` is the mechanism (verified in Codex docs, see above).
