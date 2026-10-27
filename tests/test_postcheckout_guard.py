import os
import subprocess
from pathlib import Path


GUARD = Path(__file__).resolve().parents[1] / "lib/postcheckout-guard.sh"


def run_guard(tmp_path, config, pre_commit_exit, extra_env=None):
    repo = tmp_path / "repo"
    repo.mkdir()
    if config is not None:
        (repo / ".pre-commit-config.yaml").write_text(config)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "calls"
    fake = fake_bin / "pre-commit"
    fake.write_text(f'#!/bin/sh\necho "$@" >> {log}\nexit {pre_commit_exit}\n')
    fake.chmod(0o755)
    result = subprocess.run(
        ["/bin/bash", str(GUARD), "0" * 40, "1" * 40, "1"],
        cwd=repo,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}", **(extra_env or {})},
        capture_output=True,
        text=True,
    )
    return result, log.read_text() if log.exists() else ""


STAGELESS = "repos:\n- repo: local\n  hooks:\n  - id: fmt\n    entry: fmt\n    language: system\n"


def test_no_config_is_a_noop(tmp_path):
    result, calls = run_guard(tmp_path, None, 1)
    assert result.returncode == 0 and calls == ""


def test_stageless_hooks_do_not_run_on_checkout(tmp_path):
    result, calls = run_guard(tmp_path, STAGELESS, 1)
    assert result.returncode == 0 and calls == ""


def test_opted_in_repo_delegates_and_never_fails_checkout(tmp_path):
    config = "default_install_hook_types: [pre-commit, post-checkout]\n" + STAGELESS
    result, calls = run_guard(tmp_path, config, 3)
    assert result.returncode == 0
    assert "--hook-type=post-checkout" in calls
    assert "exit 3" in result.stderr


def test_parked_as_legacy_leaves_delegation_to_pre_commit(tmp_path):
    config = "default_install_hook_types: [pre-commit, post-checkout]\n" + STAGELESS
    result, calls = run_guard(tmp_path, config, 0, {"PRE_COMMIT_RUNNING_LEGACY": "1"})
    assert result.returncode == 0 and calls == ""


def test_lfs_repo_gets_the_slot_back_for_git_lfs(tmp_path):
    # git-lfs stops installing its hooks at a post-checkout it didn't write, so an LFS clone
    # through the template would have no lock hooks (post-checkout, post-commit, post-merge).
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}  # a git hook running pytest sets GIT_DIR
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "--template=", str(repo)], check=True, env=env)
    (repo / ".gitattributes").write_text("*.bin filter=lfs diff=lfs merge=lfs -text\n")
    hook = repo / ".git/hooks/post-checkout"
    hook.parent.mkdir()
    hook.write_bytes(GUARD.read_bytes())
    hook.chmod(0o755)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "calls"
    fake = fake_bin / "git-lfs"
    fake.write_text(f'#!/bin/sh\necho "$@" >> {log}\n')
    fake.chmod(0o755)
    result = subprocess.run(
        [str(hook), "0" * 40, "1" * 40, "1"],
        cwd=repo,
        env={**env, "PATH": f"{fake_bin}:{env['PATH']}"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert not hook.exists()
    assert log.read_text().splitlines() == ["update", f"post-checkout {'0' * 40} {'1' * 40} 1"]
