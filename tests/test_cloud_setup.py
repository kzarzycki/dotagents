"""cloud-setup.sh installs mise and the pinned tools in a cloud session, and never fails it (#216)."""

import os
import subprocess
from pathlib import Path

SETUP = Path(__file__).resolve().parents[1] / ".claude" / "cloud-setup.sh"
STEPS = ["mise-trust", "mise-offline", "uv", "apm", "python", "gitleaks", "pre-commit", "mise-install"]


def test_every_step_is_logged_and_the_script_exits_zero_with_no_network(tmp_path: Path) -> None:
    """Release downloads and mise itself are unreachable here: each step logs its failure, and the exit stays 0."""
    home, repo, log = tmp_path / "home", tmp_path / "repo", tmp_path / "setup.log"
    home.mkdir()
    repo.mkdir()
    (repo / "mise.toml").write_text('[tools]\n"github:microsoft/apm" = "0.30.0"\n')
    nowhere = (tmp_path / "none").as_uri()
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "CLOUD_SETUP_LOG": str(log),
        "CLOUD_SETUP_REPO": str(repo),
        "CLOUD_SETUP_RELEASES": nowhere,
        "CLOUD_SETUP_GH_QUOTA": nowhere,
    }
    r = subprocess.run(["bash", str(SETUP)], env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    lines = log.read_text().splitlines()
    for step in ["gh-quota", "mise", *STEPS]:
        assert any(line.startswith(f"{step}: exit ") for line in lines), (step, lines)
    assert "FAILED: mise" in lines
    assert any(line.startswith("setup done") for line in lines)
