import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "affected_tests", Path(__file__).parent.parent / "lib" / "affected_tests.py"
)
sel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sel)

TESTS = ["tests/test_a.py", "tests/test_b.py"]


def test_changed_test_file_runs_alone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("tests").mkdir()
    Path("tests/test_a.py").write_text("")
    assert sel.targets(["tests/test_a.py"], TESTS) == ["tests/test_a.py"]


def test_other_file_runs_tests_that_name_it(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("tests").mkdir()
    Path("tests/test_a.py").write_text("x = 'precommit-guard.sh'")
    Path("tests/test_b.py").write_text("")
    assert sel.targets(["lib/precommit-guard.sh"], TESTS) == ["tests/test_a.py"]


def test_setup_change_or_no_base_runs_everything():
    assert sel.targets(["mise.toml"], TESTS) == TESTS
    assert sel.targets(None, TESTS) == TESTS


def test_docs_only_selects_nothing():
    assert sel.targets(["README.md", "docs/x.md"], TESTS) == []


def test_unknown_base_fails_the_diff():
    assert sel.changed("no-such-ref") is None
