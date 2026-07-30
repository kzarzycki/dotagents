# APM + fnox Example Project Implementation Plan

> Execute this plan in the `project-templates` repository. Keep the existing dotagents toolkit edits out of its commits.

**Goal:** Make the Copier templates generate a small Claude Code/Codex project agent layer, then commit one generated example that shows project-owned APM, fnox, MCP, and native CLI authentication configuration.

**Ownership boundary:** Copier generates structure, safe defaults, and named mise tasks. The generated repository owns its instructions, skills, MCP definitions, CLI dependencies, endpoints, fnox profiles, provider references, and agent-specific additions. Copier does not install packages, contact secret providers, run APM, choose a company backend, or copy credentials.

**Target stack:** Copier, mise as the only repository task runner, APM 0.23.1 for the first qualification pass, fnox pinned through mise after CLI qualification, Python 3, Claude Code, Codex.

## Task 1: Record native tool authentication in the design

**Files:**

- Modify: `/Users/zarz/dev/agents/dotagents/docs/superpowers/specs/2026-07-10-apm-repo-agent-layer-design.md`

1. Add a requirement for tool-managed native authentication. It must permit credentials stored by a CLI in the OS credential store and require the agent layer to invoke that CLI without extracting, copying, or persisting its credential.
2. Broaden environment binding language so bindings can be environment variables, native tool auth, files, sockets, or workload identity.
3. Add an acceptance scenario using `gh auth status`: no `GITHUB_TOKEN`, no `gh auth token`, and no credential copied into fnox.
4. Update requirement/AC counts, traceability, validation gates, and Definition of Done.
5. Verify identifiers and counts:

```sh
rg -o 'ENV-[0-9]{2}' docs/superpowers/specs/2026-07-10-apm-repo-agent-layer-design.md | sort -u
rg '^### AC-[0-9]+' docs/superpowers/specs/2026-07-10-apm-repo-agent-layer-design.md
rg 'GITHUB_TOKEN|gh auth token|gh auth status|native auth' docs/superpowers/specs/2026-07-10-apm-repo-agent-layer-design.md
```

Expected: 29 unique requirements and 28 AC headings are present; traceability
names ENV-11 and AC-28; prohibited token extraction appears only as a
prohibition/test.

6. Commit only the design and plan:

```sh
git add docs/superpowers/specs/2026-07-10-apm-repo-agent-layer-design.md docs/superpowers/plans/2026-07-16-apm-fnox-example-project.md
git commit -m "docs: define project agent layer MVP"
```

## Task 2: Create an isolated implementation branch

**Repository:** `/Users/zarz/dev/agents/project-templates`

1. Confirm the source repository is clean:

```sh
git -C /Users/zarz/dev/agents/project-templates status --short
```

Expected: no output. Stop and ask before proceeding if it is dirty.

2. Create an isolated worktree in the writable temporary root:

```sh
git -C /Users/zarz/dev/agents/project-templates worktree add -b feature/apm-fnox-agent-layer /private/tmp/project-templates-apm-fnox HEAD
```

3. Run existing checks from `/private/tmp/project-templates-apm-fnox` and record their commands/results before changing files. Do not infer a test runner; use the commands in that repo's CI and README.

## Task 3: Replace toolkit questions with agent-layer questions

**Files:**

- Modify: `copier.yml`
- Modify: `.github/workflows/ci.yml`
- Test: the repository's existing Copier generation tests

1. Add or update a generation test that passes:

```yaml
include_agent_layer: true
include_fnox: true
```

The test must assert these generated paths and content:

```text
apm.yml
fnox.toml
.apm/instructions/project.instructions.md
mise.toml containing the agent tasks
```

It must assert `.agents-toolkit` and `scripts/agent-layer` are absent. Add a second generation case with `include_agent_layer: false` and assert the APM/fnox/instruction paths and agent task stanzas are absent.

2. Run the focused generation test. Expected: failure because the new questions/files do not exist.
3. In `copier.yml`, replace `toolkit_stack` and `shared_apm` with `include_agent_layer`. Make the agent layer require the existing mise option. Add `include_fnox`, asked only when `include_agent_layer` is true. Add conditional exclusions for APM and fnox paths.
4. Re-run the focused test. Expected: question parsing passes; file assertions may still fail until Task 4.
5. Do not run APM, fnox, Claude, Codex, or provider authentication from Copier hooks.

## Task 4: Scaffold the reusable files

**Files:**

