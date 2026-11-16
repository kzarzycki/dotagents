import json
import subprocess

import pytest

from test_omnigent_only import HOOK

RULES = "# heavy toolchains\nswift build\nswift test  # why\nswiftc\nxcodebuild\n"


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
    ],
)
def test_allowed_on_a_host_with_the_rules(tmp_path, command):
    r = hook(tmp_path, command)
    assert (r.returncode, r.stderr) == (0, ""), command


@pytest.mark.parametrize("rules", [None, "", "# nothing\n"])
def test_host_without_rules_forbids_nothing(tmp_path, rules):
    assert hook(tmp_path, "swift build", rules).returncode == 0
