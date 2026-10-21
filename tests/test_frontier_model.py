import json

from test_install_subsets import make_checkout, run_install


def test_frontier_default_model_fails_install_and_is_kept(tmp_path):
    repo, home = make_checkout(tmp_path)
    codex = home / ".codex/config.toml"
    codex.parent.mkdir()
    codex.write_text(
        'model = "gpt-6-Astra"\n\n[profiles.deep] # default for gpt-6.\nmodel = "gpt-6-astra"  # x\n\n'
        '[profiles."a.b"]\nmodel = \'gpt-6-astra\'\n\n'
        '[profiles]\nwide.model = "gpt-6-astra"\n\n[profiles.fast]\nmodel = "gpt-6"# was gpt-6-astra\n\n[model_providers.astra]\nname = "astra"\n'
    )
    # Omnigent copies config.toml into a session's home only when missing,
    # so an old session keeps a default fixed since in the shared file.
    stale, fixed = (home / f".omnigent/codex-native/{s}/codex-home/config.toml" for s in "ab")
    for f, m in ((stale, "gpt-6-astra"), (fixed, "gpt-6")):
        f.parent.mkdir(parents=True)
        f.write_text(f'model = "{m}"\n\n[tui.model_availability_nux]\ngpt-6-astra = 4\n')
    settings = home / ".claude/settings.json"
    settings.parent.mkdir()
    settings.write_text('{"model": "claude-fable-5-1"}')

    result = run_install(repo, home, "--profile", "vps")
    assert result.returncode != 0, result.stdout + result.stderr
    lines = [l for l in result.stderr.splitlines() if "frontier" in l]
    assert len(lines) == 6, result.stderr
    assert f'{codex}: model = "gpt-6-Astra"' in lines[0]
    assert f'{codex}: [profiles.deep] model = "gpt-6-astra" is' in lines[1]
    assert f'{codex}: [profiles."a.b"] model = \'gpt-6-astra\' is' in lines[2]
    assert f'{codex}: [profiles] wide.model = "gpt-6-astra" is' in lines[3]
    assert f'{stale}: model = "gpt-6-astra"' in lines[4]
    assert f'{settings}: model = "claude-fable-5-1"' in lines[5]
    assert "gpt-6-astra" in codex.read_text()
    assert json.loads(settings.read_text())["model"] == "claude-fable-5-1"

    codex.write_text('model = "gpt-6"\n')
    stale.write_text('model = "gpt-6"\n')
    settings.write_text('{"model": "opus"}')
    result = run_install(repo, home, "--profile", "vps")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "frontier" not in result.stderr
