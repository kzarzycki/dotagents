import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from test_install_subsets import make_checkout, run_install

ROOTS = (".apm", ".cache/uv", ".local/share/mise")
MARK = "# dotagents sandbox:"


def install(tmp_path, config=None):
    repo, home = make_checkout(tmp_path)
    for root in ROOTS:
        (home / root).mkdir(parents=True)
    codex = home / ".codex/config.toml"
    codex.parent.mkdir()
    if config is not None:
        codex.write_text(config)
    result = run_install(repo, home)
    assert result.returncode == 0, result.stdout + result.stderr
    return repo, home, codex, result


def roots(codex):
    return tomllib.loads(codex.read_text())["sandbox_workspace_write"]["writable_roots"]


def test_the_host_s_gate_caches_become_writable_roots_in_the_user_s_table(tmp_path):
    user = 'model = "m"\n\n[sandbox_workspace_write]\nnetwork_access = true\n\n[mcp_servers.y]\ncommand = "y"\n'
    repo, home, codex, _ = install(tmp_path, user)
    config = tomllib.loads(codex.read_text())
    # only the roots that exist here, absolute, since Codex does not expand ~
    assert roots(codex) == [str(home / root) for root in ROOTS]
    assert config["sandbox_workspace_write"]["network_access"] is True
    assert config["mcp_servers"]["y"] == {"command": "y"}
    before = codex.read_bytes()
    assert run_install(repo, home).returncode == 0
    assert codex.read_bytes() == before  # a second install changes nothing
    (home / "Library/Caches/mise").mkdir(parents=True)
    assert run_install(repo, home).returncode == 0
    assert roots(codex)[-1] == str(home / "Library/Caches/mise")
    assert codex.read_text().count(MARK) == 1


@pytest.mark.parametrize("config", [None, "", 'model = "m"\n'])
def test_a_config_without_the_table_gets_one(tmp_path, config):
    _, home, codex, _ = install(tmp_path, config)
    assert roots(codex) == [str(home / root) for root in ROOTS]


@pytest.mark.parametrize(
    "user",
    [
        '[sandbox_workspace_write]\nwritable_roots = ["/mine"]\n',
        'sandbox_workspace_write.writable_roots = ["/mine"]\n',
    ],
)
def test_a_hand_set_writable_roots_is_the_user_s(tmp_path, user):
    _, _, codex, result = install(tmp_path, user)
    text = codex.read_text()
    assert text.startswith(user) and MARK not in text  # [otel] may follow; the roots are not ours
    assert "WARNING" in result.stderr and "writable_roots" in result.stderr


@pytest.mark.skipif(not shutil.which("codex"), reason="needs the codex CLI")
def test_the_rule_allows_ps_and_nothing_else():
    rules = Path(__file__).parent.parent / "home/.codex/rules/sandbox-reads.rules"

    def check(*command):
        out = subprocess.run(
            ["codex", "execpolicy", "check", "--rules", str(rules), "--", *command],
            capture_output=True, text=True, check=True,
        ).stdout
        return '"allow"' in out

    assert check("ps", "-axo", "pid,command")
    assert not check("psql", "-c", "select 1")
    assert not check("sh", "-c", "ps")
