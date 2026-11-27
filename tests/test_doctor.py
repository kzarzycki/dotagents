import os
import subprocess

import pytest

from test_install_subsets import make_checkout, run_install


def skill(root, name, requires=None, scripts=()):
    d = root / name
    (d / "scripts").mkdir(parents=True)
    meta = f'metadata:\n  requires: "{requires}"\n' if requires else ""
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n{meta}---\n\n# {name}\n")
    for s in scripts:
        (d / "scripts" / s).write_text("#!/bin/sh\n")


def lock(root, version, *skill_dirs, commit=None):
    root.mkdir(parents=True, exist_ok=True)
    deployed = "".join(f"  - {d}\n" for d in skill_dirs)
    resolved = f"  resolved_commit: {commit}\n" if commit else ""
    (root / "apm.lock.yaml").write_text(
        f"dependencies:\n- repo_url: x/pack\n  version: {version}\n{resolved}  deployed_files:\n{deployed}"
    )


DELETE = "delete the copy, or the clone if unused"


def git(*args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], check=True, capture_output=True
    )


def project_with_worktrees(main, *worktrees):
    """A main checkout with one commit, and a linked worktree at each path."""
    git("init", "-q", str(main))
    git("-C", str(main), "commit", "-q", "--allow-empty", "-m", "init")
    for i, w in enumerate(worktrees):
        git("-C", str(main), "worktree", "add", "-q", "-b", f"wt{i}", str(w))


def fake_tool(bindir, name, version):
    bindir.mkdir(parents=True, exist_ok=True)
    tool = bindir / name
    tool.write_text(f"#!/bin/sh\necho '{name} version {version} (2026-10-01)'\n")
    tool.chmod(0o755)


