#!/usr/bin/env python3
"""Run the tests a change touches (`mise run test:affected`); `--list` prints them and runs nothing.

The changed files come from `git diff` against GATE_BASE (else origin/main), read from the checkout alone, so a
fresh clone and CI need no saved state. A changed test file runs. Any other non-markdown file runs the test files
that name its file name. A change to the test setup (mise.toml, pytest.ini, conftest.py), or a base git cannot
diff, runs everything. A change that selects nothing exits 0: the nightly runs the full suite.
"""

import os
import subprocess
import sys
from pathlib import Path

EVERYTHING = {"mise.toml", "pytest.ini", "conftest.py"}


def changed(base):
    done = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", f"{base}...HEAD"], capture_output=True, text=True
    )
    return done.stdout.split() if done.returncode == 0 else None


def targets(files, tests):
    if files is None or any(Path(f).name in EVERYTHING for f in files):
        return tests
    picked = set()
    for f in files:
        p = Path(f)
        if p.parent.as_posix() == "tests" and p.name.startswith("test_") and p.suffix == ".py":
            if p.exists():
                picked.add(f)
        elif p.suffix != ".md":
            picked.update(t for t in tests if p.name in Path(t).read_text(errors="ignore"))
    return sorted(picked)


if __name__ == "__main__":
    tests = sorted(str(p) for p in Path("tests").glob("test_*.py"))
    picked = targets(changed(os.environ.get("GATE_BASE") or "origin/main"), tests)
    print("\n".join(picked) if picked else "affected tests: none", file=sys.stderr if not picked else sys.stdout)
    if "--list" in sys.argv or not picked:
        sys.exit(0)
    sys.exit(subprocess.run(["pytest", "-q", *picked]).returncode)
