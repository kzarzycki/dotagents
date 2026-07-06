# dotagents roadmap

Long-term plan: epics broken into stories a weaker model can pick up and execute one at a time. Each story states its files and a `Verify:` line built from the shared verification methods (V1–V5) — do the story, run the verification, stop. Read `README.md` and `docs/proposals/toolkits.md` before touching anything.

## What this project is becoming

Today: one person's agent config — symlink installer (`bin/dotagents`), per-machine profiles, SessionStart hooks, and the toolkit system (`home/.claude/hooks/toolkit.py` + `toolkits/`) that materializes per-project MCP servers, plugins, and skills from a committed definition. Direction: the same machinery, hardened and documented well enough that a colleague can clone it, strip the personal parts, and run their own instance — a pattern to copy, not a shared service to operate.

## Principles (apply to every story)

- Extend existing structure; a new file, config key, or abstraction carries the burden of proof.
- No speculative flexibility. If a story says "add X", add X for the one caller that exists.
- Everything the installer or hooks write must be idempotent and machine-local (gitignored or outside the repo).
- Secrets never in the repo: registry placeholders + `~/.agents/mcp-registry.local.json` is the pattern; follow it.
- Every story ends with a runnable verification (`Verify:` line, referencing the shared methods below). If you can't verify it, split or drop the story.

## Verification methods (shared)

Stories reference these as `Verify: V<n>`. Run exactly as written; paste command + output in your report.

- **V1 — re-materialize a toolkit.** In the target dir: `rm -f .claude/.toolkit-stamp && echo '{"cwd":"'"$PWD"'"}' | python3 ~/dev/dotagents/home/.claude/hooks/toolkit.py`. Read the `systemMessage` line (toolkit name, "materialized", loaded/missing skills, missing MCPs). Then inspect outputs: `python3 -c "import json;print(list(json.load(open('.mcp.json'))['mcpServers']))"`, plus `.claude/settings.local.json`, `ls -la .claude/skills/`, `.codex/config.toml`.
- **V2 — interactive tool-visibility probe.** Headless `claude -p` is unreliable for extension-bridge tools (always answers NO) — use tmux: `tmux new-session -d -s probe -x 200 -y 50`; `tmux send-keys -t probe "cd <dir> && claude" C-m`; wait ~8s (`tmux capture-pane -t probe -p` to watch); an MCP-approval dialog may appear — send Enter; then send the probe question (e.g. `Is any tool named mcp__claude-in-chrome__* available, even as a deferred tool? YES/NO`) followed by Enter; wait ~10s; `tmux capture-pane -t probe -p | tail -30` to read the answer; `tmux kill-session -t probe`.
- **V3 — test suite.** `cd ~/dev/dotagents && python3 -m pytest tests/` — must be green. For a new check/guard, also demonstrate it failing: seed the defect it targets, show the failure, remove the seed.
- **V4 — doctor run.** `~/dev/dotagents/bin/dotagents doctor`. Healthy machine: exit 0. To verify a specific finding fires: seed the defect in a scratch dir, run doctor, confirm the one-line finding, remove the seed.
- **V5 — commit-gate check.** In a scratch clone: `git clone ~/dev/dotagents /tmp/da-gate && cd /tmp/da-gate && git config core.hooksPath .githooks`; stage the offending content, `git commit -m test` must fail; revert, a clean commit must pass; `rm -rf /tmp/da-gate`.

## Non-goals (do not build these)

- No daemon, server, sync service, or cloud component. Install is `git pull` + symlinks; stay there.
- No GUI/TUI. Plain CLI output.
- No plugin/marketplace system of our own — Claude Code plugins already exist; toolkits only reference them.
- No support matrix for agents nobody here uses. Claude Code and Codex until a third is actually adopted.
- No abstraction layer over settings formats "in case they change".

---

## Epic 1 — Harden the toolkit system

Goal: the toolkit hook is trusted infrastructure — tested, observable, no known sharp edges. Carries the open items from `.work/handoff-toolkit-followups.md`.