def doctor(repo, home, path):
    return subprocess.run(
        ["/bin/bash", str(repo / "bin/dotagents"), "doctor"],
        env={**os.environ, "HOME": str(home), "PATH": f"{path}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_doctor_reports_a_declared_tool_the_host_lacks_or_has_too_old(tmp_path):
    repo, home = make_checkout(tmp_path)
    pack = repo / ".agents/skills"
    skill(pack, "demo", requires="dtool>=2.99.0 dother", scripts=["demo.sh"])
    skill(home / ".claude-knowledge/skills", "kskill", requires="ktool")
    bindir = tmp_path / "bin"
    fake_tool(bindir, "dtool", "2.87.0")

    result = doctor(repo, home, bindir)
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        "too old: dtool 2.87.0, skill demo needs >= 2.99.0",
        "missing: dother, needed by skill demo",
        "missing: ktool, needed by skill kskill",
    ]

    fake_tool(bindir, "dtool", "2.103.1")
    fake_tool(bindir, "dother", "1")
    fake_tool(bindir, "ktool", "1")
    result = doctor(repo, home, bindir)
    assert (result.returncode, result.stdout) == (0, ""), result.stdout + result.stderr

    # Without the declaration there is nothing to report.
    fake_tool(bindir, "dtool", "2.87.0")
    (bindir / "dother").unlink()
    (pack / "demo/SKILL.md").write_text("---\nname: demo\ndescription: x\n---\n")
    result = doctor(repo, home, bindir)
    assert (result.returncode, result.stdout) == (0, ""), result.stdout + result.stderr


def test_doctor_reports_a_skill_script_the_pinned_pack_does_not_have(tmp_path):
    repo, home = make_checkout(tmp_path)
    skill(repo / ".agents/skills", "demo", scripts=["demo.sh"])
    lock(repo, "0.25.0", ".agents/skills/demo")
    # An old pin in a project, and the same in its .claude copy.
    for d in (".agents/skills", ".claude/skills"):
        skill(home / "dev/old" / d, "demo", scripts=["demo.sh", "post_demo.sh"])
    lock(home / "dev/old", "0.24.4", ".claude/skills/demo")
    skill(home / ".claude-knowledge/skills", "demo", scripts=["post_demo.sh"])
    # A project on a newer pin is ahead, not stale.
    skill(home / "dev/ahead/.claude/skills", "demo", scripts=["demo.sh", "new_helper.sh"])
    lock(home / "dev/ahead", "0.26.0", ".claude/skills/demo")
    # A directory the account can't read is skipped, not a failed run.
    (home / "private").mkdir()
    (home / "private").chmod(0)
    # Current copies, a pack source tree and the apm cache are not reported.
    skill(home / "dev/new/.claude/skills", "demo", scripts=["demo.sh"])
    skill(home / "dev/src/engineering/skills", "demo", scripts=["post_demo.sh"])
    skill(home / ".cache/apm/x/.claude/skills", "demo", scripts=["post_demo.sh"])
    skill(home / "dev/x/.cache/y/.claude/skills", "demo", scripts=["post_demo.sh"])
    # A loop's evidence copy of another repo is no skill path either.
    skill(home / "dev/old/tmp/loop/pr1-evidence/upstream/.agents/skills", "demo", scripts=["post_demo.sh"])
    # A spike harness copies a repo into workspaces/<run> or runs/<run> per run: disposable.
    for d in ("workspaces", "runs"):
        skill(home / f"dev/x/{d}/run1/.claude/skills", "demo", scripts=["post_demo.sh"])
    skill(home / "dev/new/apm_modules/x/.claude/skills", "demo", scripts=["post_demo.sh"])
    # Codex clones its marketplaces under .tmp in each Codex home; agents load no skill there.
    skill(home / ".codex/.tmp/marketplaces/x/.agents/skills", "demo", scripts=["post_demo.sh"])
    skill(
        home / ".omnigent/codex-native/abc/codex-home/.tmp/marketplaces/x/.claude/skills",
        "demo",
        scripts=["post_demo.sh"],
    )
    skill(home / ".agents/skills", "other", scripts=["any.sh"])

    stale = (".claude-knowledge/skills", "dev/old/.agents/skills", "dev/old/.claude/skills")
    try:
        result = doctor(repo, home, tmp_path / "bin")
        for d in stale:
            (home / d / "demo/scripts/post_demo.sh").unlink()
        clean = doctor(repo, home, tmp_path / "bin")
    finally:
        (home / "private").chmod(0o755)
    assert result.returncode == 1, result.stdout + result.stderr
    assert sorted(result.stdout.splitlines()) == [
        f"pack behind: {home}/dev/old (no git origin) pack 0.24.4 behind 0.25.0: bump the project's pack",
        f"stale skill copy: {home}/.claude-knowledge/skills/demo: post_demo.sh: re-run bin/dotagents install",
    ]
    assert (clean.returncode, clean.stdout) == (0, ""), clean.stdout + clean.stderr


def test_doctor_folds_a_project_whose_pack_is_behind_into_one_line(tmp_path):
    repo, home = make_checkout(tmp_path)
    names = ("alpha", "beta", "gamma")
    for name in names:
        skill(repo / ".agents/skills", name, scripts=["run.sh"])
    lock(repo, "0.26.0", *(f".agents/skills/{n}" for n in names))
    # A project on an older pack: three skills whose scripts changed since.
    project = home / "dev/widgets"
    for name in names:
        skill(project / ".agents/skills", name, scripts=["run.sh", "old_helper.sh"])
    lock(project, "0.25.1", *(f".agents/skills/{n}" for n in names))
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    subprocess.run(
        ["git", "-C", str(project), "remote", "add", "origin", "git@example.com:acme/widgets.git"], check=True
    )
    # A stray copy with no lock to explain it.
    skill(home / "dev/stray/.claude/skills", "beta", scripts=["old_helper.sh"])

    result = doctor(repo, home, tmp_path / "bin")
    assert result.returncode == 1, result.stdout + result.stderr
    assert sorted(result.stdout.splitlines()) == [
        f"pack behind: {project} (acme/widgets) pack 0.25.1 behind 0.26.0: bump the project's pack",
        f"stale skill copy: {home}/dev/stray/.claude/skills/beta: old_helper.sh: {DELETE}",
    ]

    # The same version doesn't explain a changed script: each copy keeps its own line.
    lock(project, "0.26.0", *(f".agents/skills/{n}" for n in names))
    result = doctor(repo, home, tmp_path / "bin")
    assert sum(line.startswith("stale skill copy:") for line in result.stdout.splitlines()) == 4, result.stdout


def test_doctor_skips_a_project_pinned_between_two_releases_but_not_one_at_the_pinned_commit(tmp_path):
    repo, home = make_checkout(tmp_path)
    skill(repo / ".agents/skills", "alpha", scripts=["run.sh"])
    lock(repo, "0.26.5", ".agents/skills/alpha", commit="dd7f054")
    # A project pinned at a later commit: the same version (only a release PR bumps it), another commit, and a script
    # the pinned pack lacks. It is ahead, not stale.
    project = home / "dev/widgets"
    skill(project / ".agents/skills", "alpha", scripts=["run.sh", "new_helper.sh"])
    lock(project, "0.26.5", ".agents/skills/alpha", commit="a5496b0")
    result = doctor(repo, home, tmp_path / "bin")
    assert result.returncode == 0 and result.stdout == "", result.stdout + result.stderr

    # The same commit with an extra script is still a stale copy.
    lock(project, "0.26.5", ".agents/skills/alpha", commit="dd7f054")
    result = doctor(repo, home, tmp_path / "bin")
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines() == [f"stale skill copy: {project}/.agents/skills/alpha: new_helper.sh: {DELETE}"]


@pytest.mark.parametrize(
    "hostile",
    [
        # Quotes, $(...) and backticks: the quotes alone break a double-quoted command.
        "q'\"$(touch${IFS}m1)`touch${IFS}m2`",
        # No stray quote: a double-quoted command still runs the $(...).
        "$(touch${IFS}m3)",
    ],
)
def test_doctor_never_runs_a_directory_name_as_shell_code(tmp_path, monkeypatch, hostile):
    # The name is in the checkout, HOME and project paths.
    repo, home = make_checkout(tmp_path / hostile)
    skill(repo / ".agents/skills", "demo", scripts=["run.sh"])
    lock(repo, "0.26.0", ".agents/skills/demo")
    project = home / "dev" / hostile
    skill(project / ".agents/skills", "demo", scripts=["run.sh", "old_helper.sh"])
    lock(project, "0.25.1", ".agents/skills/demo")
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    subprocess.run(
        ["git", "-C", str(project), "remote", "add", "origin", "git@example.com:acme/widgets.git"], check=True
    )
    monkeypatch.chdir(tmp_path)

    result = doctor(repo, home, tmp_path / "bin")
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        f"pack behind: {project} (acme/widgets) pack 0.25.1 behind 0.26.0: bump the project's pack",
    ]
    assert not [p for p in tmp_path.rglob("m[123]")], "a directory name ran as shell code"


