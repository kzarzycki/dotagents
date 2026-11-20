#!/usr/bin/env python3
"""Run the tests a change touches (`mise run test:affected`); `--list` prints them and runs nothing.

The changed files come from `git diff` against GATE_BASE (else origin/main), read from the checkout alone, so a
fresh clone and CI need no saved state. A changed test file runs alone only when every other changed file is
documentation outside `home/`. Anything else (installer, shipped config or instructions, test setup) runs the whole
suite, and so does a base git cannot diff: the installer tests read `home/`, `bin/` and `lib/` through paths no name
search sees. A docs-only change selects nothing and exits 0: the nightly runs the full suite.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# ponytail: a name search misses what the installer tests read through assembled paths, and the suite runs in about
# 80 seconds, so only a tests-only or docs-only change narrows. Upgrade path: per-test coverage data (needs saved state).


def changed(base):
    done = subprocess.run(
        ["git", "diff", "-z", "--name-only", "--no-renames", f"{base}...HEAD"], capture_output=True, text=True
    )
    return done.stdout.split("\0")[:-1] if done.returncode == 0 else None


def is_test(f):
    p = Path(f)
    return p.parent.as_posix() == "tests" and p.name.startswith("test_") and p.suffix == ".py"


def targets(files, tests):
    if files is None:
        return tests
    docs = [f for f in files if f.endswith(".md") and not f.startswith("home/")]
    if any(not is_test(f) and f not in docs for f in files):
        return tests
    return sorted(f for f in files if is_test(f) and Path(f).exists())


if __name__ == "__main__":
    tests = sorted(str(p) for p in Path("tests").glob("test_*.py"))
    picked = targets(changed(os.environ.get("GATE_BASE") or "origin/main"), tests)
    print("\n".join(picked) if picked else "affected tests: none", file=None if picked else sys.stderr)
    if "--list" in sys.argv or not picked:
        sys.exit(0)
    sys.exit(
        subprocess.run(
            [*(["pytest"] if shutil.which("pytest") else [sys.executable, "-m", "pytest"]), "-q", *picked]
        ).returncode
    )
