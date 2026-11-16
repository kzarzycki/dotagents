import json
import subprocess

import pytest

from test_omnigent_only import HOOK

RULES = "# heavy toolchains\nswift build\nswift test  # why\nswiftc\nxcodebuild\napprovals.py local-ci\n"


def hook(tmp_path, command, rules=RULES):
    if rules is not None:
        (tmp_path / ".agents").mkdir()
        (tmp_path / ".agents/host-commands").write_text(rules)
    return subprocess.run(
        ["python3", str(HOOK)],
        input=json.dumps({"tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        timeout=10,
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )


@pytest.mark.parametrize(
    "command",
    [
        "swift build",
        "swift build -c release",
        "cd Core && swift test --filter X",
        "swiftc main.swift",
        "xcodebuild -scheme A",
        "swiftly run swift build",
        "FOO=1 timeout 60 swift test",
        "bash -lc 'swift build'",
        "/usr/bin/swift build",
        "swiftly run /opt/tc/bin/swift build",
        "uv run /any/path/approvals.py local-ci 12",
        "uv run python3 scripts/approvals.py local-ci --record",
        "python3 ./approvals.py local-ci",
        "python approvals.py local-ci",
        "cd x && uv run engineering/skills/engineering-loop/scripts/approvals.py local-ci",
    ],
)
def test_refused_with_rule_and_pointer(tmp_path, command):
    r = hook(tmp_path, command)
    assert r.returncode == 2, command
    assert r.stderr.startswith("Denied `") and "forbids `" in r.stderr and "claude-cloud worker" in r.stderr


@pytest.mark.parametrize(
    "command",
    [
        "./gradlew assembleDebug",  # compiles Core with Swift for Android underneath
        "cd android && ./gradlew :app:assembleDebug -Pswift=1",
        "swift --version",
        "echo swift test",
        "grep swiftc Package.swift",
        "git commit -m 'swift build fix'",
        "uv run approvals.py land 12",
        "echo uv run approvals.py local-ci",
        "python3 -c 'print(1)'",
    ],
)
def test_allowed_on_a_host_with_the_rules(tmp_path, command):
    r = hook(tmp_path, command)
    assert (r.returncode, r.stderr) == (0, ""), command


@pytest.mark.parametrize("rules", [None, "", "# nothing\n"])
def test_host_without_rules_forbids_nothing(tmp_path, rules):
    assert hook(tmp_path, "swift build", rules).returncode == 0


@pytest.mark.parametrize(
    "command, shown",
    [("swift build -c release", "swift build -c release"), ("cd Core && timeout 60 swift test -x", "swift test -x")],
)
def test_refusal_names_the_refused_command(tmp_path, command, shown):
    assert hook(tmp_path, command).stderr.startswith(f"Denied `{shown}`: this host's config forbids `")
