import json
import os
import shutil
import subprocess
import tempfile
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


@pytest.mark.skipif(not shutil.which("uv"), reason="needs uv")
def test_uv_s_own_cache_dir_is_a_root_when_it_is_elsewhere(tmp_path, monkeypatch):
    cache = tmp_path.resolve() / "shared-uv-cache"
    cache.mkdir()
    monkeypatch.setenv("UV_CACHE_DIR", str(cache))
    _, home, codex, _ = install(tmp_path)
    assert roots(codex) == [str(home / root) for root in ROOTS] + [str(cache)]


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
    assert f"{codex} sets its own writable_roots; dotagents sandbox roots not managed" in result.stderr


ALLOWED = [
    "ps -axo pid,command", "pgrep -f pytest",
    "mise run check", "mise run check:all", "mise run test",
    "uv run pytest -q", ".venv/bin/pytest -q", ".venv/bin/python -m pytest -q",
]
ASKED = [
    "psql -c x", "sh -c ps", "pkill -f pytest", "mise run deploy", "mise install",
    "mise run check ::: deploy", "mise run test ::: deploy",
    "agent-browser --config ~/.agent-browser/headless.json open http://127.0.0.1:8000",
    "agent-browser --config ~/.agent-browser/headless.json connect 9222",
    "uv run python x.py", ".venv/bin/python x.py",
]


@pytest.mark.skipif(not shutil.which("codex"), reason="needs the codex CLI")
@pytest.mark.parametrize("command", ALLOWED + ASKED)
def test_the_rules_allow_the_verifier_s_routine_commands_and_nothing_else(command):
    rules = Path(__file__).parent.parent / "home/.codex/rules/sandbox-reads.rules"
    out = subprocess.run(
        ["codex", "execpolicy", "check", "--rules", str(rules), "--", *command.split()],
        capture_output=True, text=True, check=True,
    ).stdout
    assert (json.loads(out).get("decision") == "allow") == (command in ALLOWED)


def test_the_rules_install_as_copies_since_codex_skips_a_linked_one(tmp_path):
    repo, home, _, _ = install(tmp_path)
    rules = home / ".codex/rules"
    names = sorted(p.name for p in (repo / "home/.codex/rules").iterdir())
    for name in names:
        assert not (rules / name).is_symlink()
        assert (rules / name).read_bytes() == (repo / "home/.codex/rules" / name).read_bytes()
    # an older install's link is replaced, and a repo change reaches the copy
    (rules / names[0]).unlink()
    (rules / names[0]).symlink_to(repo / "home/.codex/rules" / names[0])
    (repo / "home/.codex/rules" / names[1]).write_text("# changed\n")
    assert run_install(repo, home).returncode == 0
    assert not (rules / names[0]).is_symlink()
    assert (rules / names[1]).read_text() == "# changed\n"


def test_a_rules_file_dotagents_did_not_write_is_left_alone(tmp_path):
    repo, home = make_checkout(tmp_path)
    mine = home / ".codex/rules/sandbox-reads.rules"
    mine.parent.mkdir(parents=True)
    mine.write_text('prefix_rule(pattern = ["mine"], decision = "allow")\n')
    result = run_install(repo, home)
    assert result.returncode == 1, result.stdout + result.stderr  # a conflict fails install, as for any real file
    assert mine.read_text() == 'prefix_rule(pattern = ["mine"], decision = "allow")\n'
    assert f"CONFLICT: {mine} exists and is not a dotagents copy" in result.stdout
    assert not (home / ".codex/rules/omnigent-only.rules").is_symlink()


def sandbox_failure():
    """Why `codex sandbox` can't start on this host, or None. A kernel that bars unprivileged user namespaces
    (GitHub's Ubuntu runners) stops its bwrap before the command runs. No user config, so one Codex rejects can't
    turn the round trip below into a skip."""
    if not shutil.which("codex") or "CODEX_SANDBOX" in os.environ:
        return None
    with tempfile.TemporaryDirectory() as ws:
        probe = subprocess.run(["codex", "sandbox", "-c", 'sandbox_mode="workspace-write"', "--", "true"],
                               cwd=ws, env={"PATH": os.environ["PATH"], "HOME": ws, "CODEX_HOME": ws},
                               capture_output=True, text=True, timeout=60)
    if probe.returncode:
        return f"codex sandbox can't start here (exit {probe.returncode}): {(probe.stderr.strip().splitlines() or [""])[0]}"


SANDBOX_FAILURE = sandbox_failure()


@pytest.mark.skipif(not shutil.which("codex"), reason="needs the codex CLI")
# `codex sandbox` can't start inside Codex's own sandbox (exit 71)
@pytest.mark.skipif("CODEX_SANDBOX" in os.environ, reason="runs inside a Codex sandbox")
@pytest.mark.skipif(SANDBOX_FAILURE is not None, reason=str(SANDBOX_FAILURE))
def test_codex_s_sandbox_lets_a_gate_write_an_installed_root_and_not_without_it(tmp_path):
    """The round trip: Codex's own sandbox reads the installed config. `codex sandbox` takes the
    mode only from -c, and the temp dirs it allows by default are excluded, since tmp_path is one."""
    _, home, codex, _ = install(tmp_path.resolve())
    workspace = tmp_path.resolve() / "ws"
    workspace.mkdir()

    def touch(name, *config):
        overrides = ['sandbox_mode="workspace-write"', "sandbox_workspace_write.exclude_tmpdir_env_var=true",
                     "sandbox_workspace_write.exclude_slash_tmp=true", *config]
        return subprocess.run(
            ["codex", "sandbox", *(arg for c in overrides for arg in ("-c", c)), "--", "touch", str(home / ".apm" / name)],
            cwd=workspace, env={"PATH": os.environ["PATH"], "HOME": str(home), "CODEX_HOME": str(codex.parent)},
            capture_output=True, text=True, timeout=60,
        ).returncode

    assert touch("x.lock") == 0
    assert touch("y.lock", "sandbox_workspace_write.writable_roots=[]") != 0
    assert sorted(p.name for p in (home / ".apm").iterdir()) == ["x.lock"]
