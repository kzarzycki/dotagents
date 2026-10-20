import json
import os
import shutil
import socket
import subprocess
import tomllib

import pytest

from test_install_subsets import make_checkout, run_install


EP = "http://cc-experiments.taile39822.ts.net:4318"
EXISTING = '[projects."/x"]\ntrust_level = "trusted"\n\n[mcp_servers.y]\ncommand = "y"\n'


def test_otel_settings_and_codex_block(tmp_path):
    repo, home = make_checkout(tmp_path)
    codex = home / ".codex/config.toml"
    codex.parent.mkdir()
    codex.write_text(EXISTING)
    settings = home / ".claude/settings.json"

    result = run_install(repo, home, "--profile", "vps")
    assert result.returncode == 0, result.stdout + result.stderr
    env = json.loads(settings.read_text())["env"]
    # Codex reports gethostname(); Claude's host.name must match it.
    assert env["OTEL_RESOURCE_ATTRIBUTES"] == f"service.namespace=agents,host.name={socket.gethostname()}"
    config = tomllib.loads(codex.read_text())
    assert list(config["otel"])[0] == "environment"
    assert config["otel"] == {
        "environment": socket.gethostname(),
        "log_user_prompt": False,
        "exporter": {"otlp-http": {"endpoint": f"{EP}/v1/logs", "protocol": "binary"}},
        "metrics_exporter": {"otlp-http": {"endpoint": f"{EP}/v1/metrics", "protocol": "binary"}},
        "trace_exporter": "none",
    }
    assert config["projects"]["/x"] == {"trust_level": "trusted"}
    assert config["mcp_servers"]["y"] == {"command": "y"}

    before = settings.read_bytes(), codex.read_bytes()
    assert run_install(repo, home, "--profile", "vps").returncode == 0
    assert (settings.read_bytes(), codex.read_bytes()) == before

    assert run_install(repo, home, "--profile", "remote").returncode == 0
    assert codex.read_text() == EXISTING
    assert (home / ".codex/config.toml.dotagents-bak").read_bytes() == before[1]

    for header in ("[otel]", '["otel"]', "[ 'otel' ]", "[otel.exporter]"):
        user_otel = EXISTING + f'\n{header}\nexporter = "none"\n'
        codex.write_text(user_otel)
        result = run_install(repo, home, "--profile", "vps")
        assert result.returncode == 0
        assert "WARNING" in result.stderr and "[otel]" in result.stderr, header
        assert codex.read_text() == user_otel
    for user_otel in ('otel.exporter = "none"\n' + EXISTING, '"otel" = {}\n' + EXISTING):
        codex.write_text(user_otel)
        assert "WARNING" in run_install(repo, home, "--profile", "vps").stderr
        assert codex.read_text() == user_otel


def owned_block(home):
    text = (home / ".codex/config.toml").read_text()
    return text[text.index("[otel]"):]


def test_codex_rewrite_inside_block_keeps_user_tables(tmp_path):
    repo, home = make_checkout(tmp_path)
    codex = home / ".codex/config.toml"
    codex.parent.mkdir()
    codex.write_text(EXISTING)
    assert run_install(repo, home, "--profile", "vps").returncode == 0
    block = owned_block(home)

    # The shape `codex mcp add` 0.163 leaves: a new table right after the
    # last [otel] key, ahead of anything that followed it.
    last = 'trace_exporter = "none"\n'
    codex.write_text(codex.read_text().replace(last, last + '\n[mcp_servers.x]\ncommand = "/bin/echo"\n'))
    assert run_install(repo, home, "--profile", "vps").returncode == 0
    assert tomllib.loads(codex.read_text())["mcp_servers"]["x"] == {"command": "/bin/echo"}
    assert owned_block(home) == block

    # A key appended to the owned run would join [mcp_servers.y] once the
    # header goes: leave the file alone.
    codex.write_text(EXISTING + "\n" + block + "foo = 1\n")
    edited = codex.read_bytes()
    result = run_install(repo, home, "--profile", "remote")
    assert result.returncode == 0
    assert "WARNING" in result.stderr
    assert codex.read_bytes() == edited


@pytest.mark.parametrize("profile", ["vps", "remote"])
@pytest.mark.parametrize("old, new", [
    ("log_user_prompt", "\nlog_user_prompt"),
    ("log_user_prompt", "# why\nlog_user_prompt"),
    ('trace_exporter = "none"\n', 'trace_exporter = "none"\n\nfoo = 1\n'),
])
def test_codex_key_past_blank_or_comment_leaves_file(tmp_path, profile, old, new):
    # Only a header or EOF ends [otel]; a key after a blank or comment would
    # join [mcp_servers.y] once the header goes.
    repo, home = make_checkout(tmp_path)
    codex = home / ".codex/config.toml"
    codex.parent.mkdir()
    codex.write_text(EXISTING)
    assert run_install(repo, home, "--profile", "vps").returncode == 0
    codex.write_text(codex.read_text().replace(old, new, 1))
    edited = codex.read_bytes()
    result = run_install(repo, home, "--profile", profile)
    assert result.returncode == 0
    assert "WARNING" in result.stderr
    assert codex.read_bytes() == edited


def test_codex_comment_before_next_table_is_kept(tmp_path):
    repo, home = make_checkout(tmp_path)
    codex = home / ".codex/config.toml"
    codex.parent.mkdir()
    codex.write_text(EXISTING)
    assert run_install(repo, home, "--profile", "vps").returncode == 0
    tail = '\n# mine\n[mcp_servers.x]\ncommand = "x"\n'
    codex.write_text(codex.read_text() + tail)
    assert run_install(repo, home, "--profile", "remote").returncode == 0
    assert codex.read_text() == EXISTING + tail


@pytest.mark.skipif(not shutil.which("codex"), reason="codex CLI not on PATH")
def test_real_codex_mcp_add_round_trip(tmp_path):
    repo, home = make_checkout(tmp_path)
    (home / ".codex").mkdir()
    codex = home / ".codex/config.toml"
    assert run_install(repo, home, "--profile", "vps").returncode == 0
    add = subprocess.run(
        ["codex", "mcp", "add", "x", "--", "/bin/echo"],
        env={**os.environ, "HOME": str(home), "CODEX_HOME": str(home / ".codex")},
        capture_output=True, text=True, timeout=60,
    )
    assert add.returncode == 0, add.stdout + add.stderr
    for profile in ("vps", "remote"):
        assert run_install(repo, home, "--profile", profile).returncode == 0
        config = tomllib.loads(codex.read_text())
        assert config["mcp_servers"]["x"]["command"] == "/bin/echo"
        assert ("otel" in config) == (profile == "vps")
    assert codex.read_text() == '[mcp_servers.x]\ncommand = "/bin/echo"\n'


def test_codex_block_follows_codex_selection(tmp_path):
    repo, home = make_checkout(tmp_path)
    (home / ".codex").mkdir()
    codex = home / ".codex/config.toml"

    result = run_install(repo, home, "--only", "claude", "--profile", "vps")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (home / ".claude/settings.json").exists()
    assert list((home / ".codex").iterdir()) == []

    (home / ".claude/settings.json").unlink()
    result = run_install(repo, home, "--only", "codex", "--profile", "vps")
    assert result.returncode == 0, result.stdout + result.stderr
    assert tomllib.loads(codex.read_text())["otel"]["trace_exporter"] == "none"
    assert not (home / ".claude/settings.json").exists()
