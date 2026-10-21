import json
import shutil
import subprocess

import pytest

from test_install_subsets import ROOT

HOOK = ROOT / "home/.claude/hooks/omnigent-only.py"
RULES = ROOT / "home/.codex/rules/omnigent-only.rules"

DENIED = [
    "claude -p hi", "claude --print hi", "claude --model haiku -p hi", "/home/x/.local/bin/claude -p hi",
    "codex exec 'fix it'", "codex e hi", "omp", "omp 'do the thing'", "omp commit", "gemini -p hi",
    "agy -p hi", "agy --prompt hi", "cd x && claude -p hi", "ls | claude -p hi", "FOO=1 claude -p hi",
    "env FOO=1 claude -p hi", "timeout 60 codex exec hi", "nohup omp hi &", "x=$(claude -p hi)",
    "bash -lc 'claude -p hi'", 'sh -c "codex exec hi"', "true\nclaude -p hi", "(claude -p hi)",
    "echo `claude -p hi`",
]
ALLOWED = [
    "grep claude file", "grep -r 'claude -p' docs", "claude --version", "claude mcp list", "omp --version",
    "codex --version", "codex execpolicy check --rules r -- ls", "ls ~/.claude", "cat /usr/bin/claude",
    "echo 'claude -p hi'", "git commit -m 'run codex exec'", "agy agents", "gemini --version",
    "python3 omnigent_agent.py run claude t b r", "python3 omnigent_agent.py status s1",
    "cat > f <<'EOF'\nclaude -p hi\ncodex exec x\nEOF\necho done", "cat <<EOF\nomp\nEOF", "echo 'unbalanced",
    "cat <<<claude", "",
]


def hook(command):
    return subprocess.run(
        ["python3", str(HOOK)], input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True, text=True, timeout=10,
    )


@pytest.mark.parametrize("command", DENIED)
def test_hook_denies_bare_agent_launch(command):
    result = hook(command)
    assert result.returncode == 2 and "omnigent_agent.py" in result.stderr, command


@pytest.mark.parametrize("command", ALLOWED)
def test_hook_allows_near_misses(command):
    result = hook(command)
    assert (result.returncode, result.stderr) == (0, ""), command


def test_hook_is_wired_for_bash():
    pre = json.loads((ROOT / "home/.claude/settings.shared.json").read_text())["hooks"]["PreToolUse"]
    assert {"matcher": "Bash", "hooks": [{"type": "command", "command": 'python3 "$HOME/.claude/hooks/omnigent-only.py"'}]} in pre


@pytest.mark.skipif(not shutil.which("codex"), reason="codex not installed")
@pytest.mark.parametrize("argv,forbidden", [
    (["claude", "-p", "hi"], True), (["codex", "exec", "hi"], True), (["codex", "e", "hi"], True),
    (["omp", "hi"], True), (["gemini", "-p", "hi"], True), (["agy", "--prompt", "hi"], True),
    (["claude", "--version"], False), (["codex", "execpolicy", "check"], False), (["agy", "agents"], False),
])
def test_codex_rules(argv, forbidden):
    out = subprocess.run(["codex", "execpolicy", "check", "--rules", str(RULES), "--", *argv],
                         capture_output=True, text=True, timeout=30, check=True).stdout
    assert ('"decision":"forbidden"' in out) == forbidden, out
