# Dotagents Capability-Pack Adoption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dotagents source repository an ordinary project-scoped consumer of the released `engineering` capability pack without putting project state or skill payloads in the installed `home/` tree.

**Architecture:** Root-level APM sources, lock, compiled coding-agent targets, and a mise task form the development-repository agent layer. The `home/` mirror remains the user- and machine-scope dotagents distribution. The implementation uses the same `agent-sync` interface and APM 0.26.0 behavior qualified by `project-templates`.

**Tech Stack:** APM 0.26.0, mise, Bash, pytest, Claude Code, Codex

## Global Constraints

- Start only after `agent-skills/engineering` publishes a release compatible with `^0.2.0`.
- Copy the final inline `agent-sync` task from the approved `project-templates` scaffold; do not create a dotagents variant or wrapper script.
- Support `mise run agent-sync`, `mise run agent-sync -- --refresh`, and `mise run agent-sync -- --frozen`.
- Keep `.agents/skills/`, `.claude/skills/`, and `apm_modules/` untracked while retaining generated `.claude/rules/`.
- Commit `apm.yml`, `apm.lock.yaml`, `.apm/instructions/`, and APM-generated coding-agent targets.
- Keep `home/.agents/AGENTS.md` unchanged; it is the installed user behavioral specification.
- Do not change `bin/dotagents` or install project-scoped files under `home/`.
- Compile and test Claude Code and Codex targets.

---

### Task 1: Define and test the repository-versus-home boundary

**Files:**
- Create: `tests/test_project_agent_layer.py`
- Modify: `AGENTS.md`
- Create: `.apm/instructions/project.instructions.md`

**Interfaces:**
- Consumes: the current root `AGENTS.md` project-maintainer instructions
- Produces: `.apm/instructions/project.instructions.md` as the APM source for root generated instructions

- [ ] **Step 1: Write the failing boundary tests**

Create `tests/test_project_agent_layer.py`:

```python
from pathlib import Path
import hashlib
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_project_agent_layer_is_not_part_of_home_payload():
    forbidden = (
        "apm.yml",
        "apm.lock.yaml",
        "mise.toml",
        ".apm",
        ".agents/skills",
        ".claude/skills",
    )
    for relative in forbidden:
        assert not (ROOT / "home" / relative).exists(), relative


def test_project_instruction_source_records_scope_boundary():
    source = ROOT / ".apm/instructions/project.instructions.md"
    text = source.read_text()
    assert 'applyTo: "**"' in text
    assert "`home/` contains user- and machine-scope configuration" in text
    assert "Repository-root agent configuration serves dotagents development" in text


def test_installed_user_instructions_do_not_claim_project_ownership():
    text = (ROOT / "home/.agents/AGENTS.md").read_text()
    assert "apm.lock.yaml" not in text
    assert "agent-skills/engineering" not in text


def test_installed_user_instructions_match_stage3_base_byte_for_byte():
    current = (ROOT / "home/.agents/AGENTS.md").read_bytes()
    base = subprocess.check_output(
        ["git", "show", "ce9a031:home/.agents/AGENTS.md"],
        cwd=ROOT,
    )
    assert hashlib.sha256(current).hexdigest() == hashlib.sha256(base).hexdigest()
    assert current == base
```

- [ ] **Step 2: Run the tests and verify the missing source fails**

Run:

```sh
python3 -m pytest tests/test_project_agent_layer.py -q
```

Expected: three tests pass and
`test_project_instruction_source_records_scope_boundary` fails because
`.apm/instructions/project.instructions.md` does not exist.

- [ ] **Step 3: Create the APM instruction source**

Create `.apm/instructions/project.instructions.md` with this frontmatter:

```markdown
---
description: Instructions for maintaining the dotagents repository
applyTo: "**"
---
```

Append the current root `AGENTS.md` body, then replace its final scope section with:

```markdown
## Scope boundaries

`home/` contains user- and machine-scope configuration installed under `~/`.
Repository-root agent configuration serves dotagents development and follows the
same APM and mise contract as other projects.

The installed `home/` payload excludes:

- project-scoped agent state, generated targets, and dependency locks;
- cloud or remote project-session state;
- copied skill payloads.
```

