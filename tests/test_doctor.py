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
    skill(home / "dev/new/apm_modules/x/.claude/skills", "demo", scripts=["post_demo.sh"])
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
        f'#!/bin/sh\ncase "$*" in "use -g nosuch@latest") exit 1;; "use -g "*@latest) t=${{3%@latest}};; *) exit 9;; esac\n'
        f"mkdir -p {shims}\n{current.replace('{d}', str(shims))}\n"
    )
    (bindir / "brew").write_text(
        f'#!/bin/sh\ncase "$1" in --prefix) echo {brew};; upgrade) t=$2; {current.replace("{d}", str(brew / "bin"))};; *) exit 9;; esac\n'
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
    # A tool mise can't provide leaves no link to a shim that isn't there.
    assert "WARNING: mise did not provide nosuch >= any for skill demo" in result.stderr
    assert not (home / ".local/bin/nosuch").is_symlink()
