#!/usr/bin/python3
"""Launch OMP unchanged; activate only a locally audited, pinned release."""

import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time

ROOT = Path.home() / ".local/lib/omp-upgrade"
STATE = Path.home() / ".local/state/omp-upgrade"
REAL = ROOT / "omp-real"
AUDIT = ROOT / "audit.py"
# Mirrors audit.ASSETS; the launcher stays standalone (no import at startup).
ASSET = {
    ("Linux", "x86_64"): "omp-linux-x64",
    ("Linux", "aarch64"): "omp-linux-arm64",
    ("Linux", "arm64"): "omp-linux-arm64",
    ("Darwin", "arm64"): "omp-darwin-arm64",
    ("Darwin", "x86_64"): "omp-darwin-x64",
}.get((platform.system(), platform.machine()))
MIN_SIZE = 1024 * 1024
MAX_SIZE = 1024 * 1024 * 1024
REPORT_LIMIT = 2 * 1024 * 1024
MANIFEST_KEYS = {"version", "commit", "sha256"}
APPROVAL_KEYS = MANIFEST_KEYS | {"size", "base_sha256", "asset_url"}
# Executable header identities for the published assets; 64-bit little-endian only.
ELF_MACHINES = {62: "omp-linux-x64", 183: "omp-linux-arm64"}
MACH_CPUS = {0x01000007: "omp-darwin-x64", 0x0100000C: "omp-darwin-arm64"}
MACH_MAGIC = b"\xcf\xfa\xed\xfe"
FAT_STRIDE = {b"\xca\xfe\xba\xbe": 20, b"\xca\xfe\xba\xbf": 32}
MAX_SLICES = 16
HEADER = 8 + MAX_SLICES * 32


class Hold(Exception):
    pass


def version(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", value
    ) or len(value) > 40:
        raise Hold("Version is not a canonical stable release")
    return tuple(map(int, value.split(".")))


def hex_value(value, length):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{%d}" % length, value)


def manifest(value):
    if not isinstance(value, dict) or set(value) != MANIFEST_KEYS:
        raise Hold("Installed/source manifest schema is invalid")
    version(value["version"])
    if not hex_value(value["commit"], 40) or not hex_value(value["sha256"], 64):
        raise Hold("Installed/source manifest identity is invalid")
    return value


