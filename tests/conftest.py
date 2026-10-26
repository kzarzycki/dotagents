import os
import sys

import pytest

# The pre-push hook puts mise's shims on PATH, and a shim run under a test's fake HOME
# creates mise's data, state and cache dirs there. Install lists those dirs as Codex
# writable roots when they exist, so the tests' configs would depend on which tools ran.
# Pin mise to the real dirs, where it keeps them anyway.
_cache = "Library/Caches/mise" if sys.platform == "darwin" else ".cache/mise"
_MISE_DIRS = {
    "MISE_DATA_DIR": os.environ.get("MISE_DATA_DIR") or os.path.expanduser("~/.local/share/mise"),
    "MISE_STATE_DIR": os.environ.get("MISE_STATE_DIR") or os.path.expanduser("~/.local/state/mise"),
    "MISE_CACHE_DIR": os.environ.get("MISE_CACHE_DIR") or os.path.expanduser(f"~/{_cache}"),
}


@pytest.fixture(autouse=True)
def _mise_outside_fake_home(monkeypatch):
    for name, path in _MISE_DIRS.items():
        monkeypatch.setenv(name, path)
    # install asks uv for its cache dir; under the fake HOME that is ~/.cache/uv
    monkeypatch.delenv("UV_CACHE_DIR", raising=False)
