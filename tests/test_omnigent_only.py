import json
import shutil
import subprocess

import pytest

from test_install_subsets import ROOT

HOOK = ROOT / "home/.claude/hooks/omnigent-only.py"
RULES = ROOT / "home/.codex/rules/omnigent-only.rules"

DENIED = [
    "claude -p hi", "claude --print hi", "claude --model haiku -p hi", "/home/x/.local/bin/claude -p hi",
    "codex exec 'fix it'", "codex e hi", "codex review", "omp", "omp 'do the thing'", "omp commit", "gemini -p hi",
    "agy -p hi", "agy --prompt hi", "cd x && claude -p hi", "ls | claude -p hi", "FOO=1 claude -p hi",
    "env FOO=1 claude -p hi", "timeout 60 codex exec hi", "nohup omp hi &", "x=$(claude -p hi)",
    "bash -lc 'claude -p hi'", 'sh -c "codex exec hi"', "true\nclaude -p hi", "(claude -p hi)",
    "echo `claude -p hi`", "# start the worker\nclaude -p go", "cd repo  # go\ncodex exec fix",
    "curl -s http://h/#x; claude -p hi", "echo ${#a[@]}; claude -p hi", "for i in 1; do claude -p hi; done",
    "while true; do codex exec x; done", "if true; then claude -p hi; fi", "{ claude -p hi; }", "! claude -p hi",
    "# don't forget\nclaude -p hi", "claude -p hi  # it's the reviewer", "cd repo  # let's go\ncodex exec fix",
]
ALLOWED = [
    "grep claude file", "grep -r 'claude -p' docs", "claude --version", "claude mcp list", "omp --version",
    "codex --version", "codex execpolicy check --rules r -- ls", "ls ~/.claude", "cat /usr/bin/claude",
    "echo 'claude -p hi'", "git commit -m 'run codex exec'", "agy agents", "gemini --version",
    "python3 omnigent_agent.py run claude t b r", "python3 omnigent_agent.py status s1",
    "cat > f <<'EOF'\nclaude -p hi\ncodex exec x\nEOF\necho done", "cat <<EOF\nomp\nEOF", "echo 'unbalanced",
    "cat <<<claude", "", "omp --upgrade-status", "omp safe-update", "omp config path",
    "claude mcp add srv -- docker run -i -p 8080:8080 img", "codex mcp add x -- server --mode e",
    "command -v omp", "command -v omp >/dev/null && omp --version",
    "if ! command -v omp >/dev/null 2>&1; then echo missing; fi", "! command -v omp",
]

KILL_DENIED = [
    "pkill -f 'local-ci --record'", "killall java", "pkill node", "pkill -9 node", "pkill -TERM -f gate-runner",
    "pkill -x java", "killall -9 java", "sudo pkill -f build", "cd x && pkill -f 'mise run'", "echo $(pkill -f gate)",
    "echo `pkill gate`", "true; pkill gate", "bash -c 'pkill -f gate'", "for p in a; do pkill $p; done",
    "pkill -u 1000 node", "pkill --signal TERM gate", "pkill -f gate-runner || true", "pkill -SIGKILL gate",
]
KILL_ALLOWED = [
    "kill 1234", "kill -TERM -1234", "kill -9 -- -1234", "pkill -P 1234", "pkill -g 1234", "pkill -9 -P 1234",
    "pkill -fP 1234 run", "pkill -P1234", "pkill --parent 1234", "pkill --pgroup=1234 gate", "pkill -SIGPIPE -g 7",
    "pkill -f /work/wt/run.sh", "pkill -f '/work/wt/run.sh --record'", "pkill -f \"$PWD/run.sh\"", "pkill",
    "grep -r pkill docs", "echo 'killall java'", "git commit -m 'pkill -f x'", "which pkill", "cat <<EOF\nkillall java\nEOF",
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
    (["claude", "-p", "hi"], True), (["codex", "exec", "hi"], True), (["codex", "e", "hi"], True), (["codex", "review"], True),
    (["omp", "hi"], True), (["gemini", "-p", "hi"], True), (["agy", "--prompt", "hi"], True),
    (["claude", "--version"], False), (["codex", "execpolicy", "check"], False), (["agy", "agents"], False),
])
def test_codex_rules(argv, forbidden):
    out = subprocess.run(["codex", "execpolicy", "check", "--rules", str(RULES), "--", *argv],
                         capture_output=True, text=True, timeout=30, check=True).stdout
    assert ('"decision":"forbidden"' in out) == forbidden, out


@pytest.mark.parametrize("command", KILL_DENIED)
def test_hook_denies_kill_by_shared_name(command):
    result = hook(command)
    assert result.returncode == 2 and "process group" in result.stderr, command


@pytest.mark.parametrize("command", KILL_ALLOWED)
def test_hook_allows_scoped_kill(command):
    result = hook(command)
    assert (result.returncode, result.stderr) == (0, ""), command
