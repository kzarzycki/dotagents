import json

from test_install_subsets import make_checkout, run_install


def test_install_sets_agy_model_and_keeps_its_runtime_keys(tmp_path):
    repo, home = make_checkout(tmp_path)
    settings = home / ".gemini/antigravity-cli/settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"model": "Gemini 3.8 Flash (Medium)", "trustedWorkspaces": ["/w"]}))
    shared = json.loads((repo / "home/.gemini/antigravity-cli/settings.shared.json").read_text())

    result = run_install(repo, home, "--only", "gemini")
    assert result.returncode == 0, result.stdout + result.stderr
    got = json.loads(settings.read_text())
    assert got == {"model": shared["model"], "trustedWorkspaces": ["/w"]}
    assert not settings.is_symlink() and settings.stat().st_mode & 0o777 == 0o600
    assert not (home / ".gemini/antigravity-cli/settings.shared.json").exists()

    before = settings.read_bytes()
    result = run_install(repo, home, "--only", "gemini")
    assert result.returncode == 0 and "UPDATED" not in result.stdout
    assert settings.read_bytes() == before


def test_install_writes_no_agy_settings_before_agy_has(tmp_path):
    repo, home = make_checkout(tmp_path)
    assert run_install(repo, home, "--only", "gemini").returncode == 0
    assert not (home / ".gemini/antigravity-cli/settings.json").exists()
