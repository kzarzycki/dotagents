import subprocess
import sys

import pytest
from test_install_subsets import ROOT

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
    (tmp_path / "load").write_text("0.50 0.40 0.30 1/100 5\n")
    env = {
        "HOME": str(tmp_path),
        "PATH": f"{SHIMS}:{real}:/usr/bin:/bin",
        "SWIFT_SHIM_LOAD_FILE": str(tmp_path / "load"),
    }
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
    (tmp / "load").write_text("9.99 5 5 1/1 1\n")
    r = nested(env, SWIFT_ON_HOST_ALLOWED="1")
    assert r.returncode == 0 and r.stdout.strip() == "REAL swift build -c release"


@pytest.mark.parametrize("load", ["10.00", "138.2"])
def test_refused_at_load_10_or_more_even_when_allowed(host, load):
    tmp, env = host
    (tmp / "load").write_text(f"{load} 5 5 1/1 1\n")
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
    hooks.mkdir(parents=True)
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
