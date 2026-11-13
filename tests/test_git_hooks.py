import shutil
import subprocess

import pytest
from test_install_subsets import ROOT, make_checkout, run_install

pytestmark = pytest.mark.skipif(shutil.which("pre-commit") is None, reason="pre-commit is not installed")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def test_install_wires_pre_commit_and_pre_push_and_moves_an_old_hooks_path_over(tmp_path):
    repo, home = make_checkout(tmp_path)
    shutil.copy2(ROOT / ".pre-commit-config.yaml", repo / ".pre-commit-config.yaml")
    assert git(repo, "init", "-q").returncode == 0
    git(repo, "config", "core.hooksPath", ".githooks")  # a clone from before the pre-commit hooks

    result = run_install(repo, home, "--profile", "vps")
    assert result.returncode == 0, result.stdout + result.stderr
    assert git(repo, "config", "--local", "--get", "core.hooksPath").stdout == ""
    for hook in ("pre-commit", "pre-push"):
        assert (repo / ".git/hooks" / hook).is_file()

    again = run_install(repo, home, "--profile", "vps")
    assert again.returncode == 0 and "HOOKED" not in again.stdout  # idempotent