- **1.1 Unit tests for toolkit.py.** Extract nothing; test the module as-is with `pytest` + `tmp_path`. Cover: `find_toolkit_file` walk-up, `deep_merge_registry`, `expand_env_placeholders` (incl. unset var left as-is), `merge_settings_local` with `plugins=None` and `claude_in_chrome` both ways, stamp change → re-materialize. Files: new `tests/test_toolkit.py`, no changes to `toolkit.py` unless a bug falls out. Verify: V3.
- **1.2 Resolve the chrome-disable cache override.** `claudeInChromeDefaultEnabled: false` in `~/.claude/settings.json` is ignored when `~/.claude.json` carries cached pairing state (see handoff, open item 1). Investigate, fix or document the workaround in `docs/knowledge/`. Verify: V2 in a non-optin dir — answer must be NO; then V2 in `~/personal` (opt-in) to record whether per-project re-enable works (upstream bug #26204 may block it — report honestly).
- **1.3 Trim toolkit context under the 9.5KB soft limit.** Personal toolkit injects 10.7KB and warns. Options in order of preference: dedupe with `preload-skills.py` (both load the same skills today — inject once), then shorten skill bodies. Files: `toolkit.py`, maybe `settings.shared.json` hook order. Verify: V1 in `~/personal` — `systemMessage` has no size WARNING and still lists both preloaded skills.
- **1.4 `dotagents doctor` subcommand.** Read-only status: profile, symlink targets vs repo, settings.json drift vs generated merge, registry placeholders with missing env vars or missing `mcp-registry.local.json` overrides, stale toolkit stamps. Files: `bin/dotagents` (new case branch), nothing else. Verify: V4 — clean run on this machine, plus one seeded defect per finding type (e.g. temporarily unset an env var the registry references).
- **1.5 Stale-hook guard.** The trinity incident: machine-local `settings.local.json` referenced hook scripts deleted from the repo. Add a `doctor` check (extends 1.4): for each project under `~/dev` with `.claude/settings.local.json`, flag hook commands whose `${CLAUDE_PROJECT_DIR}`-relative script doesn't exist. Verify: V4 — seed a hook entry pointing at a nonexistent `.py` in a scratch repo; doctor flags it; clean machine stays silent.

## Epic 2 — Make it adoptable by colleagues

Goal: a colleague clones the repo (or a template of it), runs one command, and has working agent config — without inheriting Kris's personal MCP servers, skills, or instructions.

- **2.1 Separate personal from generic.** Audit `home/` and `toolkits/` for personal-only content (todoist, cookidoo, browser-local, gog-photos, personal AGENTS.md sections). Produce a list in `docs/adoption.md` — just the inventory, no restructuring yet. Verify: every file in `home/` appears in the doc classified generic/personal/mixed — cross-check with `find home -type f | wc -l` vs the doc's line count.
- **2.2 Bootstrap path for a new user.** Extend `README.md` with a "fork it" section: what to delete, what to edit (profile files, mcp-registry, AGENTS.md), the one install command, how to verify (`dotagents doctor` from 1.4). No new scripts. Verify: spawn a fresh-context agent, give it ONLY the README section, ask it to list the fork steps; its list must match the section without it reading source.
- **2.3 Template-ize the registry.** Ship `home/.agents/mcp-registry.json` with only generic servers (docs MCPs, search MCPs) and document the local-override pattern for private ones. Personal servers move to Kris's `mcp-registry.local.json`. Files: registry, `docs/adoption.md`. Verify: `grep -c zarz.net home/.agents/mcp-registry.json` returns 0; then V1 in `~/personal` — personal servers still materialize (proving the local override supplies them).
- **2.4 One worked example toolkit for a team repo.** Write `toolkits/example/` with comments explaining each key (plugins/mcp/skills/preloadSkills/claudeInChrome), referenced from the adoption doc. Verify: V1 in a scratch dir with `.agents-toolkit` containing `example` — no errors, no "NOT FOUND"/"NOT in registry" notes in the systemMessage.

## Epic 3 — Toolkit coverage for real work contexts

Goal: every recurring working context has a toolkit, so no session starts with wrong plugins/MCPs. Add toolkits only when a context actually recurs — never speculatively.

- **3.1 `xebia` toolkit.** Client-work defaults: M365/SharePoint-adjacent skills, no personal MCPs, conservative plugin set. Anchor in the client-work root (find it: dirs under `~/dev/xebia`). Files: `toolkits/xebia/{toolkit.json,CLAUDE.md}`. Verify: V1 in the anchored dir — toolkit name `xebia` in systemMessage, `.mcp.json` contains exactly the listed servers, no personal ones.
- **3.2 `research` toolkit.** Perplexity/tavily/exa/gemini MCPs + research plugin, nothing else. Verify: V1, same criteria as 3.1.
- **3.3 Toolkit inheritance — only if duplication hurts.** If three-plus toolkits repeat the same base list, add a single optional `"extends": "<name>"` key (one level, no chains) to `load_toolkit`. If duplication is two files copying five lines, skip this story permanently. Verify: V3 (new merge test) + V1 on one existing toolkit dir showing identical `.mcp.json` before/after (`diff` the two captures).

## Epic 4 — Codex (and next-agent) parity

Goal: the non-Claude agent on this machine gets the same per-project setup, to the extent it has equivalents.

- **4.1 Verify codex actually reads the generated config.** `.codex/config.toml` is written but untested end-to-end. Run codex in a materialized project, confirm MCP servers connect (esp. env-expanded values — handoff open item 4). Document findings in `docs/knowledge/`. Verify: in `~/personal`, run codex and list its MCP servers (`codex` equivalent of `/mcp`, or ask the session) — toolkit stdio servers present.
- **4.2 HTTP-server support in codex config.** `write_codex_config` only emits stdio servers today; browser-local/todoist (http) are silently dropped. Check codex's current MCP config format for http/headers support; emit if supported, else document the gap in the generated file's header comment. Verify: V1 in `~/personal`, then read `.codex/config.toml` — either the http server block is present (and 4.1's method shows it connecting) or the header comment names each skipped server.
- **4.3 Instructions injection for codex.** Toolkit CLAUDE.md fragments reach Claude via hook context. Codex supports user-level `SessionStart` hooks (`~/.codex/hooks.json`, per config-reference) — try registering the materializer there and/or emitting a `.codex/` instructions file (`model_instructions_file`, resolved relative to its `.codex/`); fall back to `AGENTS.md` append-with-markers only if neither injects context. Verify: V1 in `~/personal` twice in a row — markers appear once (idempotent), fragment text matches `toolkits/personal/CLAUDE.md`; then ask a codex session what toolkit is active.

## Epic 5 — Operability and safety

Goal: mistakes surface at commit time or install time, not mid-session weeks later.

- **5.1 CI for the repo.** GitHub Action: JSON validity for all committed `.json`, `python3 -m pytest`, `bash -n bin/dotagents`, gitleaks. Reuse the existing pre-commit config rather than duplicating rules. Files: `.github/workflows/ci.yml`. Verify: run the workflow locally first (`act` if available, else run each step's command by hand); then push a branch with a deliberately broken JSON — CI red; fix — CI green.
- **5.2 Secret-placeholder lint.** Pre-commit check (extend `.githooks/`): any committed registry value matching a credential shape (long hex, `Bearer `, `sk-`…) fails unless it's a `${env:...}` placeholder. Verify: V5 with a fake 64-char hex value in the registry as the offending content.
- **5.3 Install dry-run in CI.** Run `bin/dotagents install --dry-run --profile vps` in CI against a scratch `$HOME`; fail on CONFLICT lines or nonzero exit. Catches payload/skip-pattern regressions. Verify: reproduce the CI step locally with `HOME=$(mktemp -d) bin/dotagents install --dry-run --no-pull --profile vps`; exit 0 and no CONFLICT lines; then confirm the pushed workflow is green.

---

## How to pick up a story (instructions for the executing agent)

1. Read this file, `README.md`, and — for Epic 1 — `.work/handoff-toolkit-followups.md`.
2. Do exactly one story. Its "Files:" line is the expected blast radius; touching more needs a stated reason.
3. Run the story's `Verify:` line — the V<n> references resolve to the "Verification methods (shared)" section above; follow them literally. Paste the commands and output in your report.
4. Never commit secrets, never edit machine-local files under `~` except where the story says so, no commits unless asked.
5. If the story's premise turned out false (e.g. 3.3's duplication never materialized), report that and stop — don't build it anyway.

Ordering: Epic 1 first (1.1 and 1.4 unblock everything else's verification). Epics 2–4 are independent of each other. Epic 5 any time after 1.1.
