import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def make_checkout(tmp_path):
    repo = tmp_path / "repo"
    (repo / "bin").mkdir(parents=True)
    shutil.copy2(ROOT / "bin/dotagents", repo / "bin/dotagents")
    shutil.copytree(ROOT / "home", repo / "home", symlinks=True)
    (repo / "home/.omp/agent/config.yml.lock").touch()
    home = tmp_path / "home"
    home.mkdir()
    return repo, home


def run_install(repo, home, *args):
    return subprocess.run(
        ["/bin/bash", str(repo / "bin/dotagents"), "install", "--no-pull", *args],
        env={**os.environ, "HOME": str(home)},
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_subset_install_selects_payload_and_skips_runtime_effects(tmp_path):
    repo, home = make_checkout(tmp_path)
    result = run_install(repo, home, "--only", "omp")

    assert result.returncode == 0, result.stdout + result.stderr
    assert (home / ".omp/agent/config.yml").is_symlink()
    assert (home / ".omp/agent/extensions/herdr-omp-agent-state.ts").is_symlink()
    assert not (home / ".omp/agent/config.yml.lock").exists()
    assert not (home / ".claude").exists()
    assert not (home / ".agents").exists()
    assert not (home / ".dotagents").exists()
    assert not (home / ".dotagents-profile").exists()


def test_subset_install_accepts_dot_name_and_repeats_idempotently(tmp_path):
    repo, home = make_checkout(tmp_path)
    for _ in range(2):
        result = run_install(repo, home, "--only=.omp", "--only", "omp")
        assert result.returncode == 0, result.stdout + result.stderr
    assert (home / ".omp/agent/config.yml").is_symlink()
    assert len(list((home / ".omp/agent").glob("config.yml*"))) == 1


def test_unknown_subset_fails_before_mutating_home(tmp_path):
    repo, home = make_checkout(tmp_path)
    result = run_install(repo, home, "--only", "missing")

    assert result.returncode == 2
    assert "unsupported --only value" in result.stderr
    assert list(home.iterdir()) == []


def test_install_keeps_the_pinned_pack_at_its_lock(tmp_path):
    """A changed apm.lock.yaml installs the pinned pack once per checkout; the same lock again installs nothing."""
    repo, home = make_checkout(tmp_path)
    calls, bindir = tmp_path / "mise-calls", tmp_path / "bin"
    bindir.mkdir()
    # A failing install still creates the skills dir, as a deploy cut short would.
    (bindir / "mise").write_text(
        f'#!/bin/sh\necho "$PWD $*" >> {calls}\nmkdir -p .agents/skills\n[ -f fail ] && exit 1\nexit 0\n')
    (bindir / "mise").chmod(0o755)
    env = {**os.environ, "HOME": str(home), "PATH": f"{bindir}:{os.environ['PATH']}"}

    def install(checkout=repo, *args, code=0):
        result = subprocess.run(
            ["/bin/bash", str(checkout / "bin/dotagents"), "install", "--no-pull", "--only", ".agents", *args],
            env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode == code, result.stdout + result.stderr
        return result

    def count():
        return calls.read_text().count("apm install --frozen") if calls.exists() else 0

    install()  # a checkout without a lock installs no pack
    assert count() == 0
    (repo / "apm.lock.yaml").write_text("pin: 1\n")
    assert "DRY: cd" in install(repo, "--dry-run").stdout
    assert count() == 0 and not (home / ".local/state/dotagents").exists()
    assert "INSTALLED: the pinned pack" in install().stdout
    install()
    assert calls.read_text() == f"{repo} exec -- apm install --frozen\n"
    shutil.rmtree(repo / ".agents/skills")  # a deleted pack reinstalls under the same lock
    install()
    assert count() == 2

    other = tmp_path / "other"  # a second checkout's install doesn't stand in for this one's
    shutil.copytree(repo, other, symlinks=True)
    shutil.rmtree(other / ".agents")
    (other / "apm.lock.yaml").write_text("pin: 2\n")
    install(other)
    (repo / "apm.lock.yaml").write_text("pin: 2\n")
    install()
    assert count() == 4

    shutil.rmtree(repo / ".agents/skills")  # the lock is the recorded one: only the record's drop makes a retry
    (repo / "fail").touch()
    assert "could not install the pinned pack" in install(code=1).stderr  # a failure fails the install
    install(code=1)  # the failed attempt left its skills dir, and still the next install retries
    assert count() == 6
    (repo / "fail").unlink()
    install()
    install()
    assert count() == 7
