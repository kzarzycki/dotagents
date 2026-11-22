import json
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "home/.local/bin/claude-code-mode"
HIDDEN = ["Bash", "Read", "Edit", "Write", "Glob", "Grep", "NotebookEdit", "WebFetch", "WebSearch"]
OMNIGENT = [f"mcp__omnigent__sys_os_{t}" for t in ("shell", "read", "write", "edit")]
GUIDE = "Work through repl.\nIts scripts: call tools as JavaScript.\n"


def run(tmp_path, *args, installed=True, guide_exit=0):
    """claude-code-mode with fake bun and omnigent: bun prints the plugin folder (-e) or the guide, omnigent records
    its arguments and, for `agent add`, unpacks the archive it was handed."""
    plugin = tmp_path / "plugin"
    plugin.mkdir(exist_ok=True)
    (plugin / "guide.ts").write_text("")
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
        "GUIDE": GUIDE,
        "OUT": str(out),
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
    # the server reads only config.yaml from the upload, so the archive must hold exactly that
    assert sorted(p.name for p in out.iterdir()) == ["args", "config.yaml"]
    spec = (out / "config.yaml").read_text()
    assert "\nname: code-mode\n" in spec
    assert "    harness: claude-native\n" in spec
    # patterns, not plain names: a plain name becomes Omnigent's server deny policy, which refuses the mod's calls too
    assert (
        "    disallowed_tools: [" + ", ".join([f'"{t}(*)"' for t in HIDDEN] + [f'"{t}"' for t in OMNIGENT]) + "]\n"
        in spec
    )
    # the agent turns code-mode on for its own sessions through Omnigent's per-agent settings
    # (a JSON flow mapping, so json reads it as YAML would)
    (line,) = [line for line in spec.splitlines() if line.startswith("    settings: ")]
    settings = json.loads(line.removeprefix("    settings: "))
    assert settings == {
        "env": {"CODE_MODE_GUIDE": "system"},
        "enabledPlugins": {"code-mode@claude-mods": True, "eval-kernel@claude-mods": False},
    }
    assert spec.endswith("prompt: |\n" + "".join(f"  {line}\n" for line in GUIDE.splitlines()))


def test_install_agent_stops_when_the_guide_fails(tmp_path):
    r, argv, _ = run(tmp_path, "--install-agent", guide_exit=42)
    assert r.returncode == 42
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


def test_code_mode_is_off_by_default():
    shared = json.loads((SCRIPT.parent.parent.parent / ".claude/settings.shared.json").read_text())
    assert shared["enabledPlugins"]["code-mode@claude-mods"] is False
    assert shared["enabledPlugins"]["eval-kernel@claude-mods"] is False
