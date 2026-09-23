"""Deterministic fail-closed boundary tests; no network or model calls."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

import audit


BASE = {"version": "18.1.13", "commit": "a" * 40, "sha256": "b" * 64}
DIFF = "diff --git a/example.py b/example.py\n--- a/example.py\n+++ b/example.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"


def verdict(**overrides):
    value = {"verdict": "SAFE", "reviewed": True, "chunk_id": "chunk-001-of-001",
             "source_sha256": hashlib.sha256(DIFF.encode()).hexdigest(), "risks": [],
             "breaking_changes": [], "features": ["Changes public example value"], "uncertainties": []}
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
        removed = audit.semantic_json_diff("catalog.json", b'{"rows":[[1]]}', b'{"rows":[]}')
        retained = audit.semantic_json_diff("catalog.json", b'{"rows":[[1]]}', b'{"rows":[[]]}')
        self.assertIn('["remove-container","/k:rows/i:0","array",1]', removed)
        self.assertNotIn('["remove-container","/k:rows/i:0","array",1]', retained)
        self.assertNotEqual(removed, retained)
        self.assertIn('["change","/k:value","#0","#-0"]', audit.semantic_json_diff(
            "catalog.json", b'{"value":0}', b'{"value":-0}'))
        self.assertIn('["change","/k:value","#0.0","#-0.0"]', audit.semantic_json_diff(
            "catalog.json", b'{"value":0.0}', b'{"value":-0.0}'))

    def test_numeric_and_string_keyed_order_remains_type_sensitive(self):
        before = b'[{"id":1},{"id":"1"}]'
        after = b'[{"id":"1"},{"id":1}]'
        patch = audit.semantic_json_diff("catalog.json", before, after)
        self.assertEqual([record["op"] for record in audit.json_diff_records(
            audit.strict_json(before, preserve_numbers=True),
            audit.strict_json(after, preserve_numbers=True))], ["order", "order"])
        records = list(audit.json_order_side((), "value", 0, [audit.JSONNumber("1")] * 2000))
        self.assertTrue(records)
        self.assertTrue(all(len(json.dumps(["order", "", "value", 0, record["items"]],
                                           ensure_ascii=True, separators=(",", ":")).encode()) <= audit.MAX_JSON_RECORD
                            for record in records))
        self.assertIn('["change","/k:value","##literal","##next"]', audit.semantic_json_diff(
            "catalog.json", b'{"value":"#literal"}', b'{"value":"#next"}'))

    def test_oversized_json_blob_is_compacted_with_separate_bound(self):
        before = b'{"padding":"' + b'a' * (1024 * 1024 + 1) + b'","route":"old"}'
        after = before.replace(b'"route":"old"', b'"route":"new"')
        patch = ("diff --git a/catalog.json b/catalog.json\nold mode 100644\nnew mode 100755\n"
                 "index " + "0" * 40 + ".." + "1" * 40 + "\n--- a/catalog.json\n+++ b/catalog.json\n"
                 "@@ -1 +1 @@\n+" + "x" * (audit.MAX_CHUNK + 1) + "\n")

        def blob(commit, path, limit):
            self.assertEqual(limit, audit.MAX_STRUCTURED_JSON)
            return before if commit == "base" else after

        with mock.patch.object(audit, "manifest_blob", side_effect=blob):
            compacted = audit.compact_large_json_patches(patch, {"commit": "base"}, {"commit": "target"})
        self.assertLess(len(compacted.encode()), audit.MAX_CHUNK)
        self.assertIn('["change","/k:route","old","new"]', compacted)
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
        after = json.dumps({"items": [0] * 10000}).encode()
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

    def test_resolve_review_model_prefers_smol_role_then_falls_back_to_default(self):
        self.assertEqual(
            audit.resolve_review_model("modelRoles:\n  smol: openai-codex/gpt-5.6-luna:high\n  default: openai-codex/gpt-6-astra\n"),
            "openai-codex/gpt-5.6-luna:high")
        self.assertEqual(
            audit.resolve_review_model("modelRoles:\n  default: openai-codex/gpt-6-astra\n"),
            "openai-codex/gpt-6-astra")
        self.assertEqual(
            audit.resolve_review_model("modelRoles:\n  smol: openai-codex/gpt-6-luna:auto\n"),
            "openai-codex/gpt-6-luna:auto")
        self.assertEqual(audit.pin_review_effort("openai-codex/gpt-6-luna:auto"),
                         "openai-codex/gpt-6-luna:high")
        self.assertEqual(audit.pin_review_effort("openai-codex/gpt-6-luna"),
                         "openai-codex/gpt-6-luna:high")
        self.assertEqual(audit.pin_review_effort("openai-codex/gpt-6-luna:low"),
                         "openai-codex/gpt-6-luna:low")
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
                value["resolved_concerns"] = []
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
                self.assertEqual(source, complete)
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
                        resolved_concerns=[])
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
            verdict(chunk_id="whole-release", resolved_concerns=[]))}])
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


if __name__ == "__main__":
    unittest.main()
