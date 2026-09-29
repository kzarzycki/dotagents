"""Deterministic fail-closed boundary tests; no network or model calls."""
import collections
import contextlib
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
import tempfile
import unittest
from unittest import mock

import audit


BASE = {"version": "18.1.13", "commit": "a" * 40, "sha256": "b" * 64}
DIFF = "diff --git a/example.py b/example.py\n--- a/example.py\n+++ b/example.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"


def verdict(**overrides):
    value = {"verdict": "SAFE", "reviewed": True, "chunk_id": "chunk-001-of-001",
             "source_sha256": hashlib.sha256(DIFF.encode()).hexdigest(), "risks": [],
             "breaking_changes": [], "features": ["Changes public example value"], "uncertainties": [],
             "capability_facts": []}
    value.update(overrides)
    return value


def release(version="18.1.14", digest="c" * 64, size=audit.MIN_ASSET):
    tag = "v" + version
    return {"draft": False, "prerelease": False, "tag_name": tag,
            "html_url": f"https://github.com/can1357/oh-my-pi/releases/tag/{tag}", "body": "- Public feature claim",
            "assets": [{"name": audit.ASSET, "state": "uploaded", "size": size, "digest": "sha256:" + digest,
                        "browser_download_url": f"https://github.com/can1357/oh-my-pi/releases/download/{tag}/{audit.ASSET}"}]}


def model_stream(stop="stop", end=True, **overrides):
    message = {"role": "assistant", "provider": "openai-codex", "model": "gpt-6-astra", "stopReason": stop,
               "content": [{"type": "text", "text": json.dumps(verdict())}]}
    message.update(overrides)
    events = [{"type": "message_end", "message": message}]
    if end:
        events.append({"type": "agent_end", "messages": []})
    return ("\n".join(map(json.dumps, events)) + "\n").encode()


