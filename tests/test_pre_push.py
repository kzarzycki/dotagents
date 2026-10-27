import os
import subprocess
from pathlib import Path


HOOKS = Path(__file__).resolve().parents[1] / ".githooks"


def test_suite_runs_outside_the_pushing_repo(tmp_path):
    # git exports GIT_DIR to a hook on a push from a linked worktree, which is how the loop
    # pushes; a test's `git init` then reinitializes the pushing repo instead of its temp dir.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name, body in {"pytest": f'git init -q "{tmp_path}/inner"', "mise": "true"}.items():
        (fake_bin / name).write_text(f"#!/bin/sh\n{body}\n")
        (fake_bin / name).chmod(0o755)
    env = {**env, "HOME": str(tmp_path), "PATH": f"{fake_bin}:{env['PATH']}"}

    def git(*args, cwd=tmp_path):
        return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True)

    repo = tmp_path / "repo"
    git("init", "-q", "--bare", "origin.git")
    git("init", "-q", str(repo))
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x", cwd=repo)
    git("worktree", "add", "-q", "../wt", cwd=repo)
    git("config", "core.hooksPath", str(HOOKS), cwd=repo)
    git("push", "-q", "../origin.git", "HEAD:main", cwd=tmp_path / "wt")
    assert git("config", "core.bare", cwd=repo).stdout == "false\n"
    assert (tmp_path / "inner/.git").is_dir()
