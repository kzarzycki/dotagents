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
    host["enabledPlugins"] = {**host["enabledPlugins"], "stale@host-market": False, "ponytail@host-market": True}
    host["extraKnownMarketplaces"]["host-market"] = {"source": {"source": "github", "repo": "x/y"}}
    # Host key order differs from the repo's; it must not show up as a change.
    host = {"model": "opus", **dict(reversed(list(host.items())))}
    host["permissions"]["allow"].insert(0, "Bash(host-only:*)")
    host["autoMode"]["allow"].insert(1, "A host-only auto-mode rule.")
    settings.write_text(json.dumps(host, indent=2) + "\n")

    result = run_install(repo, home, "--profile", "vps")
    assert result.returncode == 0, result.stdout + result.stderr
    got = json.loads(settings.read_text())
    assert got["model"] == "opus"
    assert got["env"] == fresh["env"] and got["hooks"] == fresh["hooks"]
    assert got["permissions"]["allow"] == ["Bash(host-only:*)"] + fresh["permissions"]["allow"]
    assert got["permissions"]["additionalDirectories"] == ["/srv/host"]
    assert got["autoMode"]["allow"] == [fresh["autoMode"]["allow"][0], "A host-only auto-mode rule.", *fresh["autoMode"]["allow"][1:]]
    assert got["enabledPlugins"] == {**fresh["enabledPlugins"], "ponytail@host-market": True}
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


def test_the_work_overlay_writes_omnigents_telemetry_allowlist_and_mac_removes_it(tmp_path):
    repo, home = make_checkout(tmp_path)
    (home / ".omnigent").mkdir()
    allow = home / ".omnigent/telemetry-allowlist.json"

    result = run_install(repo, home, "--profile", "mac,work")
    assert result.returncode == 0, result.stdout + result.stderr
    got = json.loads(allow.read_text())
    shared = json.loads((repo / "home/.claude/settings.shared.json").read_text())
    assert got["managedBy"] == "dotagents"
    assert got["endpoint"] == shared["env"]["OTEL_EXPORTER_OTLP_ENDPOINT"]
    assert "github.com/kzarzycki/agent-skills" in got["repos"]
    assert "dotagents" not in json.loads((home / ".claude/settings.json").read_text())

    assert run_install(repo, home, "--profile", "mac").returncode == 0
    assert not allow.exists()  # a personal host: no allowlist, every project exports

    allow.write_text('{"endpoint": "http://mine", "repos": []}')  # hand-written: not ours
    result = run_install(repo, home, "--profile", "mac,work")
    assert "not managed by dotagents" in result.stderr
    assert json.loads(allow.read_text()) == {"endpoint": "http://mine", "repos": []}


def test_a_hosts_directory_marketplace_wins_and_work_pins_decision_model_to_claude(tmp_path):
    repo, home = make_checkout(tmp_path)
    settings = home / ".claude/settings.json"
    assert run_install(repo, home, "--profile", "mac,work").returncode == 0
    fresh = json.loads(settings.read_text())
    assert fresh["extraKnownMarketplaces"]["claude-mods"] == {"source": {"source": "github", "repo": "kzarzycki/claude-mods"}}
    assert fresh["pluginConfigs"] == {"decision-model@claude-mods": {"options": {"backend": "claude"}}}

    host = json.loads(settings.read_text())
    checkout = {"source": {"source": "directory", "path": "/src/claude-mods"}}
    host["extraKnownMarketplaces"]["claude-mods"] = checkout
    host["extraKnownMarketplaces"]["powerpoint-mcp"] = {"source": {"source": "github", "repo": "fork/powerpoint-mcp"}}
    host["pluginConfigs"] = {
        "auto-effort@inline": {"options": {"maxEffort": "high"}},
        "decision-model@claude-mods": {"options": {"backend": "auto", "claudeModel": "sonnet"}},
    }
    settings.write_text(json.dumps(host, indent=2) + "\n")

    result = run_install(repo, home, "--profile", "mac,work")
    assert result.returncode == 0, result.stdout + result.stderr
    got = json.loads(settings.read_text())
    assert got["extraKnownMarketplaces"]["claude-mods"] == checkout
    assert "NOTE: marketplace claude-mods keeps this host's directory source /src/claude-mods" in result.stdout
    # Only a directory source is a development override; any other host source is the repo's again.
    assert got["extraKnownMarketplaces"]["powerpoint-mcp"] == fresh["extraKnownMarketplaces"]["powerpoint-mcp"]
    assert got["pluginConfigs"] == {
        "auto-effort@inline": {"options": {"maxEffort": "high"}},
        "decision-model@claude-mods": {"options": {"backend": "claude", "claudeModel": "sonnet"}},
    }
    assert "NOTE: marketplace" in run_install(repo, home, "--profile", "mac,work", "--dry-run").stdout

    # Removing the host's entry brings the managed source back.
    del got["extraKnownMarketplaces"]["claude-mods"]
    settings.write_text(json.dumps(got, indent=2) + "\n")
    result = run_install(repo, home, "--profile", "mac,work")
    assert "NOTE: marketplace" not in result.stdout
    assert json.loads(settings.read_text())["extraKnownMarketplaces"]["claude-mods"] == fresh["extraKnownMarketplaces"]["claude-mods"]