Keep all existing installer and symlink rules unchanged.

- [ ] **Step 4: Compile the source once APM configuration exists**

Do not hand-maintain root `AGENTS.md` after Task 2 adds `apm.yml`. Task 2 runs `agent-sync`, which replaces it with APM output generated from this source.

- [ ] **Step 5: Run the boundary tests**

Run:

```sh
python3 -m pytest tests/test_project_agent_layer.py -q
```

Expected: 4 passed.

- [ ] **Step 6: Commit the source boundary**

```sh
git add .apm/instructions/project.instructions.md tests/test_project_agent_layer.py
git commit -m "docs: define dotagents project agent boundary"
```

Do not stage root `AGENTS.md` until it has been generated in Task 2.

---

### Task 2: Add the engineering dependency and canonical sync operation

**Files:**
- Create: `apm.yml`
- Create: `mise.toml`
- Modify: `.gitignore`
- Modify: `tests/test_project_agent_layer.py`
- Generate: `apm.lock.yaml`
- Generate: `AGENTS.md`
- Generate: `.claude/rules/project.md`
- Generate: Codex target files selected by APM 0.26.0

**Interfaces:**
- Consumes: `kzarzycki/agent-skills/engineering` at `^0.2.0`; qualified inline Stage 2 `agent-sync` scaffold
- Produces: the three-mode `mise run agent-sync` interface and locked Claude/Codex project configuration

- [ ] **Step 1: Add failing manifest and task contract tests**

Append to `tests/test_project_agent_layer.py`:

```python
import tomllib


def test_apm_manifest_selects_one_engineering_pack():
    text = (ROOT / "apm.yml").read_text()
    assert "targets:\n- claude\n- codex" in text
    assert text.count("git: kzarzycki/agent-skills/engineering") == 1
    assert "ref: ^0.2.0" in text


def test_mise_exposes_one_public_sync_operation():
    config = tomllib.loads((ROOT / "mise.toml").read_text())
    assert config["tools"]["github:microsoft/apm"] == "0.26.0"
    sync = config["tasks"]["agent-sync"]
    assert "--refresh" in sync["usage"]
    assert "--frozen" in sync["usage"]
    assert "apm update --yes" in sync["run"]
    assert "apm compile --clean" in sync["run"]
    assert "apm compile --validate" in sync["run"]
    assert "agent-update" not in config["tasks"]


def test_generated_targets_identify_apm():
    agents = (ROOT / "AGENTS.md").read_text()
    claude = (ROOT / ".claude/rules/project.md").read_text()
    marker = "Generated by APM CLI"
    assert marker in agents
    assert marker in claude


def test_agent_sync_rejects_unknown_mode():
    result = subprocess.run(
        ["mise", "run", "agent-sync", "--", "--unknown"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "usage:" in result.stderr.lower()


def test_agent_sync_rejects_conflicting_modes():
    result = subprocess.run(
        ["mise", "run", "agent-sync", "--", "--refresh", "--frozen"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 2
    assert "cannot be combined" in result.stderr


def test_installed_skill_trees_are_ignored_but_claude_rules_are_tracked():
    for path in (
        ".agents/skills/probe/SKILL.md",
        ".claude/skills/probe/SKILL.md",
    ):
        ignored = subprocess.run(
            ["git", "check-ignore", "--no-index", "--quiet", path],
            cwd=ROOT,
        )
        assert ignored.returncode == 0, path
    rules = subprocess.run(
        [
            "git",
            "check-ignore",
            "--no-index",
            "--quiet",
            ".claude/rules/project.md",
        ],
        cwd=ROOT,
    )
    assert rules.returncode == 1
```

- [ ] **Step 2: Run the contract tests and verify missing files fail**

Run:

```sh
python3 -m pytest tests/test_project_agent_layer.py -q
```

Expected: failures name missing `apm.yml`, `mise.toml`, and generated target files.

- [ ] **Step 3: Add the APM manifest**

Create `apm.yml`:

```yaml
name: dotagents
version: 0.1.0
description: Development agent configuration for the dotagents repository.
author: kzarzycki
targets:
- claude
- codex
dependencies:
  apm:
  - git: kzarzycki/agent-skills/engineering
    ref: ^0.2.0
  mcp: []
includes: auto
scripts: {}
```

- [ ] **Step 4: Add the canonical Stage 2 inline sync task**

Create `mise.toml` with the qualified Stage 2 contract:

```toml
[tools]
python = "3.14"
"github:microsoft/apm" = "0.26.0"

[tasks.agent-sync]
description = "Converge project-owned coding agent configuration."
usage = '''
flag "--refresh" help="Resolve available dependency releases before convergence"
flag "--frozen" help="Verify the committed lock and generated coding agent state"
'''
run = """
if [ "${usage_refresh:-false}" = true ] && [ "${usage_frozen:-false}" = true ]; then
  echo "error: --refresh and --frozen cannot be combined" >&2
  exit 2
fi
mode=default
if [ "${usage_refresh:-false}" = true ]; then mode=refresh; fi
if [ "${usage_frozen:-false}" = true ]; then mode=frozen; fi
command -v apm >/dev/null || { echo "error: apm 0.26.0 is required; run 'mise install'" >&2; exit 127; }
command -v python3 >/dev/null || { echo "error: python3 is required; run 'mise install'" >&2; exit 127; }
if [ "$mode" = frozen ]; then
  frozen_changes="$(git status --porcelain=v1 --untracked-files=all -- \
    apm.yml apm.lock.yaml .apm AGENTS.md CLAUDE.md \
    ':(glob)**/AGENTS.md' ':(glob)**/CLAUDE.md' \
    .agents .claude .codex .github/instructions)"
  if [ -n "$frozen_changes" ]; then
    echo "error: frozen agent configuration changed:" >&2
    echo "$frozen_changes" >&2
    echo "run 'mise run agent-sync' and commit the resulting agent configuration" >&2
    exit 1
  fi
fi
case "$mode" in
  default) apm install ;;
  refresh) apm update --yes ;;
  frozen)
    apm install --frozen
    apm audit --ci --no-policy
    ;;
esac
apm compile --clean
apm compile --validate
apm audit --ci --no-policy
# Add native-output validation for every implemented coding agent here.
if [ -f .mcp.json ]; then python3 -m json.tool .mcp.json >/dev/null; fi
if [ -f .codex/config.toml ]; then python3 -c 'import tomllib; tomllib.load(open(".codex/config.toml", "rb"))'; fi
if [ "$mode" = frozen ]; then
  frozen_changes="$(git status --porcelain=v1 --untracked-files=all -- \
    apm.yml apm.lock.yaml .apm AGENTS.md CLAUDE.md \
    ':(glob)**/AGENTS.md' ':(glob)**/CLAUDE.md' \
    .agents .claude .codex .github/instructions)"
  if [ -n "$frozen_changes" ]; then
    echo "error: frozen agent configuration changed:" >&2
    echo "$frozen_changes" >&2
    echo "run 'mise run agent-sync' and commit the resulting agent configuration" >&2
    exit 1
  fi
fi
"""
```

Before committing, compare this task with
`templates/_base/_mise_agent_tasks.part` at project-templates commit `6a5ea05`.
The `usage` declarations are required because mise does not forward multiline
task arguments through `$@`.

- [ ] **Step 5: Ignore installed payload and cache paths**

Add under a root-project heading in `.gitignore`:

```gitignore
# Project coding-agent installed payload and caches
apm_modules/
.agents/skills/
.claude/skills/
```

Do not ignore `.claude/` or `.claude/rules/`. Do not add ignores beneath
`home/`; the existing install manifest remains unaffected.

- [ ] **Step 6: Install, compile, and lock**

Run:

```sh
mise install
mise run agent-sync
```

Expected: `apm.lock.yaml` resolves a release compatible with `^0.2.0`; APM
generates root `AGENTS.md`, `.claude/rules/project.md`, and the Codex target
files without writing under `home/`.

- [ ] **Step 7: Run contract tests**

Run:

```sh
python3 -m pytest tests/test_project_agent_layer.py -q
```

Expected: all project-agent-layer tests pass.