- Modify: `templates/_base/_apm_yml.part`
- Modify: `templates/_base/_gitignore.part`
- Create: `templates/_base/_fnox_toml.part`
- Create: `templates/_base/_mise_agent_tasks.part`
- Create: `templates/_base/_project_instructions.md.jinja`
- Delete: `templates/_base/_agents_toolkit.part`
- Delete: each leaf template's `.agents-toolkit.jinja`
- Create in each of the eight leaf templates: `fnox.toml.jinja`
- Create in each leaf: `.apm/instructions/project.instructions.md.jinja`
- Modify each of the eight leaf templates' existing `mise.toml.jinja` to include `_mise_agent_tasks.part`
- Test: existing Copier generation tests and CI matrix

1. Extend the failing tests to inspect content:

- `apm.yml` targets only `claude` and `codex`.
- `dependencies.apm` and `dependencies.mcp` start empty.
- the instruction contains only `project_name` and `description` seed text.
- `fnox.toml` has strict exec-only behavior and no provider or secret.
- `.gitignore` includes `apm_modules/` and `fnox.local.toml`.
- `mise.toml` contains the four agent tasks directly and contains no wrapper-script reference.
- no generated file contains `dotagents`, `.agents-toolkit`, `1password`, `vault`, `GITHUB_TOKEN`, or a client endpoint.

2. Run the focused test. Expected: failure on missing wrappers/partials.
3. Implement common partials and thin leaf wrappers, following the existing `apm.yml.jinja` include pattern. Do not duplicate the shared file bodies across leaf templates.
4. Make the shared mise partial expose:

```text
agent-sync    install locked APM dependencies when a lock exists, then compile Claude and Codex
agent-check   validate APM output and parse generated JSON/TOML
agent-claude  launch Claude through fnox when fnox is enabled
agent-codex   launch Codex through fnox when fnox is enabled
```

Task bodies must fail on missing commands with a named remediation, pass arguments after `--` unchanged, and never read or print secrets. Freeze the final APM flags only after Task 5 qualification. Do not generate a wrapper script.
5. Run the focused and full Copier tests. Expected: both enabled and disabled cases pass across all leaves.
6. Commit:

```sh
git add copier.yml templates .github/workflows/ci.yml
git commit -m "feat: scaffold the repo agent layer"
```

## Task 5: Qualify the pinned CLIs

**Files:**

- Create or modify the repo's existing mise version file; extend it instead of adding a second tool-version mechanism.
- Modify: `templates/_base/_mise_agent_tasks.part`
- Modify: `templates/_base/_fnox_toml.part`

1. Capture current help for the installed APM version and candidate fnox version:

```sh
apm --version
apm install --help
apm compile --help
apm audit --help
mise latest fnox
mise x fnox@1.30.0 -- fnox --version
mise x fnox@1.30.0 -- fnox exec --help
mise x fnox@1.30.0 -- fnox check --help
```

Expected: APM reports `0.23.1`; fnox `1.30.0` is executable. If current registry state differs, record and pin the tested version rather than silently floating.

2. Create a disposable generated project under `/private/tmp` and try the exact `mise run agent-sync`, `mise run agent-check`, `mise run agent-claude -- --help`, and `mise run agent-codex -- --help` paths without provider access.
3. Adjust flags to the actual CLIs. Required behavior:

- first install may create a lock;
- later installs fail if the lock would change;
- compile targets Claude and Codex only;
- validation is noninteractive;
- fnox missing values fail rather than warn;
- fnox variables exist only in the launched child process.

4. Add mise-task regression tests for missing `apm`, argument forwarding, frozen-lock selection, and fnox-enabled/disabled launch branches. Use fake executables in a temporary `PATH`; no real agent session or provider access in automated tests.
5. Run those tests. Expected: all branches pass and captured fake-command arguments match the qualified CLI syntax.
6. Commit:

```sh
git add templates copier.yml .github/workflows/ci.yml
git commit -m "test: qualify agent layer launch commands"
```

## Task 6: Generate the example, then add project-owned configuration

**Files under:** `examples/agent-layer-mvp/`

**Generated framework files:**

- `apm.yml`
- `fnox.toml`
- `.apm/instructions/project.instructions.md`
- agent task stanzas in `mise.toml`

**Project-owned example files/configuration:**

- Modify the generated APM instruction with the canary behavior
- Add a local stdio MCP definition to `apm.yml`
- Add a non-secret local fnox profile/value to `fnox.toml`
- Create: `scripts/mcp_canary.py`
- Create: `scripts/check_native_auth.sh`
- Generate and commit: `apm.lock.yaml`, `AGENTS.md`, `.claude/rules/project.md`, `.mcp.json`, `.codex/config.toml`

1. Generate a `software/python` example:

