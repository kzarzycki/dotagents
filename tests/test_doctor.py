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
    bindir = tmp_path / "bin"
    fake_tool(bindir, "dtool", "2.87.0")

    result = doctor(repo, home, bindir)
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        "too old: dtool 2.87.0, skill demo needs >= 2.99.0",
        "missing: dother, needed by skill demo",
    ]

    fake_tool(bindir, "dtool", "2.103.1")
    fake_tool(bindir, "dother", "1")
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
    # An old pin in a project, and the same in its .claude copy.
    for d in (".agents/skills", ".claude/skills"):
        skill(home / "dev/old" / d, "demo", scripts=["demo.sh", "post_demo.sh"])
    # Current copies, a pack source tree and the apm cache are not reported.
    skill(home / "dev/new/.claude/skills", "demo", scripts=["demo.sh"])
    skill(home / "dev/src/engineering/skills", "demo", scripts=["post_demo.sh"])
    skill(home / ".cache/apm/x/engineering/skills", "demo", scripts=["post_demo.sh"])
    skill(home / ".agents/skills", "other", scripts=["any.sh"])

    result = doctor(repo, home, tmp_path / "bin")
    assert result.returncode == 1, result.stdout + result.stderr
    assert sorted(result.stdout.splitlines()) == [
        f"stale skill copy: {home}/dev/old/{d}/demo: post_demo.sh" for d in (".agents/skills", ".claude/skills")
    ]


def test_doctor_asks_for_the_pinned_pack_when_it_is_not_installed(tmp_path):
    repo, home = make_checkout(tmp_path)
    result = doctor(repo, home, tmp_path / "bin")
    assert result.returncode == 1
    assert "no pinned pack: run `mise run setup:dev`" in result.stdout


def test_install_provides_a_declared_tool_through_mise_and_doctor_passes(tmp_path, monkeypatch):
    repo, home = make_checkout(tmp_path)
    skill(repo / ".agents/skills", "demo", requires="dtool>=2.99.0", scripts=["demo.sh"])
    bindir, shims = tmp_path / "bin", tmp_path / "mise/shims"
    fake_tool(bindir, "dtool", "2.87.0")
    # A mise whose `use -g dtool@latest` puts a current dtool in its shims dir.
    (bindir / "mise").write_text(
        f'#!/bin/sh\n[ "$*" = "use -g dtool@latest" ] || exit 9\nmkdir -p {shims}\n'
        f"printf '#!/bin/sh\\necho dtool version 2.103.1\\n' > {shims}/dtool\nchmod +x {shims}/dtool\n"
    )
    (bindir / "mise").chmod(0o755)
    monkeypatch.setenv("MISE_DATA_DIR", str(tmp_path / "mise"))
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")

    result = run_install(repo, home, "--profile", "vps")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PROVIDED: dtool 2.103.1 via mise, for skill demo" in result.stdout
    assert os.readlink(home / ".local/bin/dtool") == f"{shims}/dtool"

    result = run_install(repo, home, "--profile", "vps")
    assert f"TOOL: dtool 2.103.1 at {home}/.local/bin/dtool, for skill demo (needs >= 2.99.0)" in result.stdout
    assert (doctor(repo, home, bindir).returncode, doctor(repo, home, bindir).stdout) == (0, "")