def test_doctor_asks_for_the_pinned_pack_when_it_is_not_installed(tmp_path):
    repo, home = make_checkout(tmp_path)
    result = doctor(repo, home, tmp_path / "bin")
    assert result.returncode == 1
    assert "no pinned pack: run `mise run setup:dev`" in result.stdout


def install_env(tmp_path, monkeypatch):
    """A PATH whose fake mise and brew each install a current version of a tool."""
    bindir, shims, brew = tmp_path / "bin", tmp_path / "mise/shims", tmp_path / "brew"
    bindir.mkdir()
    current = "printf '#!/bin/sh\\necho %s version 2.103.1\\n' > {d}/$t; chmod +x {d}/$t"
    (bindir / "mise").write_text(
        f'#!/bin/sh\ncase "$*" in "use -g nosuch@latest") exit 1;; "use -g xttyd@latest") echo "unsupported env: darwin/arm64" >&2; exit 1;; "use -g "*@latest) t=${{3%@latest}};; *) exit 9;; esac\n'
        f"mkdir -p {shims}\n{current.replace('{d}', str(shims))}\n"
    )
    (bindir / "brew").write_text(
        f'#!/bin/sh\ncase "$1" in --prefix) echo {brew};; upgrade|install) t=$2; [ "$t" = nosuch ] && exit 1; mkdir -p {brew / "bin"}; {current.replace("{d}", str(brew / "bin"))};; *) exit 9;; esac\n'
    )
    for f in ("mise", "brew"):
        (bindir / f).chmod(0o755)
    monkeypatch.setenv("MISE_DATA_DIR", str(tmp_path / "mise"))
    monkeypatch.setenv("PATH", f"{bindir}:{brew / 'bin'}:{tmp_path / 'system'}:{os.environ['PATH']}")
    return bindir, shims, brew