- [ ] **Step 8: Commit the project agent layer**

Review generated files, then run:

```sh
git add .gitignore .apm AGENTS.md .claude/rules apm.yml apm.lock.yaml mise.toml tests/test_project_agent_layer.py
git diff --cached --check
git commit -m "feat: adopt engineering capability pack"
```

---

### Task 3: Verify clean, idempotent, and frozen operation

**Files:**
- Modify: `README.md`
- Modify: `tests/test_project_agent_layer.py`

**Interfaces:**
- Consumes: the committed Task 2 manifest, lock, generated targets, and sync task
- Produces: local contributor guidance and end-to-end evidence for default and frozen convergence

- [ ] **Step 1: Add the contributor documentation test**

Append to `tests/test_project_agent_layer.py`:

```python
def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix().encode()
        digest.update(relative)
        if path.is_symlink():
            digest.update(b"link\0")
            digest.update(path.readlink().as_posix().encode())
        elif path.is_file():
            digest.update(b"file\0")
            digest.update(path.read_bytes())
        else:
            digest.update(b"dir\0")
    return digest.hexdigest()


def skill_tree_manifest(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_readme_documents_project_scoped_sync():
    text = (ROOT / "README.md").read_text()
    assert "mise run agent-sync" in text
    assert "repository root" in text
    assert "`home/`" in text


def test_agent_sync_leaves_home_tree_byte_identical():
    before = tree_digest(ROOT / "home")
    subprocess.run(
        ["mise", "run", "agent-sync"],
        cwd=ROOT,
        check=True,
    )
    assert tree_digest(ROOT / "home") == before
```

- [ ] **Step 2: Run the documentation test and verify it fails**

Run:

```sh
python3 -m pytest tests/test_project_agent_layer.py::test_readme_documents_project_scoped_sync -q
```

Expected: FAIL because the README does not yet describe root project convergence.

- [ ] **Step 3: Document the contributor operation**

Add a `Repository development agent layer` section after the README layout description:

````markdown
## Repository development agent layer

The repository root is an APM consumer for work on dotagents itself. Run:

```sh
mise run agent-sync
```

The task installs the locked `engineering` capability pack and compiles Claude
Code and Codex project configuration. Pass `-- --refresh` to resolve a newer
declared release or `-- --frozen` to verify committed state. Root project files
stay in this repository; `home/` remains the payload installed under `~/`.
````

- [ ] **Step 4: Exercise compatible refresh**

Run:

```sh
mise run agent-sync -- --refresh
mise run agent-sync
python3 -m pytest tests/test_project_agent_layer.py::test_apm_manifest_selects_one_engineering_pack -q
```

Expected: refresh uses `apm update --yes`, resolves only a release compatible
with `^0.2.0`, and the following default convergence succeeds. Review and stage
an updated `apm.lock.yaml` when a newer compatible release exists.

- [ ] **Step 5: Verify default idempotence against a captured baseline**

Run:

```sh
baseline_dir="$(mktemp -d)"
trap 'rm -rf "$baseline_dir"' EXIT
git status --porcelain=v1 --untracked-files=all >"$baseline_dir/status"
git diff --binary >"$baseline_dir/worktree.diff"
git diff --cached --binary >"$baseline_dir/index.diff"
mise run agent-sync
git status --porcelain=v1 --untracked-files=all | cmp -s - "$baseline_dir/status"
git diff --binary | cmp -s - "$baseline_dir/worktree.diff"
git diff --cached --binary | cmp -s - "$baseline_dir/index.diff"
mise run agent-sync
git status --porcelain=v1 --untracked-files=all | cmp -s - "$baseline_dir/status"
git diff --binary | cmp -s - "$baseline_dir/worktree.diff"
git diff --cached --binary | cmp -s - "$baseline_dir/index.diff"
```

Expected: every `cmp` exits 0. Existing staged or unstaged work remains
byte-identical, and neither sync adds a change.

- [ ] **Step 6: Verify frozen convergence**

Run:

```sh
before_status="$(git status --porcelain=v1 --untracked-files=all)"
mise run agent-sync -- --frozen
after_status="$(git status --porcelain=v1 --untracked-files=all)"
test "$before_status" = "$after_status"
```

