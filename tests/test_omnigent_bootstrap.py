"""The omnigent bootstrap installs no updater and no signers file (#157)."""

import os
import shutil
import subprocess

from test_install_subsets import ROOT

PATCH = ROOT / "patches/omnigent"
# The old install, as it was before #157: put back, the bootstrap check must fail.
OLD_INSTALL = """\
mkdir -p "$HOME/.local/bin"
install -m 0755 "$SCRIPT_DIR/update.sh" "$HOME/.local/bin/omnigent-update"
SIGNERS="$HOME/.config/omnigent/allowed_signers"
if [ ! -f "$SIGNERS" ]; then
  mkdir -p "$(dirname "$SIGNERS")"
  install -m 0644 "$SCRIPT_DIR/allowed_signers" "$SIGNERS"
fi
"""


def bootstrap_installs(tmp_path, script):
    """Run `script` in a scratch HOME with stubbed tools; return what it left there."""
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("uv", "omnigent"):
        (bin_dir / name).write_text("#!/bin/sh\nexit 0\n")
    # Stands in for the login shell the bootstrap asks for its PATH.
    (bin_dir / "login-shell").write_text('#!/bin/sh\necho "__PATH__=$PATH"\n')
    for f in bin_dir.iterdir():
        f.chmod(0o755)
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "SHELL": str(bin_dir / "login-shell"),
        "XDG_CONFIG_HOME": str(home / ".config"),
    }
    env.pop("CLAUDE_CODE_REMOTE", None)
    run = subprocess.run(["/bin/bash", str(script)], env=env, capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    return sorted(str(p.relative_to(home)) for p in home.rglob("*") if p.name in ("omnigent-update", "allowed_signers"))


def test_bootstrap_installs_no_updater_and_no_signers(tmp_path):
    assert bootstrap_installs(tmp_path, PATCH / "bootstrap.sh") == []


def test_check_fails_when_the_old_install_is_back(tmp_path):
    patched = tmp_path / "patch"
    shutil.copytree(PATCH, patched)
    (patched / "update.sh").write_text("#!/bin/sh\n")
    (patched / "allowed_signers").write_text("")
    script = patched / "bootstrap.sh"
    text = script.read_text()
    anchor = "# --- (4) Host service ---"
    assert anchor in text
    script.write_text(text.replace(anchor, OLD_INSTALL + anchor))
    assert bootstrap_installs(tmp_path, script) == [".config/omnigent/allowed_signers", ".local/bin/omnigent-update"]


def test_only_roots_deploy_script_still_names_allowed_signers():
    # omnigent-deploy is root's, changed by its owner; nothing else may install or read the file.
    naming = {str(p.relative_to(PATCH)) for p in PATCH.rglob("*") if p.is_file() and "allowed_signers" in p.read_text()}
    assert naming <= {"server/omnigent-deploy"}
    assert not (PATCH / "update.sh").exists()
    assert not (PATCH / "allowed_signers").exists()


def test_bootstrap_stays_executable():
    # The documented entry point is run directly, so it needs its executable bit.
    assert os.access(PATCH / "bootstrap.sh", os.X_OK)