def test_install_provides_a_declared_tool_through_its_installer_and_doctor_passes(tmp_path, monkeypatch):
    repo, home = make_checkout(tmp_path)
    skill(repo / ".agents/skills", "demo", requires="mtool>=2.99.0 btool>=2.99.0", scripts=["demo.sh"])
    bindir, shims, brew = install_env(tmp_path, monkeypatch)
    fake_tool(brew / "bin", "btool", "2.87.0")  # Homebrew's copy, too old; mtool is missing

    result = run_install(repo, home, "--profile", "vps", "--dry-run")
    assert "DRY: mise use -g mtool@latest" in result.stdout
    assert "DRY: brew upgrade btool" in result.stdout
    assert f"DRY: ln -sfn {shims}/mtool {home}/.local/bin/mtool" in result.stdout
    assert not (home / ".local/bin/mtool").is_symlink()

    result = run_install(repo, home, "--profile", "vps", "--only", ".claude")
    assert "PROVIDED:" not in result.stdout and "TOOL:" not in result.stdout

    result = run_install(repo, home, "--profile", "vps")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PROVIDED: mtool 2.103.1 via mise, for skill demo" in result.stdout
    assert "PROVIDED: btool 2.103.1 via brew, for skill demo" in result.stdout
    assert os.readlink(home / ".local/bin/mtool") == f"{shims}/mtool"
    assert not (home / ".local/bin/btool").exists()

    result = run_install(repo, home, "--profile", "vps")
    assert f"TOOL: mtool 2.103.1 at {home}/.local/bin/mtool, for skill demo (needs >= 2.99.0)" in result.stdout
    assert f"TOOL: btool 2.103.1 at {brew}/bin/btool, for skill demo (needs >= 2.99.0)" in result.stdout
    check = doctor(repo, home, bindir)
    assert (check.returncode, check.stdout) == (0, ""), check.stdout + check.stderr


def test_install_leaves_a_system_package_to_its_package_manager(tmp_path, monkeypatch):
    repo, home = make_checkout(tmp_path)
    skill(repo / ".agents/skills", "demo", requires="stool>=2.99.0 nosuch", scripts=["demo.sh"])
    install_env(tmp_path, monkeypatch)
    fake_tool(tmp_path / "system", "stool", "2.87.0")

    result = run_install(repo, home, "--profile", "vps")
    assert result.returncode != 0
    assert (
        f"WARNING: stool 2.87.0 at {tmp_path}/system/stool is too old for skill demo (needs >= 2.99.0); "
        "upgrade it with the package manager that installed it" in result.stderr
    )
    assert not (home / ".local/bin/stool").exists()
    # A tool neither mise nor Homebrew provides leaves no link to a shim that isn't there.
    assert "WARNING: brew did not provide nosuch >= any for skill demo" in result.stderr
    assert not (home / ".local/bin/nosuch").is_symlink()


def test_install_provides_through_brew_a_tool_mise_lacks_for_the_platform(tmp_path, monkeypatch):
    repo, home = make_checkout(tmp_path)
    skill(repo / ".agents/skills", "demo", requires="xttyd", scripts=["demo.sh"])
    bindir, _, brew = install_env(tmp_path, monkeypatch)  # its mise has no darwin build of xttyd, like ttyd

    result = run_install(repo, home, "--profile", "vps")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PROVIDED: xttyd 2.103.1 via brew, for skill demo" in result.stdout
    assert (brew / "bin/xttyd").exists() and not (home / ".local/bin/xttyd").exists()
    check = doctor(repo, home, bindir)
    assert (check.returncode, check.stdout) == (0, ""), check.stdout + check.stderr