Expected: exit 0 and no new changes. README or test edits outside the frozen
agent paths may remain present.

- [ ] **Step 7: Verify recursive frozen detection**

Create a nested generated-file fixture:

```sh
mkdir -p .agent-sync-fixture/nested
cp AGENTS.md .agent-sync-fixture/nested/AGENTS.md
mise run agent-sync -- --frozen
```

Expected: non-zero exit naming
`.agent-sync-fixture/nested/AGENTS.md`, proving the recursive
`**/AGENTS.md` pathspec is active. Remove the fixture:

```sh
rm .agent-sync-fixture/nested/AGENTS.md
rmdir .agent-sync-fixture/nested .agent-sync-fixture
```

- [ ] **Step 8: Verify orphan cleanup and frozen post-compile detection**

Recreate the generated-file fixture, then run default convergence:

```sh
mkdir -p .agent-sync-fixture/nested
cp AGENTS.md .agent-sync-fixture/nested/AGENTS.md
mise run agent-sync
test ! -e .agent-sync-fixture/nested/AGENTS.md
rmdir .agent-sync-fixture/nested .agent-sync-fixture
```

Expected: `apm compile --clean` removes the orphaned APM-generated file.

Repeat the case with the orphan committed in a disposable worktree:

```sh
git worktree add --detach /tmp/dotagents-orphan-fixture HEAD
cd /tmp/dotagents-orphan-fixture
mkdir -p .agent-sync-fixture/nested
cp AGENTS.md .agent-sync-fixture/nested/AGENTS.md
git add -f .agent-sync-fixture/nested/AGENTS.md
git -c user.name=Test -c user.email=test@example.com commit --no-verify -m "test: add stale generated output"
mise install
mise run agent-sync -- --frozen
```

Expected: pre-compile status is clean, `apm compile --clean` removes the nested
orphan, and the post-compile frozen check fails while naming
`.agent-sync-fixture/nested/AGENTS.md`. Return to the feature worktree and remove
the disposable worktree:

```sh
cd /tmp/dotagents-capability-pack
git worktree remove --force /tmp/dotagents-orphan-fixture
```

- [ ] **Step 9: Verify stale-manifest rejection**

Change `ref: ^0.2.0` to `ref: ^0.3.0` in `apm.yml`, run:

```sh
mise run agent-sync -- --frozen
```

Expected: non-zero exit naming the modified frozen agent configuration. Restore
`ref: ^0.2.0` with `apply_patch`.

- [ ] **Step 10: Verify the full repository and byte-identical home tree**

Run:

```sh
home_before="$(python3 -c 'from tests.test_project_agent_layer import ROOT, tree_digest; print(tree_digest(ROOT / "home"))')"
python3 -m pytest -q
HOME=/tmp/dotagents-capability-pack-home bin/dotagents install --no-pull
home_after="$(python3 -c 'from tests.test_project_agent_layer import ROOT, tree_digest; print(tree_digest(ROOT / "home"))')"
test "$home_before" = "$home_after"
git diff --check
```

Expected: all tests pass; the fake-HOME install succeeds without installing root
`apm.yml`, `apm.lock.yaml`, `mise.toml`, `.apm/`, `.agents/skills/`, or
`.claude/skills/`; `home/` has the same byte digest before and after; no diff
errors.

- [ ] **Step 11: Verify ignored skill-payload integrity and repair**

Git does not track `.agents/skills/` or `.claude/skills/`, so Git status cannot
detect deletion or corruption there. Default APM convergence must repair the
deployed payload; frozen install and audit must then verify its locked integrity.

Converge and record the complete inventory and SHA-256 digest of every installed
skill file:

```sh
mise run agent-sync
python3 -c 'import json; from tests.test_project_agent_layer import ROOT, skill_tree_manifest; print(json.dumps(skill_tree_manifest(ROOT / ".agents/skills"), indent=2, sort_keys=True))' > /tmp/dotagents-agents-skills.before.json
python3 -c 'import json; from tests.test_project_agent_layer import ROOT, skill_tree_manifest; print(json.dumps(skill_tree_manifest(ROOT / ".claude/skills"), indent=2, sort_keys=True))' > /tmp/dotagents-claude-skills.before.json
rg -q '"wayfinder/SKILL.md"' /tmp/dotagents-agents-skills.before.json
rg -q '"wayfinder/SKILL.md"' /tmp/dotagents-claude-skills.before.json
test -f .agents/skills/wayfinder/SKILL.md
test -f .claude/skills/wayfinder/SKILL.md
```

