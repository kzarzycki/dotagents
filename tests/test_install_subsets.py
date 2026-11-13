import os
import shutil
import subprocess
import sys
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


def test_install_links_agent_hygiene_into_the_pinned_pack(tmp_path):
    """~/.local/bin/agent-hygiene, and disk-hygiene for one release, run the pinned pack's script."""
    repo, home = make_checkout(tmp_path)
    script = repo / ".agents/skills/agent-hygiene/scripts/agent-hygiene"
    script.parent.mkdir(parents=True)
    script.write_text("import sys\nprint('pack-script', *sys.argv[1:])\n")
    result = run_install(repo, home, "--only", ".local")
    assert result.returncode == 0, result.stdout + result.stderr
    for name in ("agent-hygiene", "disk-hygiene"):
        done = subprocess.run([str(home / ".local/bin" / name), "--dry-run"], capture_output=True, text=True)
        assert done.stdout == "pack-script --dry-run\n", (name, done.stdout, done.stderr)


def test_agent_hygiene_installs_a_missing_pack_on_its_next_run(tmp_path):
    """A failed pack install leaves a command that installs again when it next runs, not a dangling link."""
    repo, home = make_checkout(tmp_path)
    result = run_install(repo, home, "--only", ".local")
    assert result.returncode == 0, result.stdout + result.stderr
    calls = tmp_path / "install.calls"
    pack = repo / ".agents/skills/agent-hygiene/scripts"
    (repo / "bin/dotagents").write_text(  # stands for an install whose pack step fails while FAIL exists
        f'#!/bin/sh\necho "$@" >> {calls}\n[ -e {tmp_path}/FAIL ] && exit 42\n'
        f"mkdir -p {pack} && printf 'print(\"pack-script\")\\n' > {pack}/agent-hygiene\n"
    )
    (tmp_path / "FAIL").touch()
    env = {**os.environ, "HOME": str(home), "DISK_HYGIENE_FAILED": "exit 42: no network"}
    # the old disk-hygiene relaunches through its link with Python after its install failed
    done = subprocess.run([sys.executable, str(home / ".local/bin/disk-hygiene")], env=env, capture_output=True, text=True)
    assert done.returncode == 1 and "did not install it (the install before: exit 42: no network)" in done.stderr, done.stderr
    (tmp_path / "FAIL").unlink()
    done = subprocess.run([str(home / ".local/bin/agent-hygiene")], env={**os.environ, "HOME": str(home)}, capture_output=True, text=True)
    assert done.stdout == "pack-script\n", done.stdout + done.stderr
    assert calls.read_text() == "install --no-pull\ninstall --no-pull\n"
    done = subprocess.run([str(home / ".local/bin/agent-hygiene")], env={**os.environ, "HOME": str(home)}, capture_output=True, text=True)
    assert done.stdout == "pack-script\n" and calls.read_text().count("install") == 2, "a present pack installs nothing"