def test_install_refreshes_a_global_skill_install_from_the_pinned_pack(tmp_path):
    repo, home = make_checkout(tmp_path)
    skill(repo / ".agents/skills", "orchestrating-agents", scripts=["omnigent_agent.py"])
    skill(home / ".agents/skills", "orchestrating-agents", scripts=["herdr_watch.sh"])
    (home / ".agents/skills/orchestrating-agents/NOTES.md").write_text("mine\n")
    (home / ".claude/skills").mkdir(parents=True)
    (home / ".claude/skills/orchestrating-agents").symlink_to("../../.agents/skills/orchestrating-agents")
    skill(home / ".agents/skills", "find-skills", scripts=["own.sh"])  # not the pack's: left alone

    assert "REFRESHED" not in run_install(repo, home, "--profile", "vps", "--only", "claude").stdout
    result = run_install(repo, home, "--profile", "vps")
    bak = home / ".dotagents-bak/.agents_skills_orchestrating-agents"
    assert result.stdout.count("REFRESHED:") == 1, result.stdout
    assert (
        f"REFRESHED: {home}/.agents/skills/orchestrating-agents from the pinned pack; the old copy is in {bak}"
        in result.stdout
    )
    scripts = home / ".agents/skills/orchestrating-agents/scripts"
    assert sorted(p.name for p in scripts.iterdir()) == ["omnigent_agent.py"]
    assert (bak / "NOTES.md").read_text() == "mine\n" and (bak / "scripts/herdr_watch.sh").exists()
    assert (home / ".claude/skills/orchestrating-agents").is_symlink()
    assert (home / ".agents/skills/find-skills/scripts/own.sh").exists()
    # A run of the skill leaves bytecode behind; that is no reason to refresh it again.
    (scripts / "__pycache__").mkdir()
    (scripts / "__pycache__/omnigent_agent.cpython-312.pyc").write_bytes(b"x")
    assert "REFRESHED" not in run_install(repo, home, "--profile", "vps").stdout
    assert doctor(repo, home, tmp_path / "bin").stdout == ""
    # Drifted again: the new copy replaces the previous backup, twice over.
    for n in (2, 3):
        (home / f".agents/skills/orchestrating-agents/NOTES{n}.md").write_text("mine\n")
        result = run_install(repo, home, "--profile", "vps")
        assert result.returncode == 0 and result.stdout.count("REFRESHED:") == 1, result.stdout + result.stderr
        assert sorted(p.name for p in bak.glob("NOTES*")) == [f"NOTES{n}.md"]
        assert not (bak / "orchestrating-agents").exists()


