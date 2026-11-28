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
    assert got["autoMode"]["allow"] == [
        fresh["autoMode"]["allow"][0],
        "A host-only auto-mode rule.",
        *fresh["autoMode"]["allow"][1:],
    ]
    assert got["enabledPlugins"] == {**fresh["enabledPlugins"], "ponytail@host-market": True}
    assert got["extraKnownMarketplaces"] == {
        **fresh["extraKnownMarketplaces"],
        "host-market": host["extraKnownMarketplaces"]["host-market"],
    }
    # The printed diff carries only the repo's changes.
    own = result.stdout.split(f"UPDATED {settings}:", 1)[1].split("UPDATED ", 1)[0]  # not the Codex config's diff
    changed = [l for l in own.splitlines() if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]
    assert sorted(changed) == [
        '+    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",',
        '-    "CLAUDE_CODE_ENABLE_TELEMETRY": "0",',
        '-    "stale@host-market": false,',
    ], own

    before = settings.read_bytes()
    result = run_install(repo, home, "--profile", "vps")
    assert result.returncode == 0 and "UPDATED" not in result.stdout
    assert settings.read_bytes() == before


def test_the_compact_window_is_a_setting_so_a_launch_flag_can_lower_it(tmp_path):
    # Claude Code ranks CLAUDE_CODE_AUTO_COMPACT_WINDOW above --autocompact, and
    # --autocompact above autoCompactWindow, so the default lives in the setting.
    repo, home = make_checkout(tmp_path)
    settings = home / ".claude/settings.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({"env": {"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "330000"}}) + "\n")
    for profile in ("mac", "vps", "remote", "mac,work"):
        result = run_install(repo, home, "--profile", profile)
        assert result.returncode == 0, result.stdout + result.stderr
        got = json.loads(settings.read_text())
        assert got["autoCompactWindow"] == 200000 and "CLAUDE_CODE_AUTO_COMPACT_WINDOW" not in got["env"], profile


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
    assert fresh["extraKnownMarketplaces"]["claude-mods"] == {
        "source": {"source": "github", "repo": "kzarzycki/claude-mods"}
    }
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
    assert (
        json.loads(settings.read_text())["extraKnownMarketplaces"]["claude-mods"]
        == fresh["extraKnownMarketplaces"]["claude-mods"]
    )


def test_install_drops_orca_hooks_a_host_still_carries(tmp_path):
    # The repo's hooks block replaces the host's wholesale, so entries Orca wrote
    # into a host's settings disappear on the next install.
    repo, home = make_checkout(tmp_path)
    settings = home / ".claude/settings.json"
    assert run_install(repo, home, "--profile", "vps").returncode == 0
    orca = {"type": "command", "command": 'if [ -x "$HOME/.orca/agent-hooks/claude-hook.sh" ]; then /bin/sh "$HOME/.orca/agent-hooks/claude-hook.sh"; fi'}
    host = json.loads(settings.read_text())
    for event in ("PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionRequest"):
        host["hooks"].setdefault(event, []).append({"matcher": "*", "hooks": [orca]})
    settings.write_text(json.dumps(host, indent=2) + "\n")

    assert run_install(repo, home, "--profile", "vps").returncode == 0
    assert ".orca" not in settings.read_text()


SEVEN = ["Bash", "Read", "Edit", "Write", "Glob", "Grep", "NotebookEdit"]