def private_directory(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise Hold(f"Unsafe managed directory: {path}")
    path.chmod(0o700)


@contextlib.contextmanager
def regular_file(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise Hold(f"Unsafe managed file: {path.name}")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            yield stream, info
    finally:
        os.close(fd)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Hold(f"Duplicate metadata key: {key}")
        result[key] = value
    return result


def read_json(path):
    limit = REPORT_LIMIT if path == STATE / "report.json" else 65536
    with regular_file(path) as (stream, _):
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise Hold(f"Metadata exceeds size limit: {path.name}")
    return json.loads(data, object_pairs_hook=unique_object)


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_json(path, value):
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        sync_directory(path.parent)
    finally:
        Path(name).unlink(missing_ok=True)


def digest(path):
    result = hashlib.sha256()
    with regular_file(path) as (stream, info):
        if not MIN_SIZE <= info.st_size <= MAX_SIZE:
            raise Hold(f"Binary size is outside release bounds: {path.name}")
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


@contextlib.contextmanager
def update_lock():
    private_directory(STATE)
    fd = os.open(STATE / "update.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise Hold("Unsafe update lock")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
        else:
            try:
                yield True
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def report(**changes):
    """Call under update.lock; reporting must never break an OMP launch."""
    try:
        try:
            value = read_json(STATE / "report.json")
            if not isinstance(value, dict):
                return
        except FileNotFoundError:
            value = {}
        value.update(changes, launcher_updated_at=int(time.time()))
        if len(json.dumps(value, indent=2, ensure_ascii=True).encode("utf-8")) + 1 > REPORT_LIMIT:
            return
        write_json(STATE / "report.json", value)
    except (OSError, ValueError, Hold):
        pass


def reject(reason, release=None):
    # Consume approval first. Never touch the transaction's last-known-good file.
    try:
        (STATE / "approved.json").unlink(missing_ok=True)
        (STATE / "candidate").unlink(missing_ok=True)
        sync_directory(STATE)
    finally:
        changes = {"status": "HOLD", "summary": str(reason), "risks": [str(reason)]}
        if release is not None:
            changes["version"] = release
        report(**changes)


def validate_approval(approval, installed):
    if not isinstance(approval, dict) or set(approval) != APPROVAL_KEYS:
        raise Hold("Approval schema is invalid")
    manifest({key: approval[key] for key in MANIFEST_KEYS})
    if version(approval["version"]) <= version(installed["version"]):
        raise Hold("Approval is stale or not newer than the installed release")
    if approval["commit"] == installed["commit"] or approval["sha256"] == installed["sha256"]:
        raise Hold("Approval does not identify a new source and binary")
    if not hex_value(approval["base_sha256"], 64) or approval["base_sha256"] != installed["sha256"]:
        raise Hold("Approval was audited against a different installed baseline")
    if type(approval["size"]) is not int or not MIN_SIZE <= approval["size"] <= MAX_SIZE:
        raise Hold("Approved binary size is outside release bounds")
    if not ASSET:
        raise Hold(f"No published asset for {platform.system()}/{platform.machine()}")
    expected = f"https://github.com/can1357/oh-my-pi/releases/download/v{approval['version']}/{ASSET}"
    if approval["asset_url"] != expected:
        raise Hold(f"Approval does not name the official version-pinned {ASSET} asset")
    if digest(REAL) != installed["sha256"]:
        raise Hold("Installed binary no longer matches its accepted source manifest")


def asset_targets(head):
    """Asset names this executable header can run as; a universal Mach-O names several."""
    if head[:4] == b"\x7fELF":
        # 64-bit little-endian ELF; e_machine selects the architecture.
        machine = int.from_bytes(head[18:20], "little") if len(head) >= 20 and head[4:6] == b"\x02\x01" else None
        return {ELF_MACHINES[machine]} if machine in ELF_MACHINES else set()
    if head[:4] == MACH_MAGIC:
        cpus = [int.from_bytes(head[4:8], "little")] if len(head) >= 8 else []
    else:
        # Universal binary: big-endian slice table with cputype first in every entry.
        stride = FAT_STRIDE.get(head[:4], 0)
        count = int.from_bytes(head[4:8], "big") if stride and len(head) >= 8 else 0
        if not 0 < count <= MAX_SLICES or len(head) < 8 + count * stride:
            return set()
        cpus = [int.from_bytes(head[8 + index * stride:12 + index * stride], "big") for index in range(count)]
    return {MACH_CPUS[cpu] for cpu in cpus if cpu in MACH_CPUS}


def stage_candidate(approval):
    staged = ROOT / "omp-staged"
    staged.unlink(missing_ok=True)
    fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        result = hashlib.sha256()
        total = 0
        with os.fdopen(fd, "wb") as output, regular_file(STATE / "candidate") as (source, info):
            if info.st_size != approval["size"]:
                raise Hold("Candidate size does not match the approval")
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                # Identity is checked on the bytes being staged, not an earlier read of the source.
                if not total and ASSET not in asset_targets(chunk[:HEADER]):
                    raise Hold(f"Candidate is not a native {ASSET} executable")
                total += len(chunk)
                if total > approval["size"]:
                    raise Hold("Candidate grew while staging")
                result.update(chunk)
                output.write(chunk)
            if total != approval["size"] or result.hexdigest() != approval["sha256"]:
                raise Hold("Candidate SHA256 does not match the audit approval")
            output.flush()
            os.fchmod(output.fileno(), 0o700)
            os.fsync(output.fileno())
        return staged
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


def smoke_command(binary, args, cwd, environment, timeout):
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(
            [str(binary), *args], cwd=cwd, env=environment,
            stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            code = process.wait(timeout=timeout)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=2)
            raise
        output.seek(0)
        text = output.read(65537)
    if code != 0 or len(text) > 65536:
        raise Hold(f"Candidate {args[0]} smoke failed (exit {code})")
    return text.decode("utf-8", errors="replace").strip()


def smoke(binary, expected_version):
    # Outside the real home/project ancestry: no secrets, profiles or extensions.
    with tempfile.TemporaryDirectory(prefix="omp-upgrade-smoke-", dir="/tmp") as directory:
        base = Path(directory)
        home = base / "home"
        work = base / "work"
        home.mkdir(mode=0o700)
        work.mkdir(mode=0o700)
        environment = {
            "HOME": str(home), "PATH": "/usr/bin:/bin",
            "PI_CODING_AGENT_DIR": str(home / ".omp/agent"),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "XDG_DATA_HOME": str(home / ".local/share"),
            "XDG_STATE_HOME": str(home / ".local/state"),
            "TMPDIR": str(base), "TERM": "dumb", "LANG": "C.UTF-8", "NO_COLOR": "1",
        }
        actual = smoke_command(binary, ["--version"], work, environment, 5)
        if not re.fullmatch(r"(?:omp/|omp v?)?" + re.escape(expected_version), actual):
            raise Hold("Candidate version smoke does not match the approved release")
        source = work / "smoke.py"
        source.write_text("def upgrade_smoke(value: int) -> int:\n    return value + 1\n", encoding="utf-8")
        output = smoke_command(binary, ["read", str(source)], work, environment, 10)
        if "def upgrade_smoke(value: int) -> int:" not in output:
            raise Hold("Candidate native-read smoke did not return the Python function")


def finish_transaction():
    # Journal is removed last. A surviving rollback without a journal is never discarded.
    (ROOT / "omp-staged").unlink(missing_ok=True)
    (ROOT / "omp-rollback").unlink(missing_ok=True)
    sync_directory(ROOT)
    (STATE / "transaction.json").unlink(missing_ok=True)
    sync_directory(STATE)


def transaction_metadata():
    value = read_json(STATE / "transaction.json")
    if not isinstance(value, dict) or set(value) != {"old", "new"}:
        raise Hold("Upgrade recovery journal is invalid")
    old, new = manifest(value["old"]), manifest(value["new"])
    if version(new["version"]) <= version(old["version"]) or new["sha256"] == old["sha256"] or new["commit"] == old["commit"]:
        raise Hold("Upgrade recovery journal identities are invalid")
    return old, new


def recover_transaction():
    """Manifest commit is the decision point; everything before it rolls back."""
    old, new = transaction_metadata()
    installed = manifest(read_json(STATE / "installed.json"))
    current = digest(REAL) if REAL.exists() else None
    if installed == new and current == new["sha256"]:
        (STATE / "approved.json").unlink(missing_ok=True)
        (STATE / "candidate").unlink(missing_ok=True)
        sync_directory(STATE)
        report(status="INSTALLED", version=new["version"], summary=f"OMP {new['version']} activated; interrupted transaction cleanup recovered")
        finish_transaction()
        return "committed"
    if installed != old:
        raise Hold("Cannot reconcile installed source identity with upgrade journal")
    if current != old["sha256"]:
        rollback = ROOT / "omp-rollback"
        if digest(rollback) != old["sha256"]:
            raise Hold("Rollback binary failed its accepted SHA256; preserving recovery files")
        os.replace(rollback, REAL)
        sync_directory(ROOT)
    finish_transaction()
    return "restored"


def recovery_fallback():
    """A failed rename must not cause execution of an uncommitted replacement."""
    old, new = transaction_metadata()
    installed = manifest(read_json(STATE / "installed.json"))
    if installed == new and digest(REAL) == new["sha256"]:
        return REAL
    for target in (ROOT / "omp-rollback", REAL):
        try:
            if digest(target) == old["sha256"]:
                return target
        except (OSError, Hold):
            continue
    raise Hold("No verified last-known-good executable is available; recovery files retained")


def activate_if_ready(allow_install=True):
    """Never waits for the worker or another launcher. Caller may exec the fallback."""
    target = REAL
    with update_lock() as acquired:
        if not acquired:
            return target
        private_directory(ROOT)
        journal = STATE / "transaction.json"
        if journal.exists():
            try:
                outcome = recover_transaction()
                if outcome == "restored":
                    reject("Interrupted upgrade rolled back to the accepted release")
            except (OSError, ValueError, Hold) as error:
                report(status="HOLD", summary=f"Upgrade recovery failed: {error}", risks=[str(error)])
                return recovery_fallback()
        if not allow_install or not (STATE / "approved.json").exists():
            return target
        release = None
        try:
            if (ROOT / "omp-rollback").exists():
                raise Hold("Orphaned rollback retained; manual recovery required before another upgrade")
            installed = manifest(read_json(STATE / "installed.json"))
            approval = read_json(STATE / "approved.json")
            validate_approval(approval, installed)
            release = approval["version"]
            staged = stage_candidate(approval)
            # Smoke the integrity-checked stage, not REAL: failed smoke never disturbs old OMP.
            smoke(staged, release)
            if digest(staged) != approval["sha256"] or digest(REAL) != installed["sha256"]:
                raise Hold("Binary identity changed during candidate smoke; activation refused")
            updated = {key: approval[key] for key in MANIFEST_KEYS}
            write_json(journal, {"old": installed, "new": updated})
            os.link(REAL, ROOT / "omp-rollback", follow_symlinks=False)
            sync_directory(ROOT)
            os.replace(staged, REAL)
            sync_directory(ROOT)
            write_json(STATE / "installed.json", updated)
            (STATE / "approved.json").unlink()
            (STATE / "candidate").unlink(missing_ok=True)
            report(status="INSTALLED", version=release, summary=f"OMP {release} activated; version and native-read smoke passed")
            finish_transaction()
        except (OSError, ValueError, Hold, subprocess.SubprocessError) as error:
            try:
                reject(f"Upgrade not activated: {error}", release)
            except OSError:
                pass
            if journal.exists():
                try:
                    recover_transaction()
                except (OSError, ValueError, Hold) as rollback_error:
                    report(status="HOLD", summary=f"Rollback failed; recovery files retained: {rollback_error}", risks=[str(rollback_error)])
                    target = recovery_fallback()
            else:
                (ROOT / "omp-staged").unlink(missing_ok=True)
    return target


def request_audit():
    # ponytail: detached child instead of a systemd unit — one less machine-local
    # artifact to install, and audit.py already serializes itself with its own
    # lock plus the daily interval. Move back to a unit only if the audit needs
    # resource limits or to run without any interactive launch.
    error = None
    try:
        with open(os.devnull, "rb") as sink, open(os.devnull, "wb") as drain:
            subprocess.Popen(
                [sys.executable, "-I", str(AUDIT), "check"],
                stdin=sink, stdout=drain, stderr=drain,
                cwd=str(STATE), start_new_session=True,
            )
    except (OSError, subprocess.SubprocessError) as failure:
        error = f"Audit service unavailable: {failure}"
    try:
        with update_lock() as acquired:
            if acquired:
                report(service_error=error, service_requested_at=int(time.time()))
    except (OSError, Hold):
        pass
    return error


def without_profile(argv):
    # OMP strips profile flags before dispatching commands, including `update`.
    result = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--":
            result.extend(argv[index:])
            break
        if arg == "--profile":
            index += 2
            continue
        if arg.startswith("--profile="):
            index += 1
            continue
        result.append(arg)
        index += 1
    return result


def interactive_launch(argv):
    if not all(stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr)):
        return False
    # Conservative allowlist: unknown options, commands and automation pass through
    # untouched. Upgrade work is reserved for unambiguous interactive launches.
    switches = {
        "-c", "--continue", "--no-session", "--no-extensions", "--no-skills",
        "--no-rules", "--no-lsp", "--no-pty", "--no-tools", "--no-title",
        "--hide-thinking", "--advisor", "--prewalk", "--no-prewalk", "--allow-home",
    }
    values = {"--model", "--smol", "--slow", "--plan", "--provider", "--profile", "--cwd", "--thinking", "--models", "--resume", "-r"}
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in switches:
            index += 1
        elif arg in ("-r", "--resume"):
            index += 2 if index + 1 < len(argv) and not argv[index + 1].startswith("-") else 1
        elif arg in values and index + 1 < len(argv) and not argv[index + 1].startswith("-"):
            index += 2
        elif "=" in arg and arg.split("=", 1)[0] in values and arg.split("=", 1)[1]:
            index += 1
        else:
            return False
    return True


def safe_text(value, limit=None):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=True)
    text = "".join(char if char.isprintable() else " " if char.isspace() else "" for char in text)
    text = " ".join(text.split())
    return text if limit is None or len(text) <= limit else text[:limit] + "..."


def show_startup_notice():
    try:
        with update_lock() as acquired:
            if not acquired:
                return
            value = read_json(STATE / "report.json")
            if not isinstance(value, dict) or value.get("status") not in ("HOLD", "APPROVED", "INSTALLED"):
                return
            meaningful = {key: value.get(key) for key in ("status", "version", "summary", "features", "risks")}
            identity = hashlib.sha256(json.dumps(meaningful, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
            try:
                previous = read_json(STATE / "notice.json")
            except (OSError, ValueError, Hold):
                previous = None
            if previous == {"identity": identity}:
                return
            print(
                f"OMP upgrade {safe_text(value['status'])} {safe_text(value.get('version', 'unknown'), 40)}: "
                f"{safe_text(value.get('summary', 'Audit report available'), 240)} "
                "(omp --upgrade-status)",
                file=sys.stderr, flush=True,
            )
            write_json(STATE / "notice.json", {"identity": identity})
    except (OSError, ValueError, Hold):
        pass


def show_status():
    try:
        installed = manifest(read_json(STATE / "installed.json"))
        print(f"Installed: OMP {installed['version']} (source {installed['commit']})")
        print(f"Binary SHA256: {installed['sha256']}")
    except (OSError, ValueError, Hold) as error:
        print(f"Installed identity unavailable: {safe_text(str(error))}")
    try:
        value = read_json(STATE / "report.json")
        if not isinstance(value, dict):
            raise Hold("Report is not an object")
    except (OSError, ValueError, Hold) as error:
        print(f"Audit status unavailable: {safe_text(str(error))}")
        return 0
    print(f"Audit: {safe_text(value.get('status', 'UNKNOWN'))} (release {safe_text(value.get('version', 'unknown'))})")
    print(safe_text(value.get("summary", "No summary recorded")))
    for key, label in (("features", "Features"), ("risks", "Risks"), ("baseline_risks", "Accepted baseline risks"), ("limitations", "Audit limitations")):
        items = value.get(key)
        if items:
            print(f"{label}:")
            for item in items if isinstance(items, list) else [items]:
                print(f"  - {safe_text(item)}")
    if value.get("service_error"):
        print(f"Scheduling: {safe_text(value['service_error'])}")
    print("Checks run in the background, at most daily. Use omp --upgrade-apply to activate a staged release, or launch interactively.")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    routed = without_profile(argv)
    if routed == ["--upgrade-status"]:
        return show_status()
    if routed == ["--upgrade-check"]:
        error = request_audit()
        print(error or "Background audit requested (daily interval applies); inspect omp --upgrade-status.")
        return 1 if error else 0
    if routed == ["--upgrade-apply"]:
        if not (STATE / "approved.json").exists() and not (STATE / "transaction.json").exists():
            print("No reviewed release staged; inspect omp --upgrade-status.", file=sys.stderr)
            return 1
        try:
            activate_if_ready()
            value = read_json(STATE / "report.json")
            if value.get("status") == "INSTALLED" and not (STATE / "approved.json").exists():
                print(safe_text(value.get("summary", "Release installed")))
                return 0
            print("Release not activated (audit/activation may be busy): "
                  + safe_text(value.get("summary", "Inspect omp --upgrade-status")), file=sys.stderr)
        except (OSError, ValueError, Hold) as error:
            print("Release not activated: " + safe_text(str(error)), file=sys.stderr)
        return 1
    if routed and routed[0] == "update":
        print("Direct omp update is disabled: it bypasses the managed source audit. Use omp --upgrade-check, then omp --upgrade-status; approved releases activate on an interactive launch.", file=sys.stderr)
        return 2
    target = REAL
    interactive = interactive_launch(argv)
    # Recovery is exceptional; ordinary protocol/help/version calls do no hashing
    # and never schedule a service. An interrupted transaction must still be safe.
    if interactive or (STATE / "transaction.json").exists():
        try:
            target = activate_if_ready(allow_install=interactive)
        except (OSError, ValueError, Hold) as error:
            if (STATE / "transaction.json").exists():
                try:
                    target = recovery_fallback()
                except (OSError, ValueError, Hold) as failure:
                    print(f"OMP recovery requires intervention: {failure}", file=sys.stderr)
                    return 126
            # Filesystem/report failures must not break the installed binary.
        if interactive:
            show_startup_notice()
            request_audit()
    try:
        os.execv(str(target), [str(target), *argv])
    except OSError as error:
        print(f"Cannot launch managed OMP: {error}", file=sys.stderr)
        return 127


if __name__ == "__main__":
    raise SystemExit(main())