def test_install_puts_dotagents_on_path(tmp_path):
    repo, home = make_checkout(tmp_path)
    run_install(repo, home, "--profile", "vps")
    # Run through the link, from elsewhere: it still finds its checkout.
    result = subprocess.run(
        [str(home / ".local/bin/dotagents"), "doctor"],
        env={**os.environ, "HOME": str(home)},
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert f"no pinned pack: run `mise run setup:dev` in {repo}" in result.stdout, result.stdout + result.stderr


def test_a_codex_host_reports_only_real_stale_copies_and_install_clears_the_global_one(tmp_path):
    """The shape of a macOS host's first doctor run: Codex marketplace clones in .tmp under
    each Codex home (an upgrade staged beside them), a stale global skill install, and a
    project on an old pin."""
    repo, home = make_checkout(tmp_path)
    skill(repo / ".agents/skills", "demo", scripts=["demo.sh"])
    skill(repo / ".agents/skills", "orchestrating-agents", scripts=["omnigent_agent.py"])
    codex_homes = [home / ".codex"] + [home / f".omnigent/codex-native/{h * 32}/codex-home" for h in "ab"]
    for codex_home in codex_homes:
        for clone in ("marketplaces/agent-skills", "marketplaces/.staging/marketplace-upgrade-Xy12"):
            for d in (".agents/skills", ".claude/skills"):
                skill(codex_home / ".tmp" / clone / d, "demo", scripts=["demo.sh", "post_demo.sh"])
    skill(home / ".agents/skills", "orchestrating-agents", scripts=["omnigent_agent.py", "herdr_watch.sh"])
    skill(home / "dev/old/.agents/skills", "demo", scripts=["demo.sh", "post_demo.sh"])

    expected = [
        f"stale skill copy: {home}/.agents/skills/orchestrating-agents: herdr_watch.sh: re-run bin/dotagents install",
        f"stale skill copy: {home}/dev/old/.agents/skills/demo: post_demo.sh: {DELETE}",
    ]
    assert sorted(doctor(repo, home, tmp_path / "bin").stdout.splitlines()) == expected
    run_install(repo, home, "--profile", "vps")
    assert doctor(repo, home, tmp_path / "bin").stdout.splitlines() == expected[1:]


def test_doctor_folds_linked_worktrees_into_their_main_checkouts_line(tmp_path):
    repo, home = make_checkout(tmp_path)
    for name in ("demo", "beta"):
        skill(repo / ".agents/skills", name, scripts=["run.sh"])
    main = home / "dev/widgets"
    # One worktree inside the project, as `.worktrees/<branch>`, one beside it; a third holds only another skill's copy.
    worktrees = (main / ".worktrees/a", home / "dev/widgets-worktrees/b")
    project_with_worktrees(main, *worktrees, main / ".worktrees/c")
    (main / "apm.yml").write_text("name: widgets\n")
    skill(main / ".agents/skills", "demo", scripts=["run.sh", "old_helper.sh"])
    skill(main / ".worktrees/c/.agents/skills", "beta", scripts=["run.sh", "old_helper.sh"])
    for w in worktrees:
        # Two skill paths in one worktree count it once.
        for d in (".agents/skills", ".claude/skills"):
            skill(w / d, "demo", scripts=["run.sh", "old_helper.sh"])

    result = doctor(repo, home, tmp_path / "bin")
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        f"stale skill copy: {main}/.agents/skills/demo: old_helper.sh: run apm install in {main} "
        "(also in 2 linked worktrees)"
    ]

    # Without the main checkout's copy, the worktree copies refresh with their branch: nothing to report.
    (main / ".agents/skills/demo/scripts/old_helper.sh").unlink()
    result = doctor(repo, home, tmp_path / "bin")
    assert (result.returncode, result.stdout) == (0, ""), result.stdout + result.stderr


def test_doctor_prints_nothing_when_only_linked_worktrees_hold_a_stale_copy(tmp_path):
    repo, home = make_checkout(tmp_path)
    skill(repo / ".agents/skills", "demo", scripts=["run.sh"])
    main = home / "dev/widgets"
    worktrees = (main / ".worktrees/a", home / "dev/widgets-worktrees/b")
    project_with_worktrees(main, *worktrees)
    (main / "apm.yml").write_text("name: widgets\n")
    for w in worktrees:
        skill(w / ".agents/skills", "demo", scripts=["run.sh", "old_helper.sh"])

    result = doctor(repo, home, tmp_path / "bin")
    assert (result.returncode, result.stdout) == (0, ""), result.stdout + result.stderr


def test_doctor_folds_linked_worktrees_of_a_project_behind_the_pin_into_one_pack_behind_line(tmp_path):
    repo, home = make_checkout(tmp_path)
    for name in ("alpha", "beta"):
        skill(repo / ".agents/skills", name, scripts=["run.sh"])
    lock(repo, "0.26.0", ".agents/skills/alpha", ".agents/skills/beta")
    main = home / "dev/widgets"
    worktrees = (main / ".worktrees/a", main / ".worktrees/b")
    project_with_worktrees(main, *worktrees)
    for root in (main, *worktrees):
        for name in ("alpha", "beta"):
            skill(root / ".agents/skills", name, scripts=["run.sh", "old_helper.sh"])
        lock(root, "0.25.1", ".agents/skills/alpha", ".agents/skills/beta")

    result = doctor(repo, home, tmp_path / "bin")
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        f"pack behind: {main} (no git origin) pack 0.25.1 behind 0.26.0: bump the project's pack "
        "(also in 2 linked worktrees)"
    ]


