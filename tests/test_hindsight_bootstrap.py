import json
import os
import subprocess
from pathlib import Path

import pytest

BOOTSTRAP = Path(__file__).resolve().parents[1] / "patches/hindsight/bootstrap.sh"


@pytest.mark.parametrize(
    ("profile", "url"),
    [
        ("mac", "https://cc-experiments.taile39822.ts.net:9077"),
        ("vps", "http://127.0.0.1:9077"),
    ],
)
def test_bootstrap_preserves_private_settings_and_refuses_invalid_json(tmp_path, profile, url):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".dotagents-profile").write_text(profile + "\n")
    omp_env = home / ".omp/agent/.env"
    omp_env.parent.mkdir(parents=True)
    omp_env.write_text("OTHER_KEY=untouched\nHINDSIGHT_API_URL=http://old.invalid\n")
    config = home / ".hindsight/coding-agent.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"apiToken": "private-value", "customSetting": 42}))

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    npx = bin_dir / "npx"
    npx.write_text('#!/bin/sh\nprintf "%s\\n" "$@" >> "$HOME/npx.log"\n')
    npx.chmod(0o755)
    env = {**os.environ, "HOME": str(home), "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    env.pop("CLAUDE_CODE_REMOTE", None)

    def run():
        return subprocess.run(
            ["/bin/bash", str(BOOTSTRAP)], env=env, capture_output=True, text=True, timeout=20, check=False
        )

    assert run().returncode == 0
    installed = json.loads(config.read_text())
    assert installed["apiToken"] == "private-value"
    assert installed["customSetting"] == 42
    assert installed["serverMode"] == "self-hosted"
    assert installed["apiUrl"] == url
    assert config.stat().st_mode & 0o777 == 0o600
    assert omp_env.read_text() == f"OTHER_KEY=untouched\nHINDSIGHT_API_URL={url}\n"
    assert omp_env.stat().st_mode & 0o777 == 0o600
    assert run().returncode == 0
    assert json.loads(config.read_text()) == installed

    called = (home / "npx.log").read_text()
    config.write_text("{invalid")
    assert run().returncode != 0
    assert (home / "npx.log").read_text() == called
    assert config.read_text() == "{invalid"
    assert omp_env.read_text() == f"OTHER_KEY=untouched\nHINDSIGHT_API_URL={url}\n"


def test_bootstrap_refuses_a_company_machine_profile(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".dotagents-profile").write_text("mac,work\n")
    env = {**os.environ, "HOME": str(home)}
    env.pop("CLAUDE_CODE_REMOTE", None)
    result = subprocess.run(
        ["/bin/bash", str(BOOTSTRAP)], env=env, capture_output=True, text=True, timeout=20, check=False
    )
    assert result.returncode == 1 and "stays off the homelab" in result.stderr
    assert not (home / ".hindsight").exists()