```sh
BOOTSTRAP_TEMPLATE_SRC="$PWD" skills/bootstrap-project/scripts/bootstrap.sh \
  --name agent-layer-mvp \
  --type software/python \
  --dest examples/agent-layer-mvp \
  include_agent_layer=true \
  include_fnox=true
```

2. Before project customization, compare the four framework files with a fresh disposable generation. Expected: byte-for-byte match, proving the template owns only the skeleton.
3. Write failing canary tests first:

- `mcp_canary.py --probe` fails without the project profile value.
- the probe succeeds under `fnox --profile local ... exec` and prints only a fixed success marker, not the value.
- generated Claude and Codex MCP configs invoke the canary through fnox, limiting its environment to the MCP child.
- `check_native_auth.sh` fails if `GITHUB_TOKEN` is set.
- with `GITHUB_TOKEN` unset, it runs only `gh auth status`; a fake `gh` test confirms it never invokes `gh auth token`.

4. Implement the project-owned canary, MCP, fnox profile, and auth check. Use `root = true`, `env = "exec"`, and missing-value error behavior supported by the qualified fnox version. The synthetic value must not be sensitive.
5. Run:

```sh
mise run agent-sync
mise run agent-check
fnox check --all
fnox --profile local --non-interactive --if-missing error exec -- python3 scripts/mcp_canary.py --probe
env -u GITHUB_TOKEN scripts/check_native_auth.sh
```

Expected: all commands exit 0; `gh auth status` uses the existing OS credential-store login; no token is printed or copied.
6. Search the example for ownership leaks and secrets:

```sh
rg -n 'GITHUB_TOKEN|gh auth token|BEGIN .*PRIVATE KEY|api[_-]?key\s*=|token\s*=' examples/agent-layer-mvp
```

Expected: only the intentional `GITHUB_TOKEN` rejection test/documentation matches; no value assignment or credential material.
7. Commit:

```sh
git add examples/agent-layer-mvp
git commit -m "example: show project-owned agent configuration"
```

## Task 7: Document generation and ownership

**Files:**

- Modify: `README.md`
- Modify: `skills/bootstrap-project/SKILL.md`
- Modify: `skills/bootstrap-project/scripts/bootstrap.sh`

1. Add a docs/test assertion that these surfaces name `include_agent_layer` and `include_fnox`, and do not advertise toolkits as the primary model.
2. Run it. Expected: failure before documentation changes.
3. Document:

- what Copier creates;
- what the project must fill in;
- `mise run agent-sync`, `agent-check`, `agent-claude`, and `agent-codex` usage;
- fnox as optional binding, with no provider selected by the template;
- native CLI auth as a separate binding type;
- generated artifacts and when to commit them;
- Claude/Codex are V1 targets; Cursor/Copilot are deferred.

4. Update bootstrap argument validation/help without making bootstrap run APM or fnox.
5. Run the docs assertion and full CI-equivalent suite.
6. Commit:

```sh
git add README.md skills/bootstrap-project
git commit -m "docs: explain agent layer scaffolding"
```

## Task 8: End-to-end verification and handoff

1. Regenerate every CI template case. Expected: no unexplained diff.
2. Generate the example from scratch in a second temporary directory, apply the documented project-specific steps, and compare its framework files and compiled outputs with the committed example.
3. Run all template tests, shell tests, Python tests, APM checks, fnox checks, JSON parsing, and TOML parsing.
4. Run manual authenticated smoke tests:

```sh
cd examples/agent-layer-mvp && mise run agent-claude
cd examples/agent-layer-mvp && mise run agent-codex
```

In each agent, confirm the project instruction is visible and the canary MCP tool works. This step may consume model usage and stays outside automated CI.
5. Review:

```sh
git status --short
git diff --check
git log --oneline --decorate -5
```

Expected: clean worktree, no whitespace errors, and four small implementation commits.
6. Merge or cherry-pick `feature/apm-fnox-agent-layer` into `/Users/zarz/dev/agents/project-templates` only after user review. Do not push or open a PR without a separate request.

## Completion criteria

- Every template leaf produces the same optional framework.
- Disabling the layer leaves no APM/fnox/framework paths.
- Every repository command runs through mise; no agent-layer wrapper script is generated.
- Template output contains no concrete provider, endpoint, MCP, client policy, or credential.
- The example clearly separates generated skeleton from project-owned configuration.
- APM compiles valid Claude Code and Codex artifacts from one project source.
- fnox injection is child-process scoped and fails closed on missing bindings.
- existing `gh` keyring authentication works without token extraction or duplication.
- automated tests make no network calls, provider calls, or paid agent calls.
