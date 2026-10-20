import json

from test_install_subsets import make_checkout, run_install


def test_install_keeps_host_settings_the_repo_does_not_set(tmp_path):
    repo, home = make_checkout(tmp_path)
    settings = home / ".claude/settings.json"
    assert run_install(repo, home, "--profile", "vps").returncode == 0
    fresh = json.loads(settings.read_text())

    host = json.loads(settings.read_text())
    host["model"] = "opus"
    host["env"]["CLAUDE_CODE_ENABLE_TELEMETRY"] = "0"
    host["permissions"]["allow"].append("Bash(host-only:*)")
    host["permissions"]["additionalDirectories"] = ["/srv/host"]
    host["enabledPlugins"] = {"stale@host-market": False, "ponytail@host-market": True}
    host["extraKnownMarketplaces"]["host-market"] = {"source": {"source": "github", "repo": "x/y"}}
    settings.write_text(json.dumps(host, indent=2) + "\n")

    result = run_install(repo, home, "--profile", "vps")
    assert result.returncode == 0, result.stdout + result.stderr
    got = json.loads(settings.read_text())
    assert got["model"] == "opus"
    assert got["env"] == fresh["env"] and got["hooks"] == fresh["hooks"]
    assert got["permissions"]["allow"] == fresh["permissions"]["allow"] + ["Bash(host-only:*)"]
    assert got["permissions"]["additionalDirectories"] == ["/srv/host"]
    assert got["enabledPlugins"] == {"ponytail@host-market": True}
    assert got["extraKnownMarketplaces"] == {**fresh["extraKnownMarketplaces"], "host-market": host["extraKnownMarketplaces"]["host-market"]}
    # The printed diff carries only the repo's changes.
    changed = [l for l in result.stdout.splitlines() if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]
    assert changed == [
        '-    "CLAUDE_CODE_ENABLE_TELEMETRY": "0",',
        '+    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",',
        '-    "stale@host-market": false,',
    ], result.stdout

    before = settings.read_bytes()
    result = run_install(repo, home, "--profile", "vps")
    assert result.returncode == 0 and "UPDATED" not in result.stdout
    assert settings.read_bytes() == before


def test_unparsable_host_settings_are_left_alone(tmp_path):
    repo, home = make_checkout(tmp_path)
    settings = home / ".claude/settings.json"
    settings.parent.mkdir()
    settings.write_text("{ not json")
    result = run_install(repo, home, "--profile", "vps")
    assert result.returncode == 1 and "left unchanged" in result.stderr
    assert settings.read_text() == "{ not json"