Expected: both manifests are non-empty and both coding-agent trees expose
Wayfinder.

Delete the Agent Skills copy and corrupt the Claude copy:

```sh
rm .agents/skills/wayfinder/SKILL.md
printf '%s\n' 'corrupt repair probe' > .claude/skills/wayfinder/SKILL.md
mise run agent-sync
```

Record the repaired payload and compare it byte-for-byte through its inventory
and hashes:

```sh
python3 -c 'import json; from tests.test_project_agent_layer import ROOT, skill_tree_manifest; print(json.dumps(skill_tree_manifest(ROOT / ".agents/skills"), indent=2, sort_keys=True))' > /tmp/dotagents-agents-skills.after.json
python3 -c 'import json; from tests.test_project_agent_layer import ROOT, skill_tree_manifest; print(json.dumps(skill_tree_manifest(ROOT / ".claude/skills"), indent=2, sort_keys=True))' > /tmp/dotagents-claude-skills.after.json
cmp -s /tmp/dotagents-agents-skills.before.json /tmp/dotagents-agents-skills.after.json
cmp -s /tmp/dotagents-claude-skills.before.json /tmp/dotagents-claude-skills.after.json
test -f .agents/skills/wayfinder/SKILL.md
test -f .claude/skills/wayfinder/SKILL.md
mise run agent-sync -- --frozen
```

Expected: default convergence restores both ignored trees to their recorded
inventory and SHA-256 digests; Wayfinder is discoverable in each tree; frozen
install and both audits pass on the repaired locked payload.

- [ ] **Step 12: Commit documentation and verification**

```sh
git add README.md tests/test_project_agent_layer.py
git diff --cached --check
git commit -m "docs: explain project capability sync"
```

---

### Task 4: Remove the redundant user-global Matt activation

**Files:**
- Modify: `home/.claude/settings.vps.json`
- Modify: `tests/test_project_agent_layer.py`

**Interfaces:**
- Consumes: verified project-scoped engineering skill discovery from Task 3
- Produces: dotagents user configuration that no longer relies on a direct global Matt installation

- [ ] **Step 1: Confirm the exact legacy activation**

Run:

```sh
rg -n "mattpocock-skills" home/.claude/settings.vps.json
```

Expected: one enabled-plugin entry:

```text
"mattpocock-skills@kzarzycki-agent-skills": true
```

- [ ] **Step 2: Add a failing regression test**

Append to `tests/test_project_agent_layer.py`:

```python
def test_home_configuration_does_not_enable_direct_matt_plugin():
    for path in (ROOT / "home/.claude").glob("settings.*.json"):
        assert "mattpocock-skills" not in path.read_text(), path
```

Run:

```sh
python3 -m pytest tests/test_project_agent_layer.py::test_home_configuration_does_not_enable_direct_matt_plugin -q
```

Expected: FAIL naming the profile that enables the direct plugin.

- [ ] **Step 3: Remove only the direct plugin enablement**

Delete `"mattpocock-skills@kzarzycki-agent-skills": true` from
`home/.claude/settings.vps.json`. Preserve unrelated marketplace declarations
and every Superpowers entry; Superpowers is an independent package choice.

- [ ] **Step 4: Validate generated user settings and project skills**

Run:

```sh
HOME=/tmp/dotagents-capability-pack-home bin/dotagents install --no-pull
mise run agent-sync -- --frozen
python3 -m pytest -q
```

Expected: install-generated Claude settings parse, frozen project sync succeeds, and all tests pass.

- [ ] **Step 5: Commit the legacy activation removal**

```sh
git add home/.claude/settings.vps.json tests/test_project_agent_layer.py
git diff --cached --check
git commit -m "chore: retire global Matt skills activation"
```
