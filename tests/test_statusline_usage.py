import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "home/.claude/statusline.sh"


def run(home, five):
    data = {"rate_limits": {"five_hour": {"used_percentage": five}, "seven_day": {"used_percentage": 20}}}
    r = subprocess.run(
        ["bash", str(SCRIPT)],
        input=json.dumps(data),
        text=True,
        capture_output=True,
        env={**os.environ, "HOME": str(home)},
    )
    assert r.returncode == 0, r.stderr


@pytest.mark.skipif(not shutil.which("jq"), reason="statusline.sh needs jq")
def test_history_appends_only_on_change(tmp_path):
    run(tmp_path, 10)
    run(tmp_path, 10)
    jsonl = tmp_path / ".cache/claude-usage.jsonl"
    assert len(jsonl.read_text().splitlines()) == 1
    run(tmp_path, 11)
    lines = jsonl.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["rate_limits"]["five_hour"]["used_percentage"] == 11
