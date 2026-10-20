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