def with_code_mode_ready(home, bun=True):
    """A user-scope plugin payload on disk and a bun for its own find-bun.sh to find, as where Code Mode can run."""
    plugin = home / ".claude/plugins/cache/claude-mods/code-mode/1"
    (plugin / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (plugin / ".claude-plugin/plugin.json").write_text("{}")
    (plugin / "hooks").mkdir(exist_ok=True)
    (plugin / "hooks/register.ts").write_text("")
    (plugin / "hooks/find-bun.sh").write_text('[ -x "$HOME/.bun/bin/bun" ] && echo "$HOME/.bun/bin/bun"\n')
    (home / ".claude/plugins/installed_plugins.json").write_text(
        json.dumps({"plugins": {"code-mode@claude-mods": [{"scope": "user", "installPath": str(plugin)}]}})
    )
    if bun:
        (home / ".bun/bin").mkdir(parents=True, exist_ok=True)
        (home / ".bun/bin/bun").write_text("#!/bin/sh\n")
        (home / ".bun/bin/bun").chmod(0o755)


def test_a_fresh_personal_install_turns_on_exclusive_code_mode(tmp_path):
    repo, home = make_checkout(tmp_path)
    with_code_mode_ready(home)
    assert run_install(repo, home, "--profile", "mac").returncode == 0
    got = json.loads((home / ".claude/settings.json").read_text())
    assert got["enabledPlugins"]["code-mode@claude-mods"] is True
    assert got["permissions"]["deny"] == SEVEN
    assert got["pluginConfigs"]["code-mode@claude-mods"]["options"]["mode"] == "exclusive"


def test_a_second_install_leaves_code_mode_on_over_a_host_that_has_it_on(tmp_path):
    repo, home = make_checkout(tmp_path)
    with_code_mode_ready(home)
    settings = home / ".claude/settings.json"
    assert run_install(repo, home, "--profile", "mac").returncode == 0
    host = json.loads(settings.read_text())
    host["enabledPlugins"]["code-mode@claude-mods"] = True
    host["permissions"]["deny"] = SEVEN
    settings.write_text(json.dumps(host, indent=2) + "\n")
    assert run_install(repo, home, "--profile", "mac").returncode == 0
    got = json.loads(settings.read_text())
    assert got["enabledPlugins"]["code-mode@claude-mods"] is True
    assert got["permissions"]["deny"] == SEVEN


def test_the_work_profile_keeps_code_mode_off_and_adds_no_deny_list(tmp_path):
    repo, home = make_checkout(tmp_path)
    with_code_mode_ready(home)
    assert run_install(repo, home, "--profile", "mac,work").returncode == 0
    got = json.loads((home / ".claude/settings.json").read_text())
    assert got["enabledPlugins"]["code-mode@claude-mods"] is False
    assert got["permissions"].get("deny", []) == []
    assert "code-mode@claude-mods" not in got.get("pluginConfigs", {})


def test_switching_a_personal_host_to_work_drops_the_code_mode_denies_and_keeps_others(tmp_path):
    repo, home = make_checkout(tmp_path)
    with_code_mode_ready(home)
    settings = home / ".claude/settings.json"
    assert run_install(repo, home, "--profile", "mac").returncode == 0
    host = json.loads(settings.read_text())
    host["permissions"]["deny"] = ["Read(./secrets/**)"] + SEVEN
    settings.write_text(json.dumps(host, indent=2) + "\n")
    assert run_install(repo, home, "--profile", "mac,work").returncode == 0
    got = json.loads(settings.read_text())
    assert got["enabledPlugins"]["code-mode@claude-mods"] is False
    assert got["permissions"]["deny"] == ["Read(./secrets/**)"]


def test_a_personal_install_sets_the_plugins_mode_to_exclusive_over_a_saved_preferred(tmp_path):
    repo, home = make_checkout(tmp_path)
    with_code_mode_ready(home)
    settings = home / ".claude/settings.json"
    assert run_install(repo, home, "--profile", "mac").returncode == 0
    got = json.loads(settings.read_text())
    got["pluginConfigs"]["code-mode@claude-mods"]["options"]["mode"] = "preferred"
    settings.write_text(json.dumps(got, indent=2) + "\n")
    assert run_install(repo, home, "--profile", "mac").returncode == 0
    assert json.loads(settings.read_text())["pluginConfigs"]["code-mode@claude-mods"]["options"]["mode"] == "exclusive"


def test_a_personal_install_without_a_usable_plugin_or_bun_adds_no_denies(tmp_path):
    repo, home = make_checkout(tmp_path)
    settings = home / ".claude/settings.json"

    def denies():
        return json.loads(settings.read_text())["permissions"].get("deny", [])

    result = run_install(repo, home, "--profile", "mac")  # nothing installed
    assert "ERROR: the code-mode plugin is not installed" in result.stderr and denies() == []

    with_code_mode_ready(home, bun=False)  # plugin there, no bun (skipped where the test host has bun on PATH)
    result = run_install(repo, home, "--profile", "mac")
    if "ERROR: bun" in result.stderr:
        assert denies() == []

    with_code_mode_ready(home)
    plugin = next((home / ".claude/plugins/cache").rglob("register.ts"))
    plugin.unlink()  # a manifest entry whose payload is gone
    result = run_install(repo, home, "--profile", "mac")
    assert "ERROR: the code-mode plugin is not installed" in result.stderr and denies() == []

    with_code_mode_ready(home)
    settings.write_text(json.dumps({"pluginConfigs": {"code-mode@claude-mods": {"options": {"bun": "no-such-bun-xyz"}}}}))
    result = run_install(repo, home, "--profile", "mac")
    assert "no-such-bun-xyz" in result.stderr and denies() == []


def test_a_host_authored_deny_survives_installs_that_never_enabled_code_mode(tmp_path):
    repo, home = make_checkout(tmp_path)
    settings = home / ".claude/settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"permissions": {"deny": ["Bash", "Read(./example/**)"]}}))
    assert run_install(repo, home, "--profile", "mac,work", "--only", "claude").returncode == 0
    assert json.loads(settings.read_text())["permissions"]["deny"] == ["Bash", "Read(./example/**)"]
    assert run_install(repo, home, "--profile", "mac", "--only", "claude").returncode == 0  # no plugin: adds none
    assert json.loads(settings.read_text())["permissions"]["deny"] == ["Bash", "Read(./example/**)"]


def test_a_codex_only_install_does_not_check_code_mode(tmp_path):
    repo, home = make_checkout(tmp_path)
    result = run_install(repo, home, "--profile", "mac", "--only", "codex")
    assert result.returncode == 0 and "code-mode" not in result.stderr
