import os
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "lib" / "affected_tests.py"


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def repo(tmp_path):
    """A clone-like repo on `base`, with a passing and a failing-able test, and the script under test."""
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@t")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_ok.py").write_text("def test_ok():\n    pass\n")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin/tool").write_text("1\n")
    (tmp_path / "README.md").write_text("a\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    git(tmp_path, "tag", "base")
    shutil.copy(SCRIPT, tmp_path / "affected_tests.py")
    return tmp_path


def change(repo_dir, path, text):
    p = repo_dir / path
    p.write_text(text)
    git(repo_dir, "add", "-A", "-f", path)
    git(repo_dir, "commit", "-qm", "change")


def run(repo_dir, *args, base="base"):
    env = {**os.environ, "GATE_BASE": base}
    return subprocess.run(
        [sys.executable, "affected_tests.py", *args], cwd=repo_dir, env=env, capture_output=True, text=True
    )


def test_changed_test_file_runs_alone_even_with_a_space_in_its_name(tmp_path):
    r = repo(tmp_path)
    change(r, "tests/test_spaced name.py", "def test_x():\n    pass\n")
    assert run(r, "--list").stdout.split("\n")[:-1] == ["tests/test_spaced name.py"]


def test_selected_test_failure_is_the_exit_code(tmp_path):
    r = repo(tmp_path)
    change(r, "tests/test_bad.py", "def test_bad():\n    assert False\n")
    assert run(r).returncode == 1


def test_docs_only_selects_nothing_and_exits_0(tmp_path):
    r = repo(tmp_path)
    change(r, "README.md", "b\n")
    done = run(r)
    assert done.returncode == 0 and "none" in done.stderr


def test_any_other_file_or_a_bad_base_runs_everything(tmp_path):
    r = repo(tmp_path)
    change(r, "bin/tool", "2\n")
    assert run(r, "--list").stdout.split() == ["tests/test_ok.py"]
    assert run(r, "--list", base="no-such-ref").stdout.split() == ["tests/test_ok.py"]


def test_default_base_is_origin_main(tmp_path):
    r = repo(tmp_path)
    git(r, "update-ref", "refs/remotes/origin/main", "HEAD")
    change(r, "README.md", "b\n")
    env = {k: v for k, v in os.environ.items() if k != "GATE_BASE"}
    done = subprocess.run(
        [sys.executable, "affected_tests.py", "--list"], cwd=r, env=env, capture_output=True, text=True
    )
    assert done.returncode == 0 and "none" in done.stderr


def test_shipped_markdown_runs_everything(tmp_path):
    r = repo(tmp_path)
    (r / "home").mkdir()
    change(r, "home/x.md", "x\n")
    assert run(r, "--list").stdout.split() == ["tests/test_ok.py"]


def test_a_deleted_test_selects_nothing_and_exits_0(tmp_path):
    r = repo(tmp_path)
    git(r, "rm", "-q", "tests/test_ok.py")
    git(r, "commit", "-qm", "rm")
    done = run(r)
    assert done.returncode == 0 and "none" in done.stderr


def test_a_test_named_file_outside_tests_runs_everything(tmp_path):
    r = repo(tmp_path)
    (r / "lib").mkdir()
    change(r, "lib/test_x.py", "x = 1\n")
    assert run(r, "--list").stdout.split() == ["tests/test_ok.py"]


def test_a_doc_a_test_names_selects_that_test(tmp_path):
    r = repo(tmp_path)
    (r / "tests/test_readme.py").write_text("def test_r():\n    assert 'README.md'\n")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "readme test")
    git(r, "tag", "-f", "base")
    change(r, "README.md", "b\n")
    assert run(r, "--list").stdout.split() == ["tests/test_readme.py"]