class VerdictTests(unittest.TestCase):
    def test_malformed_or_ambiguous_verdict_never_approves(self):
        good = verdict()
        malformed = ["```json\n" + json.dumps(good) + "\n```", json.dumps(good)[:-1],
                     json.dumps({**good, "reviewed": "true"}), json.dumps({**good, "risks": None}),
                     json.dumps({**good, "unknown": True}), json.dumps({key: value for key, value in good.items() if key != "uncertainties"}),
                     json.dumps(good).replace('"verdict": "SAFE"', '"verdict": "HOLD", "verdict": "SAFE"')]
        for text in malformed:
            with self.subTest(text=text), self.assertRaises(audit.Hold):
                audit.parse_verdict(text, good["chunk_id"], good["source_sha256"])

    def test_safe_label_cannot_hide_risks_breaking_changes_or_uncertainty(self):
        for field in ("risks", "breaking_changes", "uncertainties"):
            with self.subTest(field=field):
                value = audit.parse_verdict(json.dumps(verdict(**{field: ["example.py:1 unsafe change"]})),
                                            "chunk-001-of-001", hashlib.sha256(DIFF.encode()).hexdigest())
                self.assertFalse(audit.verdict_safe(value))
        self.assertFalse(audit.verdict_safe(verdict(reviewed=False)))
        self.assertFalse(audit.verdict_safe(verdict(verdict="HOLD")))

    def test_wrong_chunk_or_digest_is_not_review_evidence(self):
        for changes in ({"chunk_id": "chunk-002-of-002"}, {"source_sha256": "d" * 64}):
            with self.subTest(changes=changes), self.assertRaises(audit.Hold):
                audit.parse_verdict(json.dumps(verdict(**changes)), "chunk-001-of-001", hashlib.sha256(DIFF.encode()).hexdigest())

    def test_truncated_model_completion_is_rejected_even_with_valid_json(self):
        for stop in ("length", "error", "aborted", "toolUse"):
            with self.subTest(stop=stop), self.assertRaises(audit.Hold):
                audit.completion_text(model_stream(stop=stop), "openai-codex/gpt-6-astra:medium")
        with self.assertRaises(audit.Hold):
            audit.completion_text(model_stream(end=False), "openai-codex/gpt-6-astra:medium")
        with self.assertRaises(audit.Hold):
            audit.completion_text(model_stream(model="unexpected-fallback"), "openai-codex/gpt-6-astra:medium")
        self.assertEqual(json.loads(audit.completion_text(model_stream(), "openai-codex/gpt-6-astra:medium")), verdict())

    def test_full_diff_chunk_coverage_and_oversize_rejection(self):
        second = DIFF.replace("example.py", "second.py")
        with mock.patch.object(audit, "MAX_CHUNK", len(DIFF.encode()) + 1):
            chunks = audit.split_diff(DIFF + second)
            self.assertEqual(chunks, [DIFF, second])
            self.assertEqual("".join(chunks), DIFF + second)
            with self.assertRaises(audit.Hold):
                audit.split_diff(DIFF + "+" + "x" * 200)
        with mock.patch.object(audit, "MAX_SOURCE", 10), self.assertRaises(audit.Hold):
            audit.split_diff(DIFF)

    def test_chunk_coverage_rejects_missing_content(self):
        with mock.patch.object(audit, "split_file_patch", return_value=[DIFF[:-1]]):
            with self.assertRaises(audit.Hold):
                audit.split_diff(DIFF)

    def test_keyed_object_lists_do_not_emit_shift_cascade(self):
        before = [{"id": "a", "url": "one"}, {"id": "b", "url": "two"}, {"id": "c", "url": "three"}]
        after = [{"id": "b", "url": "changed"}, {"id": "c", "url": "three"}]
        records = list(audit.json_diff_records(before, after, ("providers",)))
        self.assertEqual(records, [
            {"op": "order", "path": ["providers"], "side": "old", "offset": 0, "items": ["a"]},
            {"op": "remove-container", "path": ["providers", {"id": "a"}], "kind": "object", "length": 1},
            {"op": "remove", "path": ["providers", {"id": "a"}, "url"], "old": "one"},
            {"op": "change", "path": ["providers", {"id": "b"}, "url"], "old": "two", "value": "changed"},
        ])
        reordered = list(audit.json_diff_records(before, [before[1], before[0], before[2]]))
        expected_move = [
            {"op": "order", "path": [], "side": "value", "offset": 0, "items": ["b"]},
            {"op": "order", "path": [], "side": "old", "offset": 1, "items": ["b"]},
        ]
        self.assertEqual(reordered[:2], expected_move)
        self.assertEqual(list(audit.json_diff_records({"a": 1, "b": 2}, {"b": 2, "a": 1})), expected_move)
        self.assertEqual(list(audit.json_added_records({"b": 2, "a": 1}, ("entry",)))[:1], [
            {"op": "order", "path": ["entry"], "side": "value", "offset": 0, "items": ["b", "a"]}
        ])
        self.assertEqual(list(audit.json_removed_records({"b": 2, "a": 1}, ("entry",))), [
            {"op": "remove-container", "path": ["entry"], "kind": "object", "length": 2},
            {"op": "remove", "path": ["entry", "b"], "old": 2},
            {"op": "remove", "path": ["entry", "a"], "old": 1},
        ])
        self.assertEqual(audit.compact_json_path(("a/b", 0, {"id": "x/y~z"})), '/k:a~1b/i:0/@["id","x~1y~0z"]')

    def test_semantic_diff_preserves_container_removal_and_number_lexemes(self):
        removed = audit.semantic_json_diff("catalog.json", b'{"paths":[[1]]}', b'{"paths":[]}')
        retained = audit.semantic_json_diff("catalog.json", b'{"paths":[[1]]}', b'{"paths":[[]]}')
        self.assertIn('["remove-container","/k:paths/i:0","array",1]', removed)
        self.assertNotIn('["remove-container","/k:paths/i:0","array",1]', retained)
        self.assertNotEqual(removed, retained)
        self.assertIn('["change","/k:token","#0","#-0"]', audit.semantic_json_diff(
            "catalog.json", b'{"token":0}', b'{"token":-0}'))
        self.assertIn('["change","/k:token","#0.0","#-0.0"]', audit.semantic_json_diff(
            "catalog.json", b'{"token":0.0}', b'{"token":-0.0}'))

    def test_numeric_and_string_keyed_order_remains_type_sensitive(self):
        before = b'[{"id":1},{"id":"1"}]'
        after = b'[{"id":"1"},{"id":1}]'
        self.assertEqual([record["op"] for record in audit.json_diff_records(
            audit.strict_json(before, preserve_numbers=True),
            audit.strict_json(after, preserve_numbers=True))], ["order", "order"])
        numeric_reorder = audit.semantic_json_diff(
            "catalog.json", b'{"hosts":[{"id":1},{"id":2}]}', b'{"hosts":[{"id":2},{"id":1}]}')
        self.assertIn('"#2"', numeric_reorder)
        records = list(audit.json_order_side((), "value", 0, [audit.JSONNumber("1")] * 2000))
        self.assertTrue(records)
        self.assertTrue(all(len(json.dumps(["order", "", "value", 0, audit.json_semantic_value(record["items"])],
                                           ensure_ascii=True, separators=(",", ":")).encode()) <= audit.MAX_JSON_RECORD
                            for record in records))
        self.assertIn('["change","/k:token","##literal","##next"]', audit.semantic_json_diff(
            "catalog.json", b'{"token":"#literal"}', b'{"token":"#next"}'))

    def test_oversized_json_blob_is_compacted_with_separate_bound(self):
        before = b'{"padding":"' + b'a' * (1024 * 1024 + 1) + b'","endpoint":"old"}'
        after = before.replace(b'"endpoint":"old"', b'"endpoint":"new"')
        patch = ("diff --git a/catalog.json b/catalog.json\nold mode 100644\nnew mode 100755\n"
                 "index " + "0" * 40 + ".." + "1" * 40 + "\n--- a/catalog.json\n+++ b/catalog.json\n"
                 "@@ -1 +1 @@\n+" + "x" * (audit.MAX_CHUNK + 1) + "\n")

        def blob(commit, path, limit):
            self.assertEqual(limit, audit.MAX_STRUCTURED_JSON)
            return before if commit == "base" else after

        with mock.patch.object(audit, "manifest_blob", side_effect=blob):
            compacted = audit.compact_large_json_patches(patch, {"commit": "base"}, {"commit": "target"})
        self.assertLess(len(compacted.encode()), audit.MAX_CHUNK)
        self.assertIn('["change","/k:endpoint","old","new"]', compacted)
        self.assertIn("old mode 100644", compacted)
        self.assertIn("new mode 100755", compacted)
        with mock.patch.object(audit, "MAX_STRUCTURED_JSON", 10), \
             mock.patch.object(audit, "manifest_blob", return_value=b"x" * 11), self.assertRaises(audit.Hold):
            audit.structured_json_blob("commit", "large.json")

    def test_large_json_uses_exhaustive_semantic_records_and_splits(self):
        before = b'{"providers":{"old":{"url":"https://old.example"}},"stable":1}'
        after = b'{"providers":{"new":{"url":"https://new.example"}},"stable":2}'
        patch = audit.semantic_json_diff("catalog.json", before, after)
        self.assertIn("semantic-json-diff ", patch)
        self.assertIn('["add","/k:providers/k:new/k:url","https://new.example"]', patch)
        self.assertIn('["remove","/k:providers/k:old/k:url","https://old.example"]', patch)
        with mock.patch.object(audit, "MAX_CHUNK", 360):
            chunks = audit.split_diff(patch)
        self.assertTrue(all(len(chunk.encode()) <= 360 for chunk in chunks))
        self.assertTrue(chunks[1].startswith("continued-diff a/catalog.json b/catalog.json\n"))
        with self.assertRaises(audit.Hold):
            audit.semantic_json_diff("catalog.json", b'{"a":1,"a":2}', b'{}')

    def test_semantic_expansion_is_incrementally_bounded(self):
        after = json.dumps({"urls": [0] * 10000}).encode()
        with self.assertRaises(audit.Hold):
            audit.semantic_json_diff("large.json", None, after, max_bytes=4096)
        nested, current = {}, None
        current = nested
        for _ in range(audit.MAX_JSON_DEPTH + 1):
            child = {}
            current["x"] = child
            current = child
        with self.assertRaises(audit.Hold):
            audit.semantic_json_diff("deep.json", None, json.dumps(nested).encode())

    def test_oversized_json_order_comparison_fails_before_matching(self):
        before = list(range(audit.MAX_ORDER_ITEMS // 2 + 1))
        after = before[::-1]
        with self.assertRaises(audit.Hold):
            list(audit.json_order_records((), before, after))

    def test_informational_json_is_not_parsed_or_compacted(self):
        path = "tests/fixtures/large.json"
        patch = f"diff --git a/{path} b/{path}\n+" + "not-json" * audit.MAX_CHUNK + "\n"
        with mock.patch.object(audit, "manifest_blob") as manifest:
            self.assertEqual(audit.compact_large_json_patches(
                patch, {"commit": BASE["commit"]}, {"commit": "e" * 40}), patch)
        manifest.assert_not_called()

    def test_oversized_text_file_splits_at_hunks(self):
        patch = (
            "diff --git a/example.py b/example.py\n"
            "--- a/example.py\n+++ b/example.py\n"
            "@@ -1 +1 @@\n-x = 1\n+x = 2\n"
            "@@ -10 +10 @@\n-y = 1\n+y = 2\n"
        )
        with mock.patch.object(audit, "MAX_CHUNK", 100):
            chunks = audit.split_diff(patch)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[1].startswith("continued-diff a/example.py b/example.py\n"))
        self.assertTrue(all(len(chunk.encode()) <= 100 for chunk in chunks))
        self.assertEqual(re.sub(r"(?m)^continued-diff [^\n]*\n", "", "".join(chunks)), patch)

    def test_wrong_asset_url_or_digest_cannot_become_target(self):
        for changed in ({"browser_download_url": f"https://example.com/{audit.ASSET}"},
                        {"digest": None}, {"digest": "sha256:" + "g" * 64}, {"size": True}):
            data = release()
            data["assets"][0].update(changed)
            with self.subTest(changed=changed), self.assertRaises(audit.Hold):
                audit.release_identity(data)
        for version in ("18.01.14", "18.1.14-rc1", "18.1.14+build"):
            with self.subTest(version=version), self.assertRaises(audit.Hold):
                audit.release_identity(release(version=version))

    def test_annotated_tags_resolve_exact_commit_and_reject_cycles(self):
        tag, commit = "d" * 40, "e" * 40
        replies = [{"ref": "refs/tags/v18.1.14", "object": {"type": "tag", "sha": tag}},
                   {"sha": tag, "object": {"type": "commit", "sha": commit}}]
        with mock.patch.object(audit, "api_json", side_effect=replies):
            self.assertEqual(audit.tag_commit("18.1.14"), commit)
        replies[1]["object"] = {"type": "tag", "sha": tag}
        with mock.patch.object(audit, "api_json", side_effect=replies), self.assertRaises(audit.Hold):
            audit.tag_commit("18.1.14")

    def test_resolve_review_model_prefers_slow_role_then_falls_back_to_default(self):
        self.assertEqual(
            audit.resolve_review_model("modelRoles:\n  slow: openai-codex/gpt-5.6-luna:high\n  default: openai-codex/gpt-6-astra\n"),
            "openai-codex/gpt-5.6-luna:high")
        self.assertEqual(
            audit.resolve_review_model("modelRoles:\n  default: openai-codex/gpt-6-astra\n"),
            "openai-codex/gpt-6-astra")
        self.assertEqual(audit.pin_review_effort("openai-codex/gpt-6-luna:auto"), "openai-codex/gpt-6-luna:low")
        self.assertEqual(audit.pin_review_effort("openai-codex/gpt-6-luna"), "openai-codex/gpt-6-luna:low")
        self.assertEqual(audit.pin_review_effort("openai-codex/gpt-6-luna:high"), "openai-codex/gpt-6-luna:high")
        with self.assertRaises(audit.Hold):
            audit.resolve_review_model("modelRoles:\n  task: openai-codex/gpt-5.6-luna:xhigh\n")


class DependencyGateTests(unittest.TestCase):
    def test_package_own_version_is_not_external_dependency_evidence(self):
        before = {"name": "public-project", "version": "1.0.0", "dependencies": {"external": "1.2.3"}}
        after = {**before, "version": "1.0.1"}
        identity = lambda value: audit.dependency_identity("package.json", json.dumps(value).encode())
        self.assertTrue(audit.same_identity(identity(before), identity(after)))
        for field in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
            changed = {**after, field: {"external": "9.9.9"}}
            with self.subTest(field=field):
                self.assertFalse(audit.same_identity(identity(before), identity(changed)))

    def test_bun_workspace_versions_do_not_hide_external_integrity_changes(self):
        before = b'{"workspaces":{"":{"name":"omp","version":"1.0.0",},},"packages":{"external":["external@1.0","sha512-one"],},}'
        version_only = before.replace(b'"version":"1.0.0"', b'"version":"1.0.1"')
        external_change = version_only.replace(b"sha512-one", b"sha512-two")
        original = audit.dependency_identity("bun.lock", before)
        self.assertTrue(audit.same_identity(original, audit.dependency_identity("bun.lock", version_only)))
        self.assertFalse(audit.same_identity(original, audit.dependency_identity("bun.lock", external_change)))
        self.assertEqual(audit.json_with_trailing_commas('{"literal":",}",}')["literal"], ",}")
        with self.assertRaises(audit.Hold):
            audit.dependency_identity("bun.lock", b'{/* opaque */"workspaces":{},"packages":{}}')

    def test_cargo_target_dependencies_and_external_lock_identities_are_checked(self):
        manifest = b'[package]\nname="local"\nversion="1.0.0"\n[target.linux.dependencies]\nexternal="1.0"\n'
        original = audit.dependency_identity("Cargo.toml", manifest)
        self.assertTrue(audit.same_identity(original, audit.dependency_identity("Cargo.toml", manifest.replace(b'1.0.0', b'1.0.1'))))
        self.assertFalse(audit.same_identity(original, audit.dependency_identity("Cargo.toml", manifest.replace(b'external="1.0"', b'external="2.0"'))))
        lock = b'version=4\n[[package]]\nname="local"\nversion="1.0.0"\n[[package]]\nname="external"\nversion="2.0"\nsource="registry+https://example.org"\nchecksum="one"\n'
        original = audit.dependency_identity("Cargo.lock", lock)
        self.assertTrue(audit.same_identity(original, audit.dependency_identity("Cargo.lock", lock.replace(b'1.0.0', b'1.0.1'))))
        self.assertFalse(audit.same_identity(original, audit.dependency_identity("Cargo.lock", lock.replace(b'checksum="one"', b'checksum="two"'))))

    def test_changed_dependency_and_opaque_lock_hold_without_model_judgment(self):
        def git_objects(*args, **kwargs):
            if args[0] == "ls-tree":
                oid = BASE["commit"] if args[3] == BASE["commit"] else "e" * 40
                return f"100644 blob {oid}\t{args[-1]}\0".encode()
            value = "1.0" if args[2] == BASE["commit"] else "2.0"
            return json.dumps({"dependencies": {"external": value}}).encode()
        with mock.patch.object(audit, "git", side_effect=git_objects), mock.patch.object(audit, "dependency_reviews", return_value=[]):
            risks, cleared = audit.dependency_risks(BASE, {"commit": "e" * 40, "version": "18.1.14"}, ["package.json", "pnpm-lock.yaml"])
        self.assertEqual(len(risks), 2)
        self.assertEqual(cleared, [])


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state = Path(self.temporary.name)
        self.real = self.state / "omp-real"
        self.real.write_bytes(b"x" * audit.MIN_ASSET)
        for key, value in (("STATE", self.state), ("REAL", self.real)):
            patcher = mock.patch.object(audit, key, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        audit.save_source_baseline(BASE["version"], BASE["commit"], "user-accepted", "test", "Explicit fixture trust")
        # Tree inventory needs a real git repository; these tests exercise the flow around it.
        patcher = mock.patch.object(audit, "capability_plan", return_value=([], collections.defaultdict(list)))
        patcher.start()
        self.addCleanup(patcher.stop)


    def test_large_json_and_small_code_change_reach_model_review(self):
        before = b'{"padding":"' + b'a' * (1024 * 1024 + 1) + b'","route":"old"}'
        after = before.replace(b'"route":"old"', b'"route":"new"')
        raw_json_patch = "diff --git a/catalog.json b/catalog.json\n+" + "x" * (audit.MAX_SOURCE + 1) + "\n"
        code_patch = DIFF
        with mock.patch.object(audit, "manifest_blob", side_effect=lambda commit, path, limit:
                               before if commit == BASE["commit"] else after):
            compacted_json = audit.compact_large_json_patches(
                raw_json_patch, {"commit": BASE["commit"]}, {"commit": "e" * 40})
        complete = compacted_json + code_patch

        def review(source, chunk_id, *args, **kwargs):
            value = verdict(chunk_id=chunk_id, source_sha256=hashlib.sha256(source.encode()).hexdigest())
            if kwargs.get("coherence"):
                value["resolved_concerns"] = value["resolved_capabilities"] = []
            return value

        with mock.patch.object(audit, "installed_manifest", return_value=BASE), \
             mock.patch.object(audit, "api_json", return_value=release()), \
             mock.patch.object(audit, "tag_commit", return_value="e" * 40), \
             mock.patch.object(audit, "source_diff", return_value=(complete, ["catalog.json", "example.py"])), \
             mock.patch.object(audit, "dependency_risks", return_value=([], [])), \
             mock.patch.object(audit, "review_chunk", side_effect=review) as model, \
             mock.patch.object(audit, "stage_asset"):
            report = audit.now_report()
            audit.audit_release(report)
        self.assertEqual(report["status"], "APPROVED")
        self.assertEqual(model.call_count, 2)
        self.assertIn("semantic-json-diff", model.call_args_list[0].args[0])
    def test_lightweight_release_stages_exact_asset_without_source_review(self):
        report = audit.now_report()
        with mock.patch.object(audit, "installed_manifest", return_value=BASE), \
             mock.patch.object(audit, "api_json", return_value=release()), \
             mock.patch.object(audit, "tag_commit", return_value="e" * 40), \
             mock.patch.object(audit, "verify_binary_signature", return_value="test-team") as signature, \
             mock.patch.object(audit, "stage_asset") as stage, \
             mock.patch.object(audit, "source_diff") as source:
            audit.lightweight_release(report)
        self.assertEqual(report["status"], "APPROVED")
        stage.assert_called_once()
        signature.assert_called_once_with(self.real)
        source.assert_not_called()
        self.assertTrue((self.state / "approved.json").exists())

    def test_check_defaults_lightweight_and_strict_is_opt_in(self):
        def pass_light(report):
            report.update(status="CURRENT", version=BASE["version"], summary="light")
        def pass_strict(report):
            report.update(status="CURRENT", version=BASE["version"], summary="strict")
        with mock.patch.object(audit, "lightweight_release", side_effect=pass_light) as light, \
             mock.patch.object(audit, "audit_release", side_effect=pass_strict) as strict:
            self.assertEqual(audit.check(force=True), 0)
            self.assertEqual(audit.check(force=True, strict=True), 0)
        light.assert_called_once()
        strict.assert_called_once()

    def test_background_lightweight_check_preserves_strict_hold(self):
        held = audit.now_report()
        held.update(status="HOLD", review_mode="strict", version="18.3.0",
                    summary="Whole-release review identified new risks")
        audit.persist_report(held)
        (self.state / "approved.json").write_text("{}")
        (self.state / "candidate").write_bytes(b"candidate")
        with mock.patch.object(audit, "lightweight_release") as light:
            self.assertEqual(audit.check(force=True), 0)
        light.assert_not_called()
        self.assertEqual(json.loads((self.state / "report.json").read_text()), held)
        self.assertFalse((self.state / "approved.json").exists())
        self.assertFalse((self.state / "candidate").exists())

    def test_overflowed_strict_hold_survives_background_check(self):
        held = audit.now_report()
        held.update(status="HOLD", review_mode="strict", version="18.3.0", risks=["x" * 4096])
        with mock.patch.object(audit, "MAX_JSON", 2048):
            self.assertFalse(audit.persist_report(held))
            self.assertEqual(held["review_mode"], "strict")
            with mock.patch.object(audit, "lightweight_release") as light:
                self.assertEqual(audit.check(force=True), 0)
            light.assert_not_called()
        self.assertEqual(json.loads((self.state / "report.json").read_text())["status"], "HOLD")

    def test_overflow_keeps_user_accepted_findings_pointer(self):
        accepted = {"basis": "user-accepted", "target": {"version": BASE["version"]},
                    "report_sha256": "a" * 64, "findings": ["x" * 5000]}
        archive = self.state / "evidence" / BASE["version"] / f"acceptance-{'a' * 64}.json"
        archive.parent.mkdir(parents=True)
        archive.write_text(json.dumps(accepted))
        report = audit.now_report()
        report.update(status="CURRENT", review_mode="lightweight", installed_version=BASE["version"],
                      installed_acceptance=accepted, baseline_risks=audit.BASELINE + accepted["findings"])
        with mock.patch.object(audit, "MAX_JSON", 4096):
            self.assertFalse(audit.persist_report(report))
            compact = json.loads((self.state / "report.json").read_text())
            self.assertEqual(compact["installed_acceptance"]["report_sha256"], "a" * 64)
            self.assertEqual(compact["installed_acceptance"]["findings_path"], str(archive))
            self.assertIn("full findings", compact["baseline_risks"][-1])
            def current(next_report):
                next_report.update(status="CURRENT", version=BASE["version"],
                                   installed_version=BASE["version"], summary="Artifact current")
            with mock.patch.object(audit, "audit_release", side_effect=current), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(audit.check(force=True, strict=True), 0)
        value = json.loads((self.state / "report.json").read_text())
        self.assertEqual(value["installed_acceptance"]["report_sha256"], "a" * 64)
        self.assertIn("full findings", value["baseline_risks"][-1])

    def test_pre_review_overflow_never_runs_auditor(self):
        accepted = {"basis": "user-accepted", "target": {"version": BASE["version"]},
                    "report_sha256": "a" * 64, "findings": ["x" * 3000]}
        previous = audit.now_report()
        previous.update(status="INSTALLED", review_mode="strict", version=BASE["version"],
                        installed_version=BASE["version"], acceptance=accepted)
        with mock.patch.object(audit, "MAX_JSON", 6144):
            self.assertTrue(audit.persist_report(previous))
            with mock.patch.object(audit, "audit_release") as release, self.assertRaises(audit.Hold):
                audit.check(force=True, strict=True)
            release.assert_not_called()
        compact = json.loads((self.state / "report.json").read_text())
        self.assertEqual(compact["status"], "HOLD")
        self.assertEqual(compact["installed_acceptance"]["report_sha256"], "a" * 64)

    def test_lightweight_current_keeps_user_accepted_installed_risks(self):
        accepted = {"basis": "user-accepted", "target": {"version": BASE["version"]},
                    "findings": ["Conditional outbound credential disclosure"]}
        installed = audit.now_report()
        installed.update(status="INSTALLED", review_mode="strict", version=BASE["version"],
                         risks=accepted["findings"], acceptance=accepted)
        audit.persist_report(installed)
        def current(report):
            report.update(status="CURRENT", version=BASE["version"],
                          installed_version=BASE["version"], summary="Artifact current")
        with mock.patch.object(audit, "lightweight_release", side_effect=current), \
             contextlib.redirect_stdout(io.StringIO()):
            for _ in range(2):
                self.assertEqual(audit.check(force=True), 0)
                value = json.loads((self.state / "report.json").read_text())
                self.assertEqual(value["installed_acceptance"], accepted)
                self.assertIn("User-accepted 18.1.13: Conditional outbound credential disclosure",
                              value["baseline_risks"])

        def newer(report):
            report.update(status="APPROVED", version="18.1.14",
                          installed_version=BASE["version"], summary="New artifact")
        with mock.patch.object(audit, "lightweight_release", side_effect=newer), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(audit.check(force=True), 0)
        value = json.loads((self.state / "report.json").read_text())
        self.assertEqual(value["version"], "18.1.14")
        self.assertIn("User-accepted 18.1.13: Conditional outbound credential disclosure",
                      value["baseline_risks"])
        with mock.patch.object(audit, "audit_release", side_effect=current), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(audit.check(force=True, strict=True), 0)
        value = json.loads((self.state / "report.json").read_text())
        self.assertEqual(value["installed_acceptance"], accepted)
        self.assertIn("User-accepted 18.1.13: Conditional outbound credential disclosure",
                      value["baseline_risks"])
        def held_newer(report):
            report.update(status="HOLD", version="18.1.14", installed_version=BASE["version"],
                          summary="New source risk", risks=["New release risk"])
        with mock.patch.object(audit, "audit_release", side_effect=held_newer), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(audit.check(force=True, strict=True), 1)
        value = json.loads((self.state / "report.json").read_text())
        self.assertEqual(value["risks"], ["New release risk"])
        self.assertEqual(value["installed_acceptance"], accepted)
        self.assertIn("User-accepted 18.1.13: Conditional outbound credential disclosure",
                      value["baseline_risks"])
        with mock.patch.object(audit, "audit_release", side_effect=current), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(audit.check(force=True, strict=True), 0)
        self.assertEqual(json.loads((self.state / "report.json").read_text())["installed_acceptance"], accepted)
        with mock.patch.object(audit, "audit_release", side_effect=newer), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(audit.check(force=True, strict=True), 0)
        value = json.loads((self.state / "report.json").read_text())
        self.assertEqual(value["status"], "APPROVED")
        self.assertIn("User-accepted 18.1.13: Conditional outbound credential disclosure",
                      value["baseline_risks"])

    def test_interrupted_check_keeps_acceptance_and_retries(self):
        accepted = {"basis": "user-accepted", "target": {"version": BASE["version"]},
                    "findings": ["Accepted outbound risk"]}
        previous = audit.now_report()
        previous.update(status="INSTALLED", review_mode="strict", version=BASE["version"],
                        installed_version=BASE["version"], acceptance=accepted)
        audit.persist_report(previous)
        def interrupt(_):
            raise KeyboardInterrupt()
        with mock.patch.object(audit, "audit_release", side_effect=interrupt), \
             self.assertRaises(KeyboardInterrupt):
            audit.check(force=True, strict=True)
        checking = json.loads((self.state / "report.json").read_text())
        self.assertEqual(checking["status"], "CHECKING")
        self.assertEqual(checking["installed_acceptance"], accepted)
        self.assertIn("User-accepted 18.1.13: Accepted outbound risk", checking["baseline_risks"])

        def current(report):
            report.update(status="CURRENT", version=BASE["version"],
                          installed_version=BASE["version"], summary="Artifact current")
        with mock.patch.object(audit, "audit_release", side_effect=current) as run, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(audit.check(strict=True), 0)
        run.assert_called_once()
        self.assertEqual(json.loads((self.state / "report.json").read_text())["installed_acceptance"], accepted)

    def test_lightweight_signature_check_rejects_signer_change(self):
        ok = mock.Mock(returncode=0, stderr="", stdout="")
        trusted = mock.Mock(returncode=0, stderr="TeamIdentifier=trusted\n", stdout="")
        other = mock.Mock(returncode=0, stderr="TeamIdentifier=other\n", stdout="")
        with mock.patch.object(audit.platform, "system", return_value="Darwin"), \
             mock.patch.object(audit.subprocess, "run", side_effect=[ok, trusted, ok, other]):
            with self.assertRaises(audit.Hold):
                audit.verify_binary_signature(self.real)

    def test_source_trust_can_advance_without_installing_binary(self):
        target = {"version": "18.1.21", "commit": "e" * 40}
        accepted = audit.save_source_baseline("18.1.20", "d" * 40, "user-accepted", "test", "Community trust")
        self.assertEqual(audit.accepted_source(BASE, target), accepted)
        self.assertNotEqual(accepted["commit"], BASE["commit"])

    def test_oversized_ledger_preserves_previous_readable_records(self):
        original = (self.state / "accepted-source.json").read_bytes()
        with mock.patch.object(audit, "MAX_LEDGER", len(original)), self.assertRaises(audit.Hold):
            audit.save_source_baseline("18.1.20", "d" * 40, "user-accepted", "test", "x" * 4096)
        self.assertEqual((self.state / "accepted-source.json").read_bytes(), original)
        self.assertEqual(len(audit.source_baselines()), 1)

    def test_source_selection_excludes_target_and_rejects_ambiguity(self):
        target = {"version": "18.1.21", "commit": "e" * 40}
        audit.save_source_baseline("18.1.21", "e" * 40, "user-accepted", "test", "")
        self.assertEqual(audit.accepted_source(BASE, target)["commit"], BASE["commit"])
        audit.save_source_baseline(BASE["version"], "f" * 40, "user-accepted", "test", "")
        with self.assertRaises(audit.Hold):
            audit.accepted_source(BASE, target)

    def test_dependency_review_requires_exact_identity(self):
        target = {"version": "18.1.21", "commit": "e" * 40}
        entry = {"path": "bun.lock", "base_commit": BASE["commit"], "target_commit": target["commit"],
                 "target_version": target["version"], "before_sha256": "a" * 64, "after_sha256": "b" * 64}
        self.assertEqual(audit.matching_review([entry], "bun.lock", BASE["commit"], target, "a" * 64, "b" * 64), entry)
        self.assertIsNone(audit.matching_review([entry], "bun.lock", BASE["commit"], target, "a" * 64, "c" * 64))
        self.assertIsNone(audit.matching_review([entry], "bun.lock", BASE["commit"], {**target, "commit": "f" * 40}, "a" * 64, "b" * 64))

    def test_unchanged_version_checks_identity_without_review_or_download(self):
        metadata = release(BASE["version"], BASE["sha256"])
        report = audit.now_report()
        with mock.patch.object(audit, "installed_manifest", return_value=BASE), \
             mock.patch.object(audit, "api_json", return_value=metadata), \
             mock.patch.object(audit, "tag_commit", return_value=BASE["commit"]), \
             mock.patch.object(audit, "source_diff") as source, \
             mock.patch.object(audit, "review_chunk") as review, \
             mock.patch.object(audit, "stage_asset") as download:
            audit.audit_release(report)
        self.assertEqual(report["status"], "CURRENT")
        source.assert_not_called()
        review.assert_not_called()
        download.assert_not_called()
        self.assertFalse((self.state / "approved.json").exists())

    def test_replaced_same_version_is_held(self):
        for digest, commit in (("f" * 64, BASE["commit"]), (BASE["sha256"], "f" * 40)):
            with self.subTest(digest=digest, commit=commit), \
                 mock.patch.object(audit, "installed_manifest", return_value=BASE), \
                 mock.patch.object(audit, "api_json", return_value=release(BASE["version"], digest)), \
                 mock.patch.object(audit, "tag_commit", return_value=commit), self.assertRaises(audit.Hold):
                audit.audit_release(audit.now_report())

    def test_model_risks_hold_download_but_retain_feature_report(self):
        report = audit.now_report()
        risky = verdict(risks=["example.py:1 untrusted code execution"], features=["Public example feature"])
        with mock.patch.object(audit, "installed_manifest", return_value=BASE), \
             mock.patch.object(audit, "api_json", return_value=release()), \
             mock.patch.object(audit, "tag_commit", return_value="e" * 40), \
             mock.patch.object(audit, "source_diff", return_value=(DIFF, ["example.py"])), \
             mock.patch.object(audit, "review_chunk", return_value=risky), \
             mock.patch.object(audit, "stage_asset") as download:
            with self.assertRaises(audit.Hold):
                audit.audit_release(report)
        download.assert_not_called()
        self.assertIn("Public example feature", report["features"])
        self.assertIn("example.py:1 untrusted code execution", report["risks"])
        self.assertFalse((self.state / "approved.json").exists())

    def test_asset_hash_mismatch_never_publishes_candidate(self):
        content = b"untrusted binary bytes"
        response = io.BytesIO(content)
        response.headers = {"Content-Length": str(len(content))}
        target = {"asset_url": f"https://github.com/can1357/oh-my-pi/releases/download/v18.1.14/{audit.ASSET}",
                  "size": len(content), "sha256": "0" * 64}
        with mock.patch.object(audit, "open_public", return_value=response), self.assertRaises(audit.Hold):
            audit.stage_asset(target)
        self.assertFalse((self.state / "candidate").exists())
        self.assertFalse((self.state / "approved.json").exists())

    def test_signature_mismatch_never_publishes_candidate(self):
        content = b"candidate bytes"
        response = io.BytesIO(content)
        response.headers = {"Content-Length": str(len(content))}
        target = {"asset_url": f"https://github.com/can1357/oh-my-pi/releases/download/v18.1.14/{audit.ASSET}",
                  "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        with mock.patch.object(audit, "open_public", return_value=response), \
             mock.patch.object(audit, "verify_binary_signature", side_effect=audit.Hold("bad signer")):
            with self.assertRaises(audit.Hold):
                audit.stage_asset(target)
        self.assertFalse((self.state / "candidate").exists())
        self.assertFalse((self.state / "approved.json").exists())

    def test_error_report_is_daily_and_force_does_not_weaken_gate(self):
        (self.state / "approved.json").write_text("stale approval")
        (self.state / "candidate").write_bytes(b"stale candidate")
        with mock.patch.object(audit, "audit_release", side_effect=audit.Hold("Missing public source evidence")) as run, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(audit.check(strict=True), 1)
            self.assertEqual(audit.check(strict=True), 0)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(audit.check(force=True, strict=True), 1)
            self.assertEqual(run.call_count, 2)
        report = json.loads((self.state / "report.json").read_text())
        self.assertEqual(report["status"], "HOLD")
        self.assertIn("Missing public source evidence", report["risks"])
        self.assertFalse((self.state / "approved.json").exists())
        self.assertFalse((self.state / "candidate").exists())

    def test_complete_chunk_questions_reach_final_review_but_final_hold_blocks(self):
        complete = DIFF + DIFF.replace("example.py", "second.py")
        report = audit.now_report()
        def review(source, chunk_id, inventory, notes, identities, evidence, **kwargs):
            if kwargs.get("coherence"):
                self.assertEqual(source, audit.release_ledger("e" * 40, [], complete))
                self.assertEqual(len(kwargs["prior_reviews"]), 2)
                self.assertEqual(len(kwargs["concerns"]), 2)
                self.assertTrue(all(item["verdict"] == "HOLD" for item in kwargs["prior_reviews"]))
                return verdict(chunk_id=chunk_id, verdict="HOLD", risks=["Cross-file credential flow reaches a new endpoint"],
                               source_sha256=hashlib.sha256(source.encode()).hexdigest(), features=["Cross-file feature identified"])
            return verdict(chunk_id=chunk_id, verdict="HOLD", uncertainties=["Caller in another chunk"],
                           source_sha256=hashlib.sha256(source.encode()).hexdigest())
        with mock.patch.object(audit, "installed_manifest", return_value=BASE), \
             mock.patch.object(audit, "api_json", return_value=release()), \
             mock.patch.object(audit, "tag_commit", return_value="e" * 40), \
             mock.patch.object(audit, "source_diff", return_value=(complete, ["example.py", "second.py"])), \
             mock.patch.object(audit, "MAX_CHUNK", len(DIFF.encode()) + 1), \
             mock.patch.object(audit, "review_chunk", side_effect=review), \
             mock.patch.object(audit, "stage_asset") as download:
            with self.assertRaises(audit.Hold):
                audit.audit_release(report)
        download.assert_not_called()
        self.assertIn("Cross-file credential flow reaches a new endpoint", report["risks"])
        self.assertIn("Cross-file feature identified", report["features"])
        self.assertFalse((self.state / "approved.json").exists())

    def test_incomplete_chunk_never_reaches_final_review(self):
        report = audit.now_report()
        with mock.patch.object(audit, "installed_manifest", return_value=BASE), \
             mock.patch.object(audit, "api_json", return_value=release()), \
             mock.patch.object(audit, "tag_commit", return_value="e" * 40), \
             mock.patch.object(audit, "source_diff", return_value=(DIFF, ["example.py"])), \
             mock.patch.object(audit, "review_chunk", return_value=verdict(reviewed=False)) as review, \
             mock.patch.object(audit, "stage_asset") as download:
            with self.assertRaises(audit.Hold):
                audit.audit_release(report)
        self.assertEqual(review.call_count, 1)
        download.assert_not_called()

    def test_whole_review_input_bound_holds_instead_of_truncating_source(self):
        with mock.patch.object(audit, "MAX_WHOLE_INPUT", 128), \
             mock.patch.object(audit, "model_environment") as environment, \
             self.assertRaises(audit.Hold):
            audit.review_chunk(DIFF, "whole-release", ["example.py"], "", {}, self.state,
                               coherence=True, prior_reviews=[verdict()])
        environment.assert_not_called()
        self.assertFalse((self.state / "whole-release.input.txt").exists())
        self.assertFalse((self.state / "approved.json").exists())

    def test_oversized_report_revokes_approval_and_preserves_full_evidence(self):
        report = audit.now_report()
        complete_risks = ["external.py:1 " + "x" * audit.MAX_JSON]
        report.update(status="APPROVED", risks=complete_risks, evidence_path=str(self.state / "evidence"),
                      features=["Useful public feature"], version="v" * audit.MAX_JSON)
        (self.state / "approved.json").write_text("pending")
        (self.state / "candidate").write_bytes(b"candidate")
        self.assertFalse(audit.persist_report(report))
        saved = json.loads((self.state / "report.json").read_text())
        complete = json.loads((self.state / "report-overflow.json").read_text())
        self.assertLessEqual((self.state / "report.json").stat().st_size, audit.MAX_JSON)
        self.assertEqual(saved["status"], "HOLD")
        self.assertIn("Report exceeded bound", saved["uncertainties"][0])
        self.assertEqual(saved["features"], ["Useful public feature"])
        self.assertEqual(complete["risks"], complete_risks)
        self.assertFalse((self.state / "approved.json").exists())
        self.assertFalse((self.state / "candidate").exists())
        self.assertTrue(audit.persist_report(report))

    def test_dependency_gate_holds_before_model_and_keeps_feature_claims(self):
        report = audit.now_report()
        with mock.patch.object(audit, "installed_manifest", return_value=BASE), \
             mock.patch.object(audit, "api_json", return_value=release()), \
             mock.patch.object(audit, "tag_commit", return_value="e" * 40), \
             mock.patch.object(audit, "source_diff", return_value=(DIFF, ["example.py"])), \
             mock.patch.object(audit, "dependency_risks", return_value=(["Cargo.lock: external code missing"], [])), \
             mock.patch.object(audit, "review_chunk") as review, \
             mock.patch.object(audit, "stage_asset") as download:
            with self.assertRaises(audit.Hold):
                audit.audit_release(report)
        review.assert_not_called()
        download.assert_not_called()
        self.assertIn("Cargo.lock: external code missing", report["risks"])
        self.assertTrue(any("Public feature claim" in item for item in report["features"]))
        self.assertFalse((self.state / "approved.json").exists())

    def test_infra_ci_docs_and_tests_are_informational_but_manifests_stay_gated(self):
        informational = ["infra/reload-runner.sh", ".github/workflows/ci.yml", "Dockerfile", "docs/tools/x.md",
                         "packages/cli/test/x.test.ts", "packages/cli/src/y.spec.ts", "packages/cli/CHANGELOG.md"]
        gated = ["example.py", "bun.lock", "packages/cli/src/prompts/system.md", "packages/cli/scripts/build.ts"]
        paths = sorted(informational + gated)
        complete = "".join(DIFF.replace("example.py", path) for path in paths)
        report = audit.now_report()
        with mock.patch.object(audit, "installed_manifest", return_value=BASE), \
             mock.patch.object(audit, "api_json", return_value=release()), \
             mock.patch.object(audit, "tag_commit", return_value="e" * 40), \
             mock.patch.object(audit, "source_diff", return_value=(complete, paths)), \
             mock.patch.object(audit, "dependency_risks", return_value=([], [])) as manifests, \
             mock.patch.object(audit, "review_chunk", return_value=verdict(reviewed=False)) as review, \
             mock.patch.object(audit, "stage_asset"):
            with self.assertRaises(audit.Hold):
                audit.audit_release(report)
        reviewed = review.call_args.args[0]
        self.assertEqual(report["gated_files"], sorted(gated))
        self.assertEqual(report["informational_files"], sorted(informational))
        self.assertEqual(reviewed, "".join(DIFF.replace("example.py", path) for path in sorted(gated)))
        self.assertEqual(review.call_args.args[2], {"gated_files": sorted(gated), "informational_files": sorted(informational)})
        self.assertEqual(manifests.call_args.args[2], paths)
        self.assertEqual(report["changed_files"], paths)

    def test_release_without_shipped_source_changes_holds_instead_of_approving(self):
        with mock.patch.object(audit, "installed_manifest", return_value=BASE), \
             mock.patch.object(audit, "api_json", return_value=release()), \
             mock.patch.object(audit, "tag_commit", return_value="e" * 40), \
             mock.patch.object(audit, "source_diff", return_value=(DIFF.replace("example.py", "docs/a.md"), ["docs/a.md"])), \
             mock.patch.object(audit, "review_chunk") as review, \
             mock.patch.object(audit, "stage_asset") as download, self.assertRaises(audit.Hold):
            audit.audit_release(audit.now_report())
        review.assert_not_called()
        download.assert_not_called()

    def test_diff_headers_that_disagree_with_inventory_hold(self):
        for complete, paths in ((DIFF, ["other.py"]),
                                ("diff --git a/example.py b/renamed.py\n" + DIFF.split("\n", 1)[1], ["example.py"])):
            with self.subTest(paths=paths), \
                 mock.patch.object(audit, "installed_manifest", return_value=BASE), \
                 mock.patch.object(audit, "api_json", return_value=release()), \
                 mock.patch.object(audit, "tag_commit", return_value="e" * 40), \
                 mock.patch.object(audit, "source_diff", return_value=(complete, paths)), \
                 mock.patch.object(audit, "review_chunk") as review, self.assertRaises(audit.Hold):
                audit.audit_release(audit.now_report())
            review.assert_not_called()


class AcceptanceTests(unittest.TestCase):
    setUp = StateTests.setUp
    def held_report(self):
        target = {**audit.release_identity(release()), "commit": "e" * 40}
        chunk = verdict(verdict="HOLD", risks=["example.py:1 changed behavior"])
        whole = verdict(chunk_id="whole-release", verdict="HOLD", risks=["example.py:1 changed behavior"],
                        resolved_concerns=[], resolved_capabilities=[],
                        source_sha256=hashlib.sha256(audit.release_ledger("e" * 40, [], DIFF).encode()).hexdigest())
        report = audit.now_report()
        report.update(status="HOLD", target=target, version=target["version"], reviews=[chunk],
                      coherence_review=whole, diff_sha256=hashlib.sha256(DIFF.encode()).hexdigest(),
                      accepted_source=audit.source_baselines()[0], risks=whole["risks"])
        audit.persist_report(report)
        digest = hashlib.sha256((self.state / "report.json").read_bytes()).hexdigest()
        return target, digest

    def test_changed_or_incomplete_report_never_stages(self):
        target, digest = self.held_report()
        with mock.patch.object(audit, "stage_asset") as stage, self.assertRaises(audit.Hold):
            audit.accept_reviewed(target["version"], target["commit"], target["sha256"], "0" * 64, "accept")
        stage.assert_not_called()
        report = json.loads((self.state / "report.json").read_text())
        report["reviews"][0]["reviewed"] = False
        audit.persist_report(report)
        digest = hashlib.sha256((self.state / "report.json").read_bytes()).hexdigest()
        with mock.patch.object(audit, "installed_manifest", return_value=BASE), \
             mock.patch.object(audit, "source_diff", return_value=(DIFF, ["example.py"])), \
             mock.patch.object(audit, "stage_asset") as stage, self.assertRaises(audit.Hold):
            audit.accept_reviewed(target["version"], target["commit"], target["sha256"], digest, "accept")
        stage.assert_not_called()
        self.assertFalse((self.state / "approved.json").exists())

    def test_explicit_acceptance_preserves_hold_and_binds_artifact(self):
        target, digest = self.held_report()
        with mock.patch.object(audit, "installed_manifest", return_value=BASE), \
             mock.patch.object(audit, "source_diff", return_value=(DIFF, ["example.py"])), \
             mock.patch.object(audit, "dependency_risks", return_value=([], [])), \
             mock.patch.object(audit, "api_json", return_value=release()), \
             mock.patch.object(audit, "tag_commit", return_value=target["commit"]), \
             mock.patch.object(audit, "stage_asset"), contextlib.redirect_stdout(io.StringIO()):
            audit.accept_reviewed(target["version"], target["commit"], target["sha256"], digest, "Explicit user decision")
        approved = json.loads((self.state / "approved.json").read_text())
        self.assertEqual(approved, {**target, "base_sha256": BASE["sha256"]})
        report = json.loads((self.state / "report.json").read_text())
        self.assertEqual(report["coherence_review"]["verdict"], "HOLD")
        self.assertEqual(report["acceptance"]["basis"], "user-accepted")
        self.assertEqual(report["acceptance"]["report_sha256"], digest)
        self.assertEqual(audit.source_baselines()[-1]["basis"], "user-accepted")

    def test_acceptance_recomputes_the_scoped_source_digest(self):
        target, _ = self.held_report()
        informational = DIFF.replace("example.py", "docs/ignored.md")
        complete = informational + DIFF
        report = json.loads((self.state / "report.json").read_text())
        report.update(diff_sha256=hashlib.sha256(DIFF.encode()).hexdigest(),
                      gated_files=["example.py"], informational_files=["docs/ignored.md"])
        audit.persist_report(report)
        digest = hashlib.sha256((self.state / "report.json").read_bytes()).hexdigest()
        with mock.patch.object(audit, "installed_manifest", return_value=BASE), \
             mock.patch.object(audit, "source_diff", return_value=(complete, ["docs/ignored.md", "example.py"])), \
             mock.patch.object(audit, "dependency_risks", return_value=([], [])), \
             mock.patch.object(audit, "api_json", return_value=release()), \
             mock.patch.object(audit, "tag_commit", return_value=target["commit"]), \
             mock.patch.object(audit, "stage_asset"), contextlib.redirect_stdout(io.StringIO()):
            audit.accept_reviewed(target["version"], target["commit"], target["sha256"], digest, "Accept scoped report")
        self.assertTrue((self.state / "approved.json").exists())


class ReviewReuseTests(unittest.TestCase):
    setUp = StateTests.setUp

    @contextlib.contextmanager
    def environment(self):
        yield self.state, {}, "openai-codex/gpt-6-astra:medium"

    def test_exact_input_reuses_review_but_policy_and_source_changes_do_not(self):
        with mock.patch.object(audit, "model_environment", self.environment), \
             mock.patch.object(audit, "run_bounded", return_value=model_stream()) as run:
            args = (DIFF, "chunk-001-of-001", ["example.py"], "", {}, self.state)
            audit.review_chunk(*args)
            audit.review_chunk(*args)
            self.assertEqual(run.call_count, 1)
            with mock.patch.object(audit, "SYSTEM", audit.SYSTEM + "\nStricter policy"):
                audit.review_chunk(*args)
            self.assertEqual(run.call_count, 2)
            with mock.patch.object(audit, "REUSE_REVIEWS", False):
                audit.review_chunk(*args)
            self.assertEqual(run.call_count, 3)
            changed = DIFF.replace("x = 2", "x = 3")
            changed_verdict = verdict(source_sha256=hashlib.sha256(changed.encode()).hexdigest())
            stream = model_stream(content=[{"type": "text", "text": json.dumps(changed_verdict)}])
            run.return_value = stream
            audit.review_chunk(changed, *args[1:])
            self.assertEqual(run.call_count, 4)

    def test_incomplete_reviews_are_not_reused(self):
        stream = model_stream(content=[{"type": "text", "text": json.dumps(verdict(reviewed=False))}])
        with mock.patch.object(audit, "model_environment", self.environment), \
             mock.patch.object(audit, "run_bounded", return_value=stream) as run:
            for _ in range(2):
                audit.review_chunk(DIFF, "chunk-001-of-001", [], "", {}, self.state)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(list((self.state / "review-cache").iterdir()), [])


    def test_model_smoke_checks_live_model_even_after_success(self):
        def respond(*args):
            prompt = json.loads(args[-1])
            answer = verdict(chunk_id=prompt["chunk_id"], source_sha256=prompt["source_sha256"])
            return model_stream(content=[{"type": "text", "text": json.dumps(answer)}])
        with mock.patch.object(audit, "installed_manifest", return_value=BASE), \
             mock.patch.object(audit, "model_environment", self.environment), \
             mock.patch.object(audit, "run_bounded", side_effect=respond) as run, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(audit.model_smoke(), 0)
            run.side_effect = audit.Hold("Provider unavailable")
            self.assertEqual(audit.model_smoke(), 1)
        self.assertEqual(run.call_count, 2)

    def test_pinned_current_release_avoids_model_and_uses_exact_endpoint(self):
        report = audit.now_report()
        report["requested_version"] = BASE["version"]
        with mock.patch.object(audit, "installed_manifest", return_value=BASE), \
             mock.patch.object(audit, "api_json", return_value=release(BASE["version"], BASE["sha256"])) as api, \
             mock.patch.object(audit, "tag_commit", return_value=BASE["commit"]), \
             mock.patch.object(audit, "review_chunk") as review:
            audit.audit_release(report)
        api.assert_called_once_with(f"/releases/tags/v{BASE['version']}")
        review.assert_not_called()
        self.assertEqual(report["status"], "CURRENT")


class ContextReuseTests(unittest.TestCase):
    setUp = StateTests.setUp
    environment = ReviewReuseTests.environment

    def test_supplemental_context_invalidates_only_matching_final_review(self):
        stream = model_stream(content=[{"type": "text", "text": json.dumps(
            verdict(chunk_id="whole-release", resolved_concerns=[], resolved_capabilities=[]))}])
        args = (DIFF, "whole-release", ["example.py"], "", {}, self.state)
        first = [{"path": "helper.py", "commit": "e" * 40, "source": "value = 1"}]
        second = [{"path": "helper.py", "commit": "e" * 40, "source": "value = 2"}]
        with mock.patch.object(audit, "model_environment", self.environment), \
             mock.patch.object(audit, "run_bounded", return_value=stream) as run:
            for context in (first, first, second):
                audit.review_chunk(*args, coherence=True, prior_reviews=[verdict()], context_files=context)
        self.assertEqual(run.call_count, 2)
        payload = json.loads((self.state / "whole-release.input.txt").read_text())
        self.assertEqual(payload["untrusted_context_files"], second)


class EvidenceGateTests(unittest.TestCase):
    def test_every_assigned_capability_needs_an_acknowledgement(self):
        good = verdict(capability_facts=[{"id": "host:new.example", "assessment": "Docs link, never fetched"}])
        audit.parse_verdict(json.dumps(good), good["chunk_id"], good["source_sha256"], capability_ids=["host:new.example"])
        for facts in ([], [{"id": "host:other.example", "assessment": "x"}], good["capability_facts"] * 2):
            with self.subTest(facts=facts), self.assertRaises(audit.Hold):
                audit.parse_verdict(json.dumps(verdict(capability_facts=facts)), good["chunk_id"], good["source_sha256"],
                                    capability_ids=["host:new.example"])
        whole = verdict(chunk_id="whole-release", resolved_concerns=[], resolved_capabilities=[])
        with self.assertRaises(audit.Hold):
            audit.parse_verdict(json.dumps(whole), "whole-release", whole["source_sha256"], [], ["host:new.example"])

    def test_model_tool_use_holds(self):
        stream = ('{"type":"tool_execution_start"}\n'.encode() + model_stream())
        with self.assertRaises(audit.Hold):
            audit.completion_text(stream, "openai-codex/gpt-6-astra")

    def test_known_process_api_in_a_new_file_is_a_capability_change(self):
        before = {"exec": {"spawn": ["a.ts:1"]}, "host": {"x.example": ["a.ts:2"]}}
        after = {"exec": {"spawn": ["a.ts:1", "b.ts:9"]}, "host": {"x.example": ["a.ts:2", "b.ts:3"]}}
        self.assertEqual([item["id"] for item in audit.inventory_delta(before, after)], ["exec:spawn@b.ts"])

    def test_executable_or_undecodable_binary_holds(self):
        for data in (b"\x7fELF" + b"\0" * 12, b"UTOK1\n" + b"\0" * 4 + b"\x7fELF", b"MZ" + b"\0" * 10):
            with self.subTest(data=data), self.assertRaises(audit.Hold):
                audit.binary_facts(data, "tokens.bin")
        with self.assertRaises(audit.Hold):
            audit.binary_facts(b"not zstd", "tokens.zst")

    def test_oversized_hunk_splits_at_lines_without_loss(self):
        patch = "diff --git a/big.txt b/big.txt\n--- /dev/null\n+++ b/big.txt\n@@ -0,0 +1,40 @@\n" + "".join(
            f"+line {n:03d} {'x' * 20}\n" for n in range(40))
        with mock.patch.object(audit, "MAX_CHUNK", 200):
            chunks = audit.split_diff(patch)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.startswith("continued-diff a/big.txt b/big.txt\n") for chunk in chunks[1:]))
        with mock.patch.object(audit, "MAX_CHUNK", 200), self.assertRaises(audit.Hold):
            audit.split_diff(patch.replace("+line 005", "+" + "y" * 300))

    def test_module_bazel_accepts_in_repo_rules_but_not_new_modules(self):
        before = '"""oh-my-pi docs"""\nmodule(name = "oh-my-pi")\nbazel_dep(name = "platforms", version = "1.1.0")\n'
        after = ('"""omp docs"""\nmodule(name = "omp")\nbazel_dep(name = "platforms", version = "1.1.0")\n'
                 'probe = use_repo_rule("//bazel:probe.bzl", "probe_repository")\nprobe(name = "probe")\n')
        self.assertTrue(audit.module_bazel_safe(before, after))
        for added in ('bazel_dep(name = "evil", version = "1.0")\n', 'x = use_repo_rule("@evil//:r.bzl", "r")\n',
                      'other(name = "x")\n'):
            with self.subTest(added=added), self.assertRaises(audit.Hold):
                audit.module_bazel_safe(before, after + added)

    def test_dependency_packages_hold_on_digest_mismatch_and_changed_binaries(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.side_effect = [b"payload", b""]
        with mock.patch.object(audit, "open_public", return_value=response), self.assertRaises(audit.Hold):
            audit.fetch_package("https://static.crates.io/crates/a/a-1.crate", "sha256", "0" * 64)
        self.assertIn("+new\n", audit.package_patches("crates/a", {"src/lib.rs": b"old\n"}, {"src/lib.rs": b"new\n"})[0])
        with self.assertRaises(audit.Hold):
            audit.package_patches("crates/a", {"blob": b"\0a"}, {"blob": b"\0b"})
        with self.assertRaises(audit.Hold):
            audit.crates_io_packages(b'[[package]]\nname = "a"\nversion = "1"\nsource = "git+https://evil/a"\n')
        with self.assertRaises(audit.Hold):
            audit.public_url("https://evil.example/a.crate", "package")

    def test_bazel_lock_accepts_rename_only_and_holds_on_foreign_archive(self):
        def spec(url="https://static.crates.io/crates/a/1.0.0/download", build="# bazel mod show_repo 'oh-my-pi'\n"):
            return {"repoRuleId": audit.HTTP_ARCHIVE, "attributes": {
                "build_file_content": build, "remote_patch_strip": 0, "sha256": "1" * 64,
                "strip_prefix": "a-1.0.0", "type": "tar.gz", "urls": [url]}}
        def lock(crate, contents=None):
            return {"lockFileVersion": 1, "moduleExtensions": {audit.CRATE_EXTENSION: {"general": {
                "bzlTransitiveDigest": "d", "usagesDigest": "u", "recordedInputs": [],
                "generatedRepoSpecs": {"crates": {"repoRuleId": "hub", "attributes": {"contents": contents or {}}},
                                       "crates__a-1.0.0": crate}}}}}
        renamed = spec(build="# bazel mod show_repo 'omp'\n")
        foreign = spec(url="https://evil.example/crates/a/1.0.0/download")
        cargo = b'[[package]]\nname = "local"\nversion = "1.0.0"\n'
        def blobs(after):
            data = {("base", audit.BAZEL_LOCK): json.dumps(lock(spec())).encode(),
                    ("target", audit.BAZEL_LOCK): json.dumps(lock(after)).encode(), ("target", "Cargo.lock"): cargo}
            return lambda commit, path, limit=None: data[(commit, path)]
        with mock.patch.object(audit, "manifest_blob", side_effect=blobs(renamed)):
            patch, new, old = audit.bazel_lock_evidence("base", "target", {audit.BAZEL_LOCK})
        self.assertIn("1 existing crate repositories changed only by the project rename", patch)
        self.assertEqual(new, set())
        with mock.patch.object(audit, "manifest_blob", side_effect=blobs(foreign)), self.assertRaises(audit.Hold):
            audit.bazel_lock_evidence("base", "target", {audit.BAZEL_LOCK})
        old_alias = 'alias(\n    name = "a",\n    actual = "@crates__a-1.0.0//:a",\n)\n'
        new_alias = old_alias.replace("//:a", "//:different")
        before = lock(spec(), {"a/BUILD.bazel": old_alias, "removed/BUILD.bazel": old_alias})
        after = lock(renamed, {"a/BUILD.bazel": new_alias})
        data = {("base", audit.BAZEL_LOCK): json.dumps(before).encode(),
                ("target", audit.BAZEL_LOCK): json.dumps(after).encode(),
                ("target", "Cargo.lock"): cargo}
        with mock.patch.object(audit, "manifest_blob", side_effect=lambda commit, path, limit=None: data[(commit, path)]):
            patch, _, _ = audit.bazel_lock_evidence("base", "target", {audit.BAZEL_LOCK})
        self.assertIn('hub-generated-file a/BUILD.bazel', patch)
        self.assertIn('-    actual = "@crates__a-1.0.0//:a"', patch)
        self.assertIn('+    actual = "@crates__a-1.0.0//:different"', patch)
        self.assertIn('hub-generated-file removed/BUILD.bazel', patch)
        self.assertIn('@crates__a-1.0.0//:different', audit.release_ledger("target", [], patch))
        previous_build = 'deps = ["@crates__a-0.9.0//:a"]\n'
        current_build = 'deps = ["@crates__a-1.0.0//:a"]\n'
        data[("base", audit.BAZEL_LOCK)] = json.dumps(lock(spec(build=previous_build))).encode()
        data[("target", audit.BAZEL_LOCK)] = json.dumps(lock(spec(build=current_build))).encode()
        with mock.patch.object(audit, "manifest_blob", side_effect=lambda commit, path, limit=None: data[(commit, path)]):
            patch, _, _ = audit.bazel_lock_evidence("base", "target", {audit.BAZEL_LOCK})
        self.assertIn('-deps = ["@crates__a-0.9.0//:a"]', patch)
        self.assertIn('+deps = ["@crates__a-1.0.0//:a"]', patch)
        self.assertIn('-deps = ["@crates__a-0.9.0//:a"]',
                      json.loads(audit.release_ledger("target", [], patch))["bazel_lock_evidence"][0])

    def test_changed_manifests_require_matching_changed_lock_entries(self):
        cargo = (b'[[package]]\nname = "local"\nversion = "1.0.0"\n'
                 b'[[package]]\nname = "safe"\nversion = "1.2.3"\n'
                 b'source = "registry+https://github.com/rust-lang/crates.io-index"\n'
                 + b'checksum = "' + b'1' * 64 + b'"\n')
        bun = json.dumps({"workspaces": {"": {"dependencies": {"safe": "1.2.3"}}},
                          "packages": {"safe": ["safe@1.2.3", "", {}, "sha512-" + "a" * 88]}}).encode()
        with mock.patch.object(audit, "manifest_blob", side_effect=lambda commit, path, limit=None:
                               {"Cargo.lock": cargo, "bun.lock": bun}[path]):
            for path, before, after in (
                ("Cargo.toml", b'[dependencies]\nsafe = "1.2.3"\n',
                 b'[dependencies]\nsafe = "1.2.3"\nevil = { git = "https://evil.example/repo" }\n'),
                ("package.json", b'{"dependencies":{"safe":"1.2.3"}}',
                 b'{"dependencies":{"safe":"1.2.3","evil":"1.0.0"}}'),
            ):
                with self.subTest(path=path), self.assertRaises(audit.Hold):
                    audit.dependency_source_reviewed(path, before, after, "base", "target", {path})
                with self.subTest(path=path, changed_lock=True), self.assertRaises(audit.Hold):
                    audit.dependency_source_reviewed(path, before, after, "base", "target",
                                                     {path, "Cargo.lock" if path == "Cargo.toml" else "bun.lock"})
            patched = (b'[dependencies]\nsafe = "1.2.3"\n'
                       b'[patch.crates-io]\nsafe = { git = "https://evil.example/repo" }\n')
            with self.assertRaises(audit.Hold):
                audit.dependency_source_reviewed("Cargo.toml", b'[dependencies]\nsafe = "1.2.3"\n',
                                                 patched, "base", "target", {"Cargo.toml", "Cargo.lock"})
            trusted = b'{"dependencies":{"safe":"1.2.3"},"trustedDependencies":["safe"]}'
            with self.assertRaises(audit.Hold):
                audit.dependency_source_reviewed("package.json", b'{"dependencies":{"safe":"1.2.3"}}',
                                                 trusted, "base", "target", {"package.json", "bun.lock"})
        patched_bun = json.loads(bun)
        patched_bun["patchedDependencies"] = {"safe@1.2.3": "docs/patches/safe.patch"}
        with mock.patch.object(audit, "manifest_blob", return_value=json.dumps(patched_bun).encode()):
            with self.assertRaises(audit.Hold):
                audit.dependency_source_reviewed("bun.lock", bun, json.dumps(patched_bun).encode(),
                                                 "base", "target", {"bun.lock"})


    def test_review_bypasses_found_in_independent_review_hold(self):
        patch = DIFF.replace("example.py", "dependency/npm/a-1/lib/tests/x.js")
        diff, gated, _ = audit.scope_diff(DIFF + patch, ["example.py"])
        self.assertIn("dependency/npm/a-1/lib/tests/x.js", [path for path, _ in gated])
        def tgz(data):
            buffer = io.BytesIO()
            with gzip.GzipFile(fileobj=buffer, mode="wb") as stream:
                stream.write(data)
            return buffer.getvalue()
        member = io.BytesIO()
        with tarfile.open(fileobj=member, mode="w") as archive:
            info = tarfile.TarInfo("package/index.js")
            info.size = 3
            archive.addfile(info, io.BytesIO(b"ok\n"))
        self.assertEqual(audit.package_files(tgz(member.getvalue()), "a"), {"index.js": b"ok\n"})
        with self.assertRaises(audit.Hold):
            audit.package_files(tgz(member.getvalue() + b"hidden payload"), "a")
        with mock.patch.object(audit, "manifest_blob", return_value=None), self.assertRaises(audit.Hold):
            audit.dependency_source_reviewed("package.json", b"{}", b"{}", "base", "target", {"package.json"})
        for line in ('_V = "sha256-abc"', 'url = "https://x.example/a.tgz"', "rctx.download_and_extract(u)"):
            with self.subTest(line=line), self.assertRaises(audit.Hold):
                audit.dependency_source_reviewed("bazel/r.bzl", b"a = 1\n", f"a = 1\n{line}\n".encode(), "b", "t", set())
        self.assertTrue(audit.dependency_source_reviewed("bazel/r.bzl", b"a = 1\n", b"a = 2\n", "b", "t", set()))
        with self.assertRaises(audit.Hold):
            audit.dependency_source_reviewed("infra/r.bzl", b"a = 1\n", b"a = 2\n", "b", "t", set())

    def test_dependency_binary_allowed_only_as_unreferenced_test_fixture(self):
        blob = b"\x80\x02\0pickle"
        patch = audit.package_patches("crates/c-1", {}, {"tests/t.pth": blob, "src/lib.rs": b'//! np.load("t.pth")\nfn a() {}',
                                                           "Makefile": b"t.pth: x", "Cargo.toml": b'path = "tests/t.pth"'})
        self.assertIn("unbuilt-test-fixture", "".join(patch))
        for files in ({"src/t.pth": blob}, {"tests/t.pth": blob, "build.rs": b'include_bytes!("../tests/t.pth")'}):
            with self.subTest(files=list(files)), self.assertRaises(audit.Hold):
                audit.package_patches("crates/c-1", {}, files)

    def test_piwp_prior_parses_completely_or_holds(self):
        import struct

        def piwp(deltas=(0, 1), words=b"a\nb\n", trailer=b""):
            return (b"PIWP" + struct.pack("<5Id", 1, 2, 0, 1, 2, 3.0) + struct.pack("<2f", 1, 2) + b"\x01"
                    + struct.pack("<3I", 2, 2, *deltas[:1]) + struct.pack("<I", deltas[1]) + struct.pack("<2f", 1, 1)
                    + words + trailer)

        self.assertEqual(audit.piwp_table(piwp(), "p")["bigrams"], 2)
        for bad in (piwp(trailer=b"x"), piwp(deltas=(0, 5)), piwp(words=b"b\na\n"), piwp(words=b"a\n\x7fELF\n")):
            with self.subTest(bad=bad[-12:]), self.assertRaises(audit.Hold):
                audit.piwp_table(bad, "p")

    def test_hub_allows_only_workspace_edition_entries(self):
        audit.hub_contents_safe({"crates.bzl": ""}, {"crates.bzl": '    "crates/vendor/brush-parser": "2024",\n'
            '    "crates/vendor/brush-parser": {\n        "cfg(target_os = \\"macos\\")": {\n        },\n        _COMMON_CONDITION: {\n            "bon": Label("//bon-3.10.1"),\n        },\n    },\n'
            '"cfg(windows)": ["@@//bazel/triples:aarch64-pc-windows-msvc","@@//bazel/triples:x86_64-pc-windows-msvc"],'})
        with self.assertRaises(audit.Hold):
            audit.hub_contents_safe({"crates.bzl": ""}, {"crates.bzl": '"cfg(windows)": ["@@//evil:x"],'})
        for line in ('"crates/x": "2024", rctx.execute(["sh"])', '"../x": "2024",', '"crates/x": { "y": run("z") },'):
            with self.subTest(line=line), self.assertRaises(audit.Hold):
                audit.hub_contents_safe({"crates.bzl": ""}, {"crates.bzl": line})

    def test_dev_tooling_native_binary_warns_only_when_unreachable_and_unimported(self):
        lock = json.dumps({"workspaces": {"": {"dependencies": {"app": "1"}, "devDependencies": {"lint": "1"}}},
                           "packages": {"app": ["app@1", "", {"optionalDependencies": {"app-native": "1"}}, "sha512-a"],
                                        "app-native": ["app-native@1", "", {}, "sha512-b"],
                                        "lint": ["lint@1", "", {"optionalDependencies": {"lint-native": "1"}}, "sha512-c"],
                                        "lint-native": ["lint-native@1", "", {}, "sha512-d"]}}).encode()
        self.assertEqual(audit.npm_dev_only(lock), {"lint", "lint-native"})
        binary = {"lint.node": b"\x7fELF\0"}
        patch = audit.package_patches("npm/lint-native-1", {}, binary, lambda: True)
        self.assertIn("WARNING dev-tooling-native-binary", patch[0])
        for dev_only in (None, lambda: False):
            with self.subTest(dev_only=dev_only), self.assertRaises(audit.Hold):
                audit.package_patches("npm/lint-native-1", {}, binary, dev_only)

    def test_vendored_crate_reviewed_as_difference_from_pinned_crate(self):
        base, target = {"commit": "a" * 40}, {"commit": "b" * 40}
        new = "diff --git a/crates/vendor/x/{0} b/crates/vendor/x/{0}\nnew file mode 100644\n+whole file\n"
        blobs = {"src/lib.rs": b"fn a() {}\n", "src/extra.rs": b"fn b() {}\n", "src/parser.c": b"tables\n"}
        crate = ("x", "1.0.0", {"src/lib.rs": b"fn a() {}\n", "src/extra.rs": b"fn c() {}\n"})
        with mock.patch.object(audit, "manifest_blob", lambda commit, path, *_: blobs.get(path.removeprefix("crates/vendor/x/"))), \
                mock.patch.object(audit, "pinned_vendor_crate", return_value=crate), \
                mock.patch.object(audit, "regenerated_grammar", return_value={"src/parser.c": b"tables\n"}):
            crates = {}
            self.assertIn("identical-to-pinned-crate x-1.0.0", audit.vendored_patch(
                "crates/vendor/x/src/lib.rs", new.format("src/lib.rs"), base, target, crates))
            changed = audit.vendored_patch("crates/vendor/x/src/extra.rs", new.format("src/extra.rs"), base, target, crates)
            self.assertIn("-fn c() {}", changed)
            self.assertIn("+fn b() {}", changed)
            self.assertIn("regenerated-by-pinned-tree-sitter-cli", audit.vendored_patch(
                "crates/vendor/x/src/parser.c", new.format("src/parser.c"), base, target, crates))
            crates["crates/vendor/x#grammar"] = {"src/parser.c": b"other\n"}
            patch = new.format("src/parser.c")
            self.assertEqual(audit.vendored_patch("crates/vendor/x/src/parser.c", patch, base, target, crates), patch)


if __name__ == "__main__":
    unittest.main()