@pytest.mark.parametrize(
    "where, action",
    [
        ("dev/widgets", "run apm install in {home}/dev/widgets"),
        ("", "re-run bin/dotagents install"),
        ("dev/old-clone", DELETE),
    ],
    ids=["project-with-apm-yml", "global-skill-path", "other"],
)
def test_each_stale_copy_line_ends_with_the_action_that_clears_it(tmp_path, where, action):
    repo, home = make_checkout(tmp_path)
    skill(repo / ".agents/skills", "demo", scripts=["demo.sh"])
    root = home / where
    if where == "dev/widgets":
        root.mkdir(parents=True)
        (root / "apm.yml").write_text("name: widgets\n")
    skill(root / ".agents/skills", "demo", scripts=["demo.sh", "old_helper.sh"])

    result = doctor(repo, home, tmp_path / "bin")
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        f"stale skill copy: {root}/.agents/skills/demo: old_helper.sh: {action.format(home=home)}"
    ]


def forwarder(root, name="orchestrating-agents", target="omnigent-agents"):
    skill(root, name, scripts=[])
    (root / name / "scripts/omnigent_agent.py").write_text(f'skill = "{target}"\n')


def test_install_puts_a_forwarders_target_beside_it_in_every_skills_dir(tmp_path):
    repo, home = make_checkout(tmp_path)
    forwarder(repo / ".agents/skills")
    skill(repo / ".agents/skills", "omnigent-agents", scripts=["omnigent_agent.py"])
    # An old full copy, as an earlier install left it; ~/.claude/skills links it.
    skill(home / ".agents/skills", "orchestrating-agents", scripts=["herdr_watch.sh"])
    (home / ".claude/skills").mkdir(parents=True)
    (home / ".claude/skills/orchestrating-agents").symlink_to("../../.agents/skills/orchestrating-agents")

    result = run_install(repo, home, "--profile", "vps")
    assert result.returncode == 0, result.stdout + result.stderr
    for d in (".agents/skills", ".claude/skills"):
        assert (home / d / "omnigent-agents/SKILL.md").is_file(), d
    assert doctor(repo, home, tmp_path / "bin").stdout == ""


def test_install_keeps_a_copy_whose_pack_forwarder_has_no_target(tmp_path):
    repo, home = make_checkout(tmp_path)
    forwarder(repo / ".agents/skills")  # the pack lacks omnigent-agents
    skill(home / ".agents/skills", "orchestrating-agents", scripts=["herdr_watch.sh"])

    result = run_install(repo, home, "--profile", "vps")
    assert result.returncode != 0
    assert "WARNING: kept" in result.stderr and "omnigent-agents" in result.stderr
    assert (home / ".agents/skills/orchestrating-agents/scripts/herdr_watch.sh").exists()
    assert not (home / ".dotagents-bak").exists()


def test_doctor_fails_on_a_forwarder_whose_target_is_missing(tmp_path):
    repo, home = make_checkout(tmp_path)
    skill(repo / ".agents/skills", "demo")
    forwarder(home / ".agents/skills")
    (home / ".claude/skills").mkdir(parents=True)
    (home / ".claude/skills/orchestrating-agents").symlink_to("../../.agents/skills/orchestrating-agents")
    skill(home / ".agents/skills", "omnigent-agents")  # beside the .agents copy only

    result = doctor(repo, home, tmp_path / "bin")
    assert result.returncode != 0
    assert result.stdout == (
        f"broken forwarder: {home}/.claude/skills/orchestrating-agents needs the skill omnigent-agents "
        "beside it: re-run bin/dotagents install\n"
    )


def test_install_leaves_a_lock_that_apm_rewrote_as_it_was(tmp_path, monkeypatch):
    repo, home = make_checkout(tmp_path)
    lock(repo, "1.0.0", ".agents/skills/demo")
    before = (repo / "apm.lock.yaml").read_bytes()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "mise").write_text(f"#!/bin/sh\necho rewritten > {repo}/apm.lock.yaml\nmkdir -p {repo}/.agents/skills\n")
    (bindir / "mise").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")

    result = run_install(repo, home, "--profile", "vps")
    assert "INSTALLED: the pinned pack" in result.stdout, result.stdout + result.stderr
    assert (repo / "apm.lock.yaml").read_bytes() == before
