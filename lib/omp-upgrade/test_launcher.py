"""Security boundaries and transaction outcomes; no downloaded code is executed."""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("managed_launcher", Path(__file__).with_name("launcher.py"))
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="test-omp-launcher-")
        self.addCleanup(self.temp.cleanup)
        # resolve(): macOS hands out /var/... which the child reports as /private/var
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "lib"
        self.state = self.base / "state"
        self.root.mkdir(mode=0o700)
        self.state.mkdir(mode=0o700)
        self.real = self.root / "omp-real"
        self.header = b"\xcf\xfa\xed\xfe" + (0x0100000C).to_bytes(4, "little") + bytes(24)
        patch = mock.patch.object(launcher, "ASSET", "omp-darwin-arm64")
        patch.start()
        self.addCleanup(patch.stop)
        self.old_bytes = self.header + b"old-accepted-binary"
        self.new_bytes = self.header + b"new-approved-binary"
        self.real.write_bytes(self.old_bytes)
        self.real.chmod(0o700)
        self.old = {"version": "18.1.13", "commit": "a" * 40, "sha256": self.sha(self.old_bytes)}
        self.new = {"version": "18.1.14", "commit": "b" * 40, "sha256": self.sha(self.new_bytes)}
        self.approval = {
            **self.new, "size": len(self.new_bytes), "base_sha256": self.old["sha256"],
            "asset_url": f"https://github.com/can1357/oh-my-pi/releases/download/v18.1.14/{launcher.ASSET}",
        }
        for name, value in (("ROOT", self.root), ("STATE", self.state), ("REAL", self.real), ("MIN_SIZE", 4)):
            patch = mock.patch.object(launcher, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        self.put("installed.json", self.old)

    @staticmethod
    def sha(data):
        return hashlib.sha256(data).hexdigest()

    def put(self, name, value):
        launcher.write_json(self.state / name, value)

    def get(self, name):
        return launcher.read_json(self.state / name)

    def approve(self, **changes):
        self.put("approved.json", {**self.approval, **changes})
        (self.state / "candidate").write_bytes(self.new_bytes)
        (self.state / "candidate").chmod(0o644)

    def assert_old_held(self):
        self.assertEqual(self.real.read_bytes(), self.old_bytes)
        self.assertEqual(self.get("installed.json"), self.old)
        self.assertFalse((self.state / "approved.json").exists())
        self.assertEqual(self.get("report.json")["status"], "HOLD")

    def test_integrity_rejection_happens_before_candidate_execution(self):
        self.approve()
        (self.state / "candidate").write_bytes(self.header + b"x" * (len(self.new_bytes) - len(self.header)))
        with mock.patch.object(launcher, "smoke") as execute:
            self.assertEqual(launcher.activate_if_ready(), self.real)
        execute.assert_not_called()
        self.assert_old_held()
        self.assertIn("SHA256", self.get("report.json")["summary"])

    def test_wrong_platform_is_rejected_before_execution(self):
        elf = b"\x7fELF\x02\x01" + bytes(12) + (183).to_bytes(2, "little") + bytes(44)
        self.new_bytes = elf
        self.approve(size=len(elf), sha256=self.sha(elf))
        with mock.patch.object(launcher, "smoke") as execute:
            launcher.activate_if_ready()
        execute.assert_not_called()
        self.assert_old_held()
        self.assertIn("native", self.get("report.json")["summary"])

    def test_explicit_apply_activates_without_starting_session(self):
        self.approve()
        with mock.patch.object(launcher, "smoke"), mock.patch("builtins.print"), \
             mock.patch.object(launcher.os, "execv") as execute:
            self.assertEqual(launcher.main(["--upgrade-apply"]), 0)
            self.assertEqual(launcher.main(["--upgrade-apply"]), 1)
        execute.assert_not_called()
        self.assertEqual(self.get("installed.json")["version"], self.approval["version"])
        self.assertEqual(self.real.read_bytes(), self.new_bytes)

    def test_apply_reports_gate_failure_without_traceback(self):
        self.approve()
        with mock.patch.object(launcher, "activate_if_ready", side_effect=launcher.Hold("Unsafe update lock")), \
             mock.patch("builtins.print") as output:
            self.assertEqual(launcher.main(["--upgrade-apply"]), 1)
        self.assertIn("Unsafe update lock", output.call_args.args[0])
        self.assertEqual(self.real.read_bytes(), self.old_bytes)

    def test_metadata_trust_boundaries_are_rejected_without_execution(self):
        invalid = [
            {"asset_url": self.approval["asset_url"] + "?redirect=evil"},
            {"version": "18.1.14-beta.1"},
            {"version": "018.1.14"},
            {"commit": "z" * 40},
            {"sha256": "G" * 64},
            {"size": True},
            {"size": launcher.MAX_SIZE + 1},
            {"base_sha256": "c" * 64},
            {"commit": self.old["commit"]},
            {"extra": "untrusted"},
        ]
        for changes in invalid:
            with self.subTest(changes=changes):
                self.approve(**changes)
                with mock.patch.object(launcher, "smoke") as execute:
                    launcher.activate_if_ready()
                execute.assert_not_called()
                self.assert_old_held()

    def test_stale_approval_is_consumed(self):
        self.approve(version=self.old["version"])
        with mock.patch.object(launcher, "smoke") as execute:
            launcher.activate_if_ready()
        execute.assert_not_called()
        self.assert_old_held()
        self.assertIn("stale", self.get("report.json")["summary"])

    def test_installed_binary_drift_cannot_receive_a_baseline_approval(self):
        self.approve()
        changed = self.old_bytes + b"outside-update"
        self.real.write_bytes(changed)
        with mock.patch.object(launcher, "smoke") as execute:
            launcher.activate_if_ready()
        execute.assert_not_called()
        self.assertEqual(self.real.read_bytes(), changed)
        self.assertEqual(self.get("installed.json"), self.old)
        self.assertEqual(self.get("report.json")["status"], "HOLD")

    def test_candidate_symlink_does_not_cross_the_file_boundary(self):
        self.approve()
        outside = self.base / "outside"
        outside.write_bytes(self.new_bytes)
        candidate = self.state / "candidate"
        candidate.unlink()
        candidate.symlink_to(outside)
        with mock.patch.object(launcher, "smoke") as execute:
            launcher.activate_if_ready()
        execute.assert_not_called()
        self.assert_old_held()
        self.assertEqual(outside.read_bytes(), self.new_bytes)

    def test_valid_activation_commits_only_after_smoke(self):
        self.approve()
        self.put("report.json", {"features": ["Useful feature"], "risks": [], "status": "APPROVED"})

        def candidate_smoke(binary, expected):
            self.assertEqual(binary.read_bytes(), self.new_bytes)
            self.assertEqual(self.real.read_bytes(), self.old_bytes)
            self.assertEqual(self.get("installed.json"), self.old)
            self.assertEqual(expected, self.new["version"])

        with mock.patch.object(launcher, "smoke", side_effect=candidate_smoke):
            self.assertEqual(launcher.activate_if_ready(), self.real)
        self.assertEqual(self.real.read_bytes(), self.new_bytes)
        self.assertEqual(self.get("installed.json"), self.new)
        self.assertEqual(self.get("report.json")["status"], "INSTALLED")
        self.assertEqual(self.get("report.json")["features"], ["Useful feature"])
        for path in (self.root / "omp-rollback", self.root / "omp-staged", self.state / "approved.json", self.state / "candidate", self.state / "transaction.json"):
            self.assertFalse(path.exists(), str(path))

    def test_smoke_failure_never_replaces_last_known_good(self):
        self.approve()
        with mock.patch.object(launcher, "smoke", side_effect=launcher.Hold("native read failed")):
            self.assertEqual(launcher.activate_if_ready(), self.real)
        self.assert_old_held()
        self.assertFalse((self.state / "transaction.json").exists())
        self.assertFalse((self.root / "omp-staged").exists())

    def test_stage_changed_during_smoke_cannot_be_activated(self):
        self.approve()

        def tamper(binary, _version):
            binary.write_bytes(self.new_bytes + b"changed")

        with mock.patch.object(launcher, "smoke", side_effect=tamper):
            launcher.activate_if_ready()
        self.assert_old_held()

    def fail_manifest_commit(self, path, value):
        if path == self.state / "installed.json" and value == self.new:
            raise OSError("simulated manifest commit failure")
        self.original_write(path, value)

    def test_failed_manifest_commit_restores_old_binary(self):
        self.approve()
        self.original_write = launcher.write_json
        with mock.patch.object(launcher, "smoke"), mock.patch.object(launcher, "write_json", side_effect=self.fail_manifest_commit):
            self.assertEqual(launcher.activate_if_ready(), self.real)
        self.assert_old_held()
        self.assertFalse((self.root / "omp-rollback").exists())
        self.assertFalse((self.state / "transaction.json").exists())

    def test_failed_rollback_preserves_and_launches_verified_backup_then_recovers(self):
        self.approve()
        self.original_write = launcher.write_json
        original_replace = os.replace
        rollback = self.root / "omp-rollback"

        def fail_rollback(source, destination, *args, **kwargs):
            if Path(source) == rollback:
                raise OSError("simulated rollback rename failure")
            return original_replace(source, destination, *args, **kwargs)

        with mock.patch.object(launcher, "smoke"), mock.patch.object(launcher, "write_json", side_effect=self.fail_manifest_commit), mock.patch.object(launcher.os, "replace", side_effect=fail_rollback):
            self.assertEqual(launcher.activate_if_ready(), rollback)
        self.assertEqual(rollback.read_bytes(), self.old_bytes)
        self.assertEqual(self.real.read_bytes(), self.new_bytes)
        self.assertEqual(self.get("installed.json"), self.old)
        self.assertTrue((self.state / "transaction.json").exists())
        self.assertFalse((self.state / "approved.json").exists())
        self.assertEqual(self.get("report.json")["status"], "HOLD")
        self.assertEqual(launcher.activate_if_ready(allow_install=False), self.real)
        self.assertEqual(self.real.read_bytes(), self.old_bytes)
        self.assertFalse(rollback.exists())
        self.assertFalse((self.state / "transaction.json").exists())

    def test_interrupted_committed_transaction_is_finished_not_rolled_back(self):
        self.approve()
        self.put("report.json", {"status": "APPROVED", "features": ["Audited feature"], "risks": []})
        self.real.write_bytes(self.new_bytes)
        (self.root / "omp-rollback").write_bytes(self.old_bytes)
        self.put("installed.json", self.new)
        self.put("transaction.json", {"old": self.old, "new": self.new})
        self.assertEqual(launcher.activate_if_ready(), self.real)
        self.assertEqual(self.real.read_bytes(), self.new_bytes)
        self.assertEqual(self.get("installed.json"), self.new)
        self.assertFalse((self.root / "omp-rollback").exists())
        self.assertFalse((self.state / "transaction.json").exists())
        self.assertFalse((self.state / "approved.json").exists())
        self.assertFalse((self.state / "candidate").exists())
        self.assertEqual(self.get("report.json")["status"], "INSTALLED")
        self.assertEqual(self.get("report.json")["version"], self.new["version"])
        self.assertEqual(self.get("report.json")["features"], ["Audited feature"])

    def test_unjournaled_last_known_good_is_never_deleted(self):
        self.approve()
        rollback = self.root / "omp-rollback"
        rollback.write_bytes(self.old_bytes)
        with mock.patch.object(launcher, "smoke") as execute:
            launcher.activate_if_ready()
        execute.assert_not_called()
        self.assert_old_held()
        self.assertEqual(rollback.read_bytes(), self.old_bytes)

    def test_contended_lock_skips_without_consuming_approval(self):
        self.approve()
        with launcher.update_lock() as acquired:
            self.assertTrue(acquired)
            with mock.patch.object(launcher, "smoke") as execute:
                self.assertEqual(launcher.activate_if_ready(), self.real)
        execute.assert_not_called()
        self.assertTrue((self.state / "approved.json").exists())
        self.assertEqual(self.real.read_bytes(), self.old_bytes)

    def test_automation_even_with_tty_never_hashes_installs_or_schedules(self):
        self.approve()
        calls = [["--version"], ["--help"], ["read", "/tmp/file"], ["acp"], ["--mode", "rpc"], ["--mode=json"], ["-p", "prompt"], ["__omp_worker_js_eval"], ["--smoke-test"]]
        with contextlib.ExitStack() as stack:
            for stream in (sys.stdin, sys.stdout, sys.stderr):
                stack.enter_context(mock.patch.object(stream, "isatty", return_value=True))
            execute = stack.enter_context(mock.patch.object(launcher.os, "execv"))
            schedule = stack.enter_context(mock.patch.object(launcher, "request_audit"))
            hashing = stack.enter_context(mock.patch.object(launcher, "digest"))
            for argv in calls:
                with self.subTest(argv=argv):
                    launcher.main(argv)
                    execute.assert_called_with(str(self.real), [str(self.real), *argv])
        schedule.assert_not_called()
        hashing.assert_not_called()
        self.assertTrue((self.state / "approved.json").exists())

    def test_audit_spawn_failure_does_not_break_interactive_launch(self):
        with mock.patch.object(launcher, "interactive_launch", return_value=True), mock.patch.object(launcher.subprocess, "Popen", side_effect=OSError("no python")), mock.patch.object(launcher.os, "execv") as execute:
            launcher.main([])
        execute.assert_called_once_with(str(self.real), [str(self.real)])
        self.assertIn("service unavailable", self.get("report.json")["service_error"])

    def test_safe_update_checks_then_activates_approved_candidate(self):
        self.put("report.json", {"status": "APPROVED", "version": self.new["version"], "summary": "artifact passed"})
        result = subprocess.CompletedProcess(["audit.py", "check"], 0, "", "")
        def activate(**_):
            self.put("report.json", {"status": "INSTALLED", "version": self.new["version"], "summary": "installed"})
        with mock.patch.object(launcher.subprocess, "run", return_value=result), \
             mock.patch.object(launcher, "activate_if_ready", side_effect=activate) as activate_mock, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(launcher.main(["safe-update"]), 0)
        activate_mock.assert_called_once_with(allow_install=True)
        self.assertIn("installed", output.getvalue())

    def test_safe_update_stops_on_failed_artifact_check(self):
        self.put("report.json", {"status": "HOLD", "summary": "signature mismatch"})
        result = subprocess.CompletedProcess(["audit.py", "check"], 1, "", "")
        with mock.patch.object(launcher.subprocess, "run", return_value=result), \
             mock.patch.object(launcher, "activate_if_ready") as activate, \
             contextlib.redirect_stderr(io.StringIO()) as output:
            self.assertEqual(launcher.main(["safe-update"]), 1)
        activate.assert_not_called()
        self.assertIn("signature mismatch", output.getvalue())

    def test_interactive_launch_does_not_auto_activate_approved_candidate(self):
        self.approve()
        with mock.patch.object(launcher, "interactive_launch", return_value=True), \
             mock.patch.object(launcher, "activate_if_ready", return_value=self.real) as activate, \
             mock.patch.object(launcher, "request_audit"), \
             mock.patch.object(launcher.os, "execv"):
            launcher.main([])
        activate.assert_called_once_with(allow_install=False)

    def test_direct_update_and_profile_alias_update_are_blocked(self):
        for argv in (["update"], ["--profile", "work", "update"], ["--profile=work", "update", "--check"]):
            with self.subTest(argv=argv), mock.patch.object(launcher.os, "execv") as execute, contextlib.redirect_stderr(io.StringIO()) as output:
                self.assertEqual(launcher.main(argv), 2)
            execute.assert_not_called()
            self.assertIn("safe-update", output.getvalue())

    def test_actual_exec_preserves_arguments_cwd_stdio_environment_and_exit(self):
        self.real.write_text(
            "#!/usr/bin/python3\nimport json, os, sys\n"
            "print(json.dumps({'args': sys.argv[1:], 'cwd': os.getcwd(), 'env': os.environ['OMP_TEST_PASSTHROUGH']}))\n"
            "print('unhidden stderr', file=sys.stderr)\nsys.exit(23)\n", encoding="utf-8"
        )
        argv = ["--mode", "rpc", "spaces and a\nnewline", "--literal=$value"]
        bootstrap = (
            "import importlib.util, pathlib; "
            f"s=importlib.util.spec_from_file_location('launch', {str(Path(launcher.__file__))!r}); "
            "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
            f"m.REAL=pathlib.Path({str(self.real)!r}); m.STATE=pathlib.Path({str(self.state)!r}); "
            f"raise SystemExit(m.main({argv!r}))"
        )
        result = subprocess.run([sys.executable, "-c", bootstrap], cwd=self.base, env={**os.environ, "OMP_TEST_PASSTHROUGH": "unchanged"}, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 23)
        self.assertEqual(json.loads(result.stdout), {"args": argv, "cwd": str(self.base), "env": "unchanged"})
        self.assertEqual(result.stderr, "unhidden stderr\n")

    def test_actual_smoke_has_clean_home_environment_and_native_read_contract(self):
        executable = self.base / "smoke-probe"
        executable.write_text(
            "#!/usr/bin/python3\nimport os, pathlib, sys\n"
            "assert not any(k in os.environ for k in ['OPENAI_API_KEY', 'NODE_OPTIONS', 'OMP_PROFILE', 'PI_PACKAGE_DIR'])\n"
            f"assert os.environ['HOME'] != {str(Path.home())!r}\n"
            "assert pathlib.Path(os.environ['PI_CODING_AGENT_DIR']).is_relative_to(os.environ['HOME'])\n"
            "if sys.argv[1] == '--version': print('omp/18.1.14')\n"
            "elif sys.argv[1] == 'read': print(pathlib.Path(sys.argv[2]).read_text())\n"
            "else: sys.exit(9)\n", encoding="utf-8"
        )
        executable.chmod(0o700)
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "must-not-leak", "NODE_OPTIONS": "unsafe", "OMP_PROFILE": "unsafe", "PI_PACKAGE_DIR": "unsafe"}):
            launcher.smoke(executable, "18.1.14")
        with self.assertRaisesRegex(launcher.Hold, "version smoke"):
            launcher.smoke(executable, "18.1.15")

    def test_interactive_resume_with_optional_session_requests_audit(self):
        with contextlib.ExitStack() as stack:
            for stream in (sys.stdin, sys.stdout, sys.stderr):
                stack.enter_context(mock.patch.object(stream, "isatty", return_value=True))
            stack.enter_context(mock.patch.object(launcher.os, "execv"))
            schedule = stack.enter_context(mock.patch.object(launcher, "request_audit"))
            for argv in (["--resume"], ["-r"], ["--resume", "session-id"], ["-r", "session-id"], ["--resume=session-id"], ["-r", "--no-session"]):
                with self.subTest(argv=argv):
                    schedule.reset_mock()
                    launcher.main(argv)
                    schedule.assert_called_once()

    def test_startup_notice_is_sanitized_and_repeats_only_for_meaningful_changes(self):
        value = {"status": "HOLD", "version": "18.1.14", "summary": "\x1b]52;c;secret\x07 unsafe\u202etext", "risks": ["telemetry"], "checked_at_epoch": 1}
        self.put("report.json", value)
        with contextlib.redirect_stderr(io.StringIO()) as output, mock.patch.object(launcher, "interactive_launch", return_value=True), mock.patch.object(launcher, "request_audit"), mock.patch.object(launcher.os, "execv"):
            launcher.main([])
            self.put("report.json", {**value, "checked_at_epoch": 2})
            launcher.main([])
            self.put("report.json", {**value, "checked_at_epoch": 3, "risks": ["changed risk"]})
            launcher.main([])
        text = output.getvalue()
        self.assertEqual(text.count("omp --upgrade-status"), 2)
        self.assertIn("HOLD 18.1.14", text)
        for control in ("\x1b", "\x07", "\u202e"):
            self.assertNotIn(control, text)

    def test_successful_service_request_clears_stale_failure(self):
        self.put("report.json", {"status": "CURRENT", "service_error": "previous unavailable"})
        with mock.patch.object(launcher.subprocess, "Popen"):
            self.assertIsNone(launcher.request_audit())
        self.assertIsNone(self.get("report.json")["service_error"])
        self.assertEqual(self.get("report.json")["status"], "CURRENT")

    def test_large_worker_report_survives_scheduling_and_remains_visible(self):
        value = {"status": "HOLD", "version": "18.1.14", "summary": "Audited risk", "risks": ["Evidence " * 10000], "checked_at_epoch": 123}
        self.put("report.json", value)
        with mock.patch.object(launcher.subprocess, "Popen"):
            launcher.request_audit()
        for key, expected in value.items():
            self.assertEqual(self.get("report.json")[key], expected)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            launcher.show_status()
        self.assertIn("HOLD", output.getvalue())
        self.assertIn(value["risks"][0].strip(), output.getvalue())

    def test_unreadable_existing_report_is_not_replaced_by_scheduling_metadata(self):
        payloads = (b"{malformed", b"[]", json.dumps({"summary": "x" * launcher.REPORT_LIMIT}).encode())
        for payload in payloads:
            with self.subTest(size=len(payload)):
                (self.state / "report.json").write_bytes(payload)
                with mock.patch.object(launcher.subprocess, "Popen"):
                    launcher.request_audit()
                self.assertEqual((self.state / "report.json").read_bytes(), payload)

    def test_profile_aliases_route_managed_status_and_check_commands(self):
        self.put("report.json", {"status": "CURRENT", "version": "18.1.13", "summary": "Accepted release"})
        for profile in (["--profile", "work"], ["--profile=work"]):
            with self.subTest(profile=profile), contextlib.redirect_stdout(io.StringIO()) as output, mock.patch.object(launcher.os, "execv") as execute, mock.patch.object(launcher, "request_audit", return_value=None) as schedule:
                self.assertEqual(launcher.main([*profile, "--upgrade-status"]), 0)
                self.assertIn("Installed: OMP 18.1.13", output.getvalue())
                schedule.assert_not_called()
                self.assertEqual(launcher.main([*profile, "--upgrade-check"]), 0)
                schedule.assert_called_once()
                execute.assert_not_called()

    def test_status_shows_installed_identity_features_and_risks_without_execution(self):
        self.put("report.json", {"status": "HOLD", "version": "18.1.14", "summary": "Audit found a new outbound destination", "features": ["New reader"], "risks": ["Unexpected telemetry"]})
        with contextlib.redirect_stdout(io.StringIO()) as output, mock.patch.object(launcher.os, "execv") as execute:
            self.assertEqual(launcher.main(["--upgrade-status"]), 0)
        execute.assert_not_called()
        self.assertIn("18.1.13", output.getvalue())
        self.assertIn("New reader", output.getvalue())
        self.assertIn("Unexpected telemetry", output.getvalue())


if __name__ == "__main__":
    unittest.main()
