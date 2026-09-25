import os
import subprocess
from pathlib import Path


GUARD = Path(__file__).resolve().parents[1] / "lib/postcheckout-guard.sh"


def run_guard(tmp_path, config, pre_commit_exit):
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
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
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
