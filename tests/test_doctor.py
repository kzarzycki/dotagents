import os
import subprocess

from test_install_subsets import make_checkout, run_install


def skill(root, name, requires=None, scripts=()):
    d = root / name
    (d / "scripts").mkdir(parents=True)
    meta = f'metadata:\n  requires: "{requires}"\n' if requires else ""
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n{meta}---\n\n# {name}\n")
    for s in scripts:
        (d / "scripts" / s).write_text("#!/bin/sh\n")


def lock(root, version, skill_dir):
    root.mkdir(parents=True, exist_ok=True)
    (root / "apm.lock.yaml").write_text(
        f"dependencies:\n- repo_url: x/pack\n  version: {version}\n  deployed_files:\n  - {skill_dir}\n"
    )


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
    skill(home / "dev/new/apm_modules/x/.claude/skills", "demo", scripts=["post_demo.sh"])
    # Codex clones its marketplaces under .tmp in each Codex home; agents load no skill there.
    skill(home / ".codex/.tmp/marketplaces/x/.agents/skills", "demo", scripts=["post_demo.sh"])
    skill(home / ".omnigent/codex-native/abc/codex-home/.tmp/marketplaces/x/.claude/skills", "demo", scripts=["post_demo.sh"])
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
    assert sorted(result.stdout.splitlines()) == [f"stale skill copy: {home}/{d}/demo: post_demo.sh" for d in stale]
    assert (clean.returncode, clean.stdout) == (0, ""), clean.stdout + clean.stderr


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
        [str(home / ".local/bin/dotagents"), "doctor"], env={**os.environ, "HOME": str(home)},
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
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
        f"stale skill copy: {home}/.agents/skills/orchestrating-agents: herdr_watch.sh",
        f"stale skill copy: {home}/dev/old/.agents/skills/demo: post_demo.sh",
    ]
    assert sorted(doctor(repo, home, tmp_path / "bin").stdout.splitlines()) == expected
    run_install(repo, home, "--profile", "vps")
    assert doctor(repo, home, tmp_path / "bin").stdout.splitlines() == expected[1:]
