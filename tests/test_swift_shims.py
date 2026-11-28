import subprocess
import sys

import pytest
from test_install_subsets import ROOT, make_checkout, run_install

SHIMS = ROOT / "home/.claude/hooks/swift-shims"
ENV_SH = ROOT / "home/.agents/env.sh"
CALL = "import subprocess,sys; sys.exit(subprocess.run(['swift','build','-c','release']).returncode)"


@pytest.fixture
def host(tmp_path):
    (tmp_path / ".agents").mkdir()
    (tmp_path / ".agents/host-commands").write_text("# heavy\nswift build\nswift test\n")
    real = tmp_path / "real"
    real.mkdir()
    for name in ("swift", "swift-build", "swift-test"):
        (real / name).write_text(f'#!/bin/sh\necho REAL {name} "$@"\n')
        (real / name).chmod(0o755)
    (tmp_path / "load").write_text("0.50\n")
    # Test-only load injection: a sitecustomize patches the system reading the shim takes.
    (tmp_path / "site").mkdir()
    (tmp_path / "site/sitecustomize.py").write_text(
        f"import os\nos.getloadavg = lambda: (float(open({str(tmp_path / 'load')!r}).read()), 0.0, 0.0)\n"
    )
    env = {"HOME": str(tmp_path), "PATH": f"{SHIMS}:{real}:/usr/bin:/bin", "PYTHONPATH": str(tmp_path / "site")}
    return tmp_path, env


def nested(env, **extra):
    # A script, not the command line: the hook never sees this call.
    return subprocess.run(
        [sys.executable, "-c", CALL], env={**env, **extra}, capture_output=True, text=True, timeout=30, check=False
    )


def test_nested_call_refused_with_the_rule(host):
    _, env = host
    r = nested(env)
    assert r.returncode != 0 and "REAL" not in r.stdout
    assert "forbids `swift build`" in r.stderr and "host-commands" in r.stderr and "SWIFT_ON_HOST_ALLOWED" in r.stderr


def test_allowed_flag_runs_the_real_binary_under_load_10(host):
    tmp, env = host
    (tmp / "load").write_text("9.99\n")
    r = nested(env, SWIFT_ON_HOST_ALLOWED="1")
    assert r.returncode == 0 and r.stdout.strip() == "REAL swift build -c release"


@pytest.mark.parametrize("load", ["10.00", "138.2"])
def test_refused_at_load_10_or_more_even_when_allowed(host, load):
    tmp, env = host
    (tmp / "load").write_text(f"{load}\n")
    r = nested(env, SWIFT_ON_HOST_ALLOWED="1")
    assert r.returncode != 0 and "REAL" not in r.stdout and "load is" in r.stderr


def test_other_swift_calls_pass_and_alias_shims_are_refused(host):
    _, env = host
    ok = subprocess.run(["swift", "--version"], env=env, capture_output=True, text=True, check=False)
    assert ok.returncode == 0 and ok.stdout.strip() == "REAL swift --version"
    for name in ("swift-build", "swift-test"):
        r = subprocess.run([name], env=env, capture_output=True, text=True, check=False)
        assert r.returncode != 0 and "REAL" not in r.stdout, name


def test_no_rule_passes_through(host):
    tmp, env = host
    (tmp / ".agents/host-commands").write_text("xcodebuild\n")
    r = nested(env)
    assert r.returncode == 0 and "REAL swift build" in r.stdout


def env_sh_path(tmp_path, rules):
    if rules is not None:
        (tmp_path / ".agents").mkdir(exist_ok=True)
        (tmp_path / ".agents/host-commands").write_text(rules)
    hooks = tmp_path / ".claude/hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    (hooks / "omnigent-only.py").unlink(missing_ok=True)
    (hooks / "omnigent-only.py").symlink_to(ROOT / "home/.claude/hooks/omnigent-only.py")
    r = subprocess.run(
        ["sh", "-c", f'. {ENV_SH}; echo "$PATH"'],
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    return r.stdout.strip()


def test_env_sh_installs_shims_only_with_a_swift_rule(tmp_path):
    shims = f"{tmp_path}/.claude/hooks/swift-shims"
    path = env_sh_path(tmp_path, "swift build\n").split(":")
    assert shims in path and path.index(shims) < path.index("/usr/bin")


@pytest.mark.parametrize("rules", [None, "", "xcodebuild\n", "# swift build\nswiftc\n"])
def test_env_sh_no_shims_without_a_swift_rule(tmp_path, rules):
    assert "swift-shims" not in env_sh_path(tmp_path, rules)


def test_refusal_names_the_configured_hosts(host):
    tmp, env = host
    (tmp / ".agents/swift-hosts").write_text("# where Swift runs\nbuild-host-example\nmac-example  # note\n")
    r = nested(env)
    assert r.returncode != 0 and "Swift runs on: build-host-example, mac-example." in r.stderr


def test_the_shim_ignores_a_load_fixture_variable(host):
    tmp, env = host
    (tmp / "load").write_text("138.2\n")
    fixture = tmp / "fixture"
    fixture.write_text("0.1 0 0 1/1 1\n")
    r = nested(env, SWIFT_ON_HOST_ALLOWED="1", SWIFT_SHIM_LOAD_FILE=str(fixture), SWIFT_SHIM_LOAD="0.1")
    assert r.returncode != 0 and "REAL" not in r.stdout


def test_an_invalid_byte_in_the_rules_keeps_the_valid_rules(host):
    tmp, env = host
    (tmp / ".agents/host-commands").write_bytes(b"swift build\n# caf\xe9\n")
    assert nested(env).returncode != 0
    shims = f"{tmp}/.claude/hooks/swift-shims"
    assert shims in env_sh_path(tmp, None).split(":")


def test_env_sh_keeps_the_shims_when_the_rules_cannot_be_read(tmp_path):
    (tmp_path / ".agents").mkdir()
    (tmp_path / ".agents/host-commands").mkdir()  # exists, unreadable as a file
    assert f"{tmp_path}/.claude/hooks/swift-shims" in env_sh_path(tmp_path, None).split(":")


@pytest.mark.parametrize(("rules", "linked"), [("swift build\n", True), ("xcodebuild\n", False), (None, False)])
def test_install_links_the_shims_only_with_a_swift_rule(tmp_path, rules, linked):
    repo, home = make_checkout(tmp_path)
    if rules is not None:
        (home / ".agents").mkdir()
        (home / ".agents/host-commands").write_text(rules)
    result = run_install(repo, home, "--only", "claude")
    assert result.returncode == 0, result.stdout + result.stderr
    shims = home / ".claude/hooks/swift-shims"
    assert shims.exists() is linked
    assert all((shims / n).is_symlink() for n in ("swift", "swift-build", "swift-test", "shim.py")) if linked else True
