#!/usr/bin/env python3
"""Swift shim: refuse a Swift call nested below the command line on a host that forbids it.

The host-command hook (../omnigent-only.py) sees only the command an agent types. A test or
script that shells out to `swift build` bypasses it, so on a host whose ~/.agents/host-commands
lists a `swift` rule, env.sh puts this directory first on PATH. `swift`, `swift-build` and
`swift-test` here run shim.py, which

- passes the call to the real binary (found further down PATH, this directory skipped) when no
  rule matches it, so `swift --version` still works;
- otherwise refuses, unless SWIFT_ON_HOST_ALLOWED=1 is set and the 1-minute load is under 10 (the
  one allowed case, an Android APK build for an emulator proof, is fine only on an idle host).

The rule parsing is the hook's own. The hosts where Swift runs are read from ~/.agents/swift-hosts
(one per line, optional), so the repo names none. The load is the system's own; tests inject it
with a sitecustomize on PYTHONPATH, never an environment variable the shim reads. Cases: tests/test_swift_shims.py.
"""

import importlib.util
import os
import sys

MAX_LOAD = 10.0
WORDS = {"swift": ["swift"], "swift-build": ["swift", "build"], "swift-test": ["swift", "test"]}


def load_hook(shim_dir):
    path = os.path.join(shim_dir, "..", "omnigent-only.py")
    spec = importlib.util.spec_from_file_location("omnigent_only", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_average():
    return os.getloadavg()[0]


def real_binary(name, shim_dir):
    skip = {os.path.realpath(shim_dir)}
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(entry or ".", name)
        if os.path.realpath(entry or ".") in skip or not os.access(candidate, os.X_OK) or os.path.isdir(candidate):
            continue
        return candidate
    return None


def swift_hosts():
    try:
        with open(os.path.expanduser("~/.agents/swift-hosts")) as f:
            lines = f.read().splitlines()
    except OSError:
        return "a claude-cloud worker or a Mac"
    return ", ".join(h for h in (line.split("#")[0].strip() for line in lines) if h) or "a claude-cloud worker or a Mac"


def main():
    shim_dir, name, args = sys.argv[1], sys.argv[2], sys.argv[3:]
    rule = load_hook(shim_dir).host_forbidden([*WORDS[name], *args])
    real = real_binary(name, shim_dir)
    if rule:
        allowed = os.environ.get("SWIFT_ON_HOST_ALLOWED") == "1"
        try:
            load = load_average()
        except (OSError, ValueError, IndexError):
            load = float("inf")
        if not (allowed and load < MAX_LOAD):
            why = (
                "SWIFT_ON_HOST_ALLOWED=1 is not set"
                if not allowed
                else f"the 1-minute load is {load:g}, not under {MAX_LOAD:g}"
            )
            print(
                f"Denied `{' '.join([name, *args])}`: this host's config forbids `{rule}` (a line in "
                f"{os.path.expanduser('~/.agents/host-commands')}), and {why}. Swift runs on: {swift_hosts()}. "
                "Only an Android APK build for an emulator proof may run here: set SWIFT_ON_HOST_ALLOWED=1 "
                "on an idle host.",
                file=sys.stderr,
            )
            sys.exit(2)
    if real is None:
        print(f"{name}: no real binary further down PATH", file=sys.stderr)
        sys.exit(127)
    os.execv(real, [real, *args])


if __name__ == "__main__":
    main()
