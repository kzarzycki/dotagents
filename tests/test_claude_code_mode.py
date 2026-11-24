import json
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "home/.local/bin/claude-code-mode"
HIDDEN = ["Bash", "Read", "Edit", "Write", "Glob", "Grep", "NotebookEdit", "WebFetch", "WebSearch"]
OMNIGENT = [f"mcp__omnigent__sys_os_{t}" for t in ("shell", "read", "write", "edit")]
GUIDE = "Work through repl.\nIts scripts: call tools as JavaScript.\n"


def run(tmp_path, *args, installed=True, guide_exit=0, guide=GUIDE, with_plugin_files=True, **extra_env):
    """claude-code-mode with fake bun and omnigent: bun prints the plugin folder (-e) or the guide, omnigent records
    its arguments and, for `agent add`, unpacks the archive it was handed."""
    plugin = tmp_path / "plugin"
    plugin.mkdir(exist_ok=True)
    (plugin / "guide.ts").write_text("")
    if with_plugin_files:
        for name in (".claude-plugin/plugin.json", "hooks/hooks.json", "hooks/register.ts", "kernel/kernel.ts"):
            (plugin / name).parent.mkdir(exist_ok=True)
            (plugin / name).write_text(name)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "bun").write_text(
        f'#!/bin/sh\ncase "$1" in -e) echo "{plugin if installed else ""}" ;; *) printf %s "$GUIDE"; exit {guide_exit} ;; esac\n'
    )
    (bin_dir / "omnigent").write_text(
        '#!/bin/sh\nprintf "%s\\0" "$@" > "$OUT/args"\n[ "$1 $2" = "agent add" ] && tar -xzf "$3" -C "$OUT"\nexit 0\n'
    )
    for f in ("bun", "omnigent"):
        (bin_dir / f).chmod(0o755)
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    env = {
        "HOME": str(tmp_path),
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "GUIDE": guide,
        "OUT": str(out),
        **extra_env,
    }
    r = subprocess.run(["sh", str(SCRIPT), *args], capture_output=True, text=True, timeout=10, env=env)
    argv = (out / "args").read_text().split("\0")[:-1] if (out / "args").exists() else None
    return r, argv, out


def test_without_the_plugin_names_the_install(tmp_path):
    r, argv, _ = run(tmp_path, installed=False)
    assert r.returncode == 1
    assert "claude plugin install code-mode@claude-mods" in r.stderr
    assert argv is None


