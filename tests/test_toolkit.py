import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "home", ".claude", "hooks"))

import toolkit  # noqa: E402


def test_parse_toolkit_names_single():
    assert toolkit.parse_toolkit_names("agents\n") == ["agents"]


def test_parse_toolkit_names_multi_whitespace_separated():
    assert toolkit.parse_toolkit_names("agents playwright\n") == ["agents", "playwright"]


def test_parse_toolkit_names_ignores_comments_and_blank_lines():
    content = "# comment\n\nagents  playwright  # trailing comment\n\n"
    assert toolkit.parse_toolkit_names(content) == ["agents", "playwright"]


def test_merge_toolkit_json_single_unchanged():
    t = {"plugins": ["a"], "mcp": ["m1"], "skills": ["s1"], "preloadSkills": ["p1"]}
    assert toolkit.merge_toolkit_json([t]) == t


def test_merge_toolkit_json_list_union_preserves_order_no_dupes():
    base = {"plugins": ["a", "b"], "mcp": [], "skills": [], "preloadSkills": []}
    overlay = {"plugins": ["b", "c"], "mcp": [], "skills": [], "preloadSkills": []}
    merged = toolkit.merge_toolkit_json([base, overlay])
    assert merged["plugins"] == ["a", "b", "c"]


def test_merge_toolkit_json_plugins_null_plus_list():
    base = {"plugins": None, "mcp": [], "skills": [], "preloadSkills": []}
    overlay = {"plugins": ["x"], "mcp": [], "skills": [], "preloadSkills": []}
    merged = toolkit.merge_toolkit_json([base, overlay])
    assert merged["plugins"] == ["x"]


def test_merge_toolkit_json_all_null_stays_null():
    base = {"plugins": None, "mcp": [], "skills": [], "preloadSkills": []}
    overlay = {"plugins": None, "mcp": [], "skills": [], "preloadSkills": []}
    merged = toolkit.merge_toolkit_json([base, overlay])
    assert merged["plugins"] is None


def test_merge_toolkit_json_scalar_later_wins():
    base = {"plugins": [], "mcp": [], "skills": [], "preloadSkills": [], "claudeInChrome": False}
    overlay = {"plugins": [], "mcp": [], "skills": [], "preloadSkills": [], "claudeInChrome": True}
    merged = toolkit.merge_toolkit_json([base, overlay])
    assert merged["claudeInChrome"] is True


def test_merge_toolkit_json_scalar_kept_if_only_earlier_defines_it():
    base = {"plugins": [], "mcp": [], "skills": [], "preloadSkills": [], "claudeInChrome": True}
    overlay = {"plugins": [], "mcp": [], "skills": [], "preloadSkills": []}
    merged = toolkit.merge_toolkit_json([base, overlay])
    assert merged["claudeInChrome"] is True


def test_parent_pointer_materializes_at_session_git_root(tmp_path):
    """Pointer in a group dir; outputs land at the child repo's root, not the group."""
    import json as _json
    import subprocess

    tk = tmp_path / "toolkits" / "mini"
    tk.mkdir(parents=True)
    (tk / "toolkit.json").write_text('{"plugins": [], "mcp": [], "skills": [], "preloadSkills": []}')

    group = tmp_path / "group"
    repo = group / "child"
    deep = repo / "sub"
    deep.mkdir(parents=True)
    (group / ".agents-toolkit").write_text("mini\n")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)

    hook = os.path.join(os.path.dirname(__file__), "..", "home", ".claude", "hooks", "toolkit.py")
    env = dict(os.environ, AGENTS_TOOLKITS_DIR=str(tmp_path / "toolkits"))
    out = subprocess.run(
        [sys.executable, hook], input=_json.dumps({"cwd": str(deep)}),
        capture_output=True, text=True, env=env, check=True,
    )
    assert "materialized" in _json.loads(out.stdout)["systemMessage"]
    assert (repo / ".claude" / ".toolkit-stamp").exists()
    assert not (group / ".claude").exists()
