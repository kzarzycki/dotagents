import json

from test_install_subsets import make_checkout, run_install


def test_install_keeps_host_settings_the_repo_does_not_set(tmp_path):
    repo, home = make_checkout(tmp_path)
    settings = home / ".claude/settings.json"
    assert run_install(repo, home, "--profile", "vps").returncode == 0
    fresh = json.loads(settings.read_text())

    host = json.loads(settings.read_text())
    host["env"]["CLAUDE_CODE_ENABLE_TELEMETRY"] = "0"
    host["permissions"]["additionalDirectories"] = ["/srv/host"]
    host["enabledPlugins"] = {"stale@host-market": False, "ponytail@host-market": True}
    host["extraKnownMarketplaces"]["host-market"] = {"source": {"source": "github", "repo": "x/y"}}
    # Host key order differs from the repo's; it must not show up as a change.
    host = {"model": "opus", **dict(reversed(list(host.items())))}
    host["permissions"]["allow"].insert(0, "Bash(host-only:*)")
    settings.write_text(json.dumps(host, indent=2) + "\n")

    result = run_install(repo, home, "--profile", "vps")
    assert result.returncode == 0, result.stdout + result.stderr
    got = json.loads(settings.read_text())
    assert got["model"] == "opus"
    assert got["env"] == fresh["env"] and got["hooks"] == fresh["hooks"]
    assert got["permissions"]["allow"] == ["Bash(host-only:*)"] + fresh["permissions"]["allow"]
    assert got["permissions"]["additionalDirectories"] == ["/srv/host"]
    assert got["enabledPlugins"] == {"ponytail@host-market": True}
    assert got["extraKnownMarketplaces"] == {**fresh["extraKnownMarketplaces"], "host-market": host["extraKnownMarketplaces"]["host-market"]}
    # The printed diff carries only the repo's changes.
    changed = [l for l in result.stdout.splitlines() if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]
    assert sorted(changed) == [
        '+    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",',
        '-    "CLAUDE_CODE_ENABLE_TELEMETRY": "0",',
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


def test_a_stacked_work_profile_turns_telemetry_off_over_mac(tmp_path):
    repo, home = make_checkout(tmp_path)
    codex = home / ".codex/config.toml"
    codex.parent.mkdir()
    codex.write_text('model = "x"\n')
    assert run_install(repo, home, "--profile", "mac").returncode == 0
    assert "[otel]" in codex.read_text()

    result = run_install(repo, home, "--profile", "mac,work")
    assert result.returncode == 0, result.stdout + result.stderr
    got = json.loads((home / ".claude/settings.json").read_text())
    mac = json.loads((repo / "home/.claude/settings.mac.json").read_text())
    assert got["env"]["CLAUDE_CODE_ENABLE_TELEMETRY"] == "0"
    assert got["theme"] == mac["theme"]  # the mac overlay still applies
    assert "[otel]" not in codex.read_text()
    assert (home / ".dotagents-profile").read_text() == "mac,work\n"