def test_without_bun_says_so(tmp_path):
    run(tmp_path)  # builds the fakes
    (tmp_path / "bin/bun").unlink()
    r = subprocess.run(
        ["/bin/sh", str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=10,
        env={"HOME": str(tmp_path), "PATH": f"{tmp_path / 'bin'}:/usr/bin:/bin"},
    )
    assert r.returncode == 1
    assert "needs bun" in r.stderr


def test_install_agent_hands_omnigent_a_claude_native_agent(tmp_path):
    r, argv, out = run(tmp_path, "--install-agent")
    assert r.returncode == 0, r.stderr
    assert argv[:2] == ["agent", "add"]
    # the archive carries a copy of the installed plugin and a skills/ folder: Omnigent starts the session with
    # --plugin-dir <bundle> then, which loads the plugin's mod; a --settings-only enablement doesn't (#229)
    assert sorted(p.name for p in out.iterdir()) == [
        ".claude-plugin",
        "args",
        "config.yaml",
        "guide.ts",
        "hooks",
        "kernel",
        "skills",
    ]
    assert (out / ".claude-plugin/plugin.json").read_text() == ".claude-plugin/plugin.json"
    assert (out / "hooks/register.ts").read_text() == "hooks/register.ts"
    assert (out / "hooks/hooks.json").exists() and (out / "kernel/kernel.ts").exists()
    assert (out / "skills/code-mode/SKILL.md").read_text().startswith("---\nname: code-mode\n")
    spec = (out / "config.yaml").read_text()
    assert "\nname: code-mode\n" in spec
    assert "    harness: claude-native\n" in spec
    # a mod's tool call can't prompt, so outside bypass every Bash call that would ask is refused
    assert "    permission_mode: bypassPermissions\n" in spec
    # patterns, not plain names: a plain name becomes Omnigent's server deny policy, which refuses the mod's calls too
    assert (
        "    disallowed_tools: [" + ", ".join([f'"{t}(*)"' for t in HIDDEN] + [f'"{t}"' for t in OMNIGENT]) + "]\n"
        in spec
    )
    # code-mode comes from the bundle's copy, so the settings leave the marketplace plugin off: one `repl`
    # (a JSON flow mapping, so json reads it as YAML would)
    (line,) = [line for line in spec.splitlines() if line.startswith("    settings: ")]
    settings = json.loads(line.removeprefix("    settings: "))
    assert settings == {"env": {"CODE_MODE_GUIDE": "system"}, "enabledPlugins": {"eval-kernel@claude-mods": False}}
    assert spec.endswith("prompt: |\n" + "".join(f"  {line}\n" for line in GUIDE.splitlines()))


def test_install_agent_stops_when_the_installed_plugin_is_incomplete(tmp_path):
    r, argv, _ = run(tmp_path, "--install-agent", with_plugin_files=False)
    assert r.returncode == 1
    assert "can't carry code-mode" in r.stderr
    assert argv is None


def test_install_agent_stops_when_the_guide_fails(tmp_path):
    r, argv, _ = run(tmp_path, "--install-agent", guide_exit=42)
    assert r.returncode == 42
    assert argv is None


def test_install_agent_stops_on_an_empty_guide(tmp_path):
    r, argv, _ = run(tmp_path, "--install-agent", guide="")
    assert r.returncode == 1
    assert "printed no guide" in r.stderr
    assert argv is None


def test_session_turns_code_mode_on_for_itself_only(tmp_path):
    r, argv, _ = run(tmp_path, "--resume", "x")
    assert r.returncode == 0, r.stderr
    assert argv[0] == "claude"
    assert argv[argv.index("--disallowedTools") + 1] == ",".join(HIDDEN + OMNIGENT)
    guide = Path(argv[argv.index("--append-system-prompt-file") + 1])
    assert guide.read_text() == GUIDE
    settings = json.loads(argv[argv.index("--settings") + 1])
    assert settings["enabledPlugins"] == {"code-mode@claude-mods": True, "eval-kernel@claude-mods": False}
    assert settings["env"] == {"CODE_MODE_GUIDE": "system"}
    assert argv[-2:] == ["--resume", "x"]


def test_a_checkout_session_loads_code_mode_from_it(tmp_path):
    r, argv, _ = run(tmp_path, "--resume", "x", CODE_MODE_DIR=str(tmp_path / "plugin"))
    assert r.returncode == 0, r.stderr
    assert argv[argv.index("--disallowedTools") + 1] == ",".join(HIDDEN + OMNIGENT)
    assert argv[argv.index("--plugin-dir") + 1] == str(tmp_path / "plugin")
    settings = json.loads(argv[argv.index("--settings") + 1])
    assert settings["enabledPlugins"] == {"eval-kernel@claude-mods": False}
    assert settings["env"] == {"CODE_MODE_GUIDE": "system"}


def test_code_mode_is_off_by_default():
    shared = json.loads((SCRIPT.parent.parent.parent / ".claude/settings.shared.json").read_text())
    assert shared["enabledPlugins"]["code-mode@claude-mods"] is False
    assert shared["enabledPlugins"]["eval-kernel@claude-mods"] is False


def test_cloud_setup_turns_on_exclusive_code_mode_for_the_environment(tmp_path):
    """The lines a cloud environment's setup runs: code-mode installed and on, the built-ins denied to the model,
    whatever settings were there kept, and a failing step logged without failing the setup."""
    r = subprocess.run(["sh", str(SCRIPT), "--cloud-setup"], capture_output=True, text=True, timeout=10)
    assert r.returncode == 0, r.stderr
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for f, body in (("bun", "exit 0"), ("claude", 'echo "claude $*" >> "$HOME/calls"'), ("npm", "exit 1")):
        (bin_dir / f).write_text(f"#!/bin/sh\n{body}\n")
        (bin_dir / f).chmod(0o755)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude/settings.json").write_text('{"model": "opus", "permissions": {"deny": ["Bash", "X"]}}')
    run_it = subprocess.run(
        ["bash", "-c", r.stdout + "\necho after"],
        capture_output=True,
        text=True,
        timeout=10,
        env={"HOME": str(tmp_path), "PATH": f"{bin_dir}:/usr/bin:/bin"},
    )
    assert run_it.returncode == 0 and run_it.stdout == "after\n"  # the environment's own setup runs on
    assert (tmp_path / "calls").read_text().splitlines() == [
        "claude plugin marketplace add kzarzycki/claude-mods",
        "claude plugin install code-mode@claude-mods --scope user",
    ]
    settings = json.loads((tmp_path / ".claude/settings.json").read_text())
    assert settings["model"] == "opus"
    assert settings["enabledPlugins"] == {"code-mode@claude-mods": True, "eval-kernel@claude-mods": False}
    assert settings["permissions"]["deny"] == ["Bash", "X"] + [t for t in HIDDEN if t != "Bash"]


FAKE_ENVIRONMENTS = """
import json, os
class Refused(Exception): pass
LOG = os.environ["OUT"] + "/calls"
def _log(*a):
    open(LOG, "a").write(json.dumps(a) + "\\n")
def headers(): return {"a": 1}
def environments(auth): return json.loads(os.environ["ENVS"])
def named(envs, name): return next((e for e in envs if e["name"] == name), None)
def read(auth, env_id):
    return {"name": env_id, "config": {"init_script": "#!/bin/bash\\nset -u\\nbase setup\\n",
            "environment": {"K": "v"}, "network_config": {"allow_default_hosts": False}}}
def update(auth, env_id, current, config, masked=()): _log("update", env_id, config, list(masked))
def call(path, body, auth, masked=()):
    _log("create", path, body, list(masked))
    return {"environment_id": "env_new"}
"""


def cloud_env(tmp_path, envs, *args):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / "scripts/claude_environments.py").write_text(FAKE_ENVIRONMENTS)
    (tmp_path / "out").mkdir(exist_ok=True)
    r = subprocess.run(
        ["sh", str(SCRIPT), "--cloud-env", *args],
        capture_output=True,
        text=True,
        timeout=10,
        env={
            "PATH": "/usr/bin:/bin",
            "OMNIGENT_AGENTS_SCRIPTS": str(tmp_path / "scripts"),
            "OUT": str(tmp_path / "out"),
            "ENVS": json.dumps(envs),
        },
    )
    log = tmp_path / "out/calls"
    return r, [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def test_cloud_env_makes_the_variant_with_code_mode_first(tmp_path):
    setup = subprocess.run(["sh", str(SCRIPT), "--cloud-setup"], capture_output=True, text=True).stdout
    r, calls = cloud_env(tmp_path, [{"name": "proj", "environment_id": "env_p", "kind": "anthropic_cloud"}], "proj")
    assert r.returncode == 0, r.stderr
    assert r.stdout == "proj-code-mode env_new: made from proj\n"
    ((verb, path, body, masked),) = calls
    assert (verb, path, body["name"]) == ("create", "/v1/environment_providers/cloud/create", "proj-code-mode")
    config = body["config"]
    # shebang, code mode, then the environment's own setup, so its toolchains and gate stay as they were
    assert config["init_script"] == "#!/bin/bash\n" + setup + "set -u\nbase setup\n"
    assert config["environment"] == {"K": "v"} and config["network_config"] == {"allow_default_hosts": False}
    assert masked == ["v"]  # variable values never show in a refusal


def test_cloud_env_updates_a_variant_already_there(tmp_path):
    envs = [{"name": "proj", "environment_id": "env_p"}, {"name": "proj-code-mode", "environment_id": "env_v"}]
    r, calls = cloud_env(tmp_path, envs, "proj")
    assert r.returncode == 0, r.stderr
    assert [c[:2] for c in calls] == [["update", "env_v"]]


def test_cloud_env_refuses_an_unknown_environment(tmp_path):
    r, calls = cloud_env(tmp_path, [], "nope")
    assert r.returncode == 1
    assert "no cloud environment called nope" in r.stderr
    assert calls == []


def test_cloud_env_needs_a_name(tmp_path):
    r, calls = cloud_env(tmp_path, [])
    assert r.returncode == 2 and "usage" in r.stderr and calls == []
