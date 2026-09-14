## Verdict: CAUTION — accepted by user for this release

OMP 18.1.21 is installed. The user explicitly accepted the reviewed behavior changes and remaining uncertainty. The model's HOLD verdict is preserved; no SAFE verdict was fabricated. Acceptance does not apply to future releases.

## Critical findings (accepted for this exact target)

- Hook metadata errors can skip configured hooks instead of failing the commit (`crates/pi-vcs/src/git/mutate.rs:852-854,880-886`). Broadly resembles Git behavior, but changes previous OMP behavior.
- Argument-keyed browser handles can alias one profile/process; kill:true on the owning handle may interrupt another handle (`packages/coding-agent/src/tools/browser/registry.ts:89-114,264-278,390-394`; `attach.ts:228-268`). Static finding, not runtime-reproduced.
- Default persistent browser profiles are executable-keyed, allowing projects using the same OMP profile to share cookies and authenticated state (`packages/coding-agent/src/tools/browser/attach.ts:185-216`; `packages/utils/src/dirs.ts:711-714`).
- All prelude waits suspend the Eval watchdog without a universal handler deadline; a noncooperating handler can remain pending (`packages/coding-agent/src/eval/js/tool-bridge.ts:198-214`; `eval/preludes.ts:111-132`).

## Notable but non-blocking

No malicious supply-chain behavior identified in reviewed source and dependency changes. Eleven dependency archives passed integrity and npm registry signature checks. Full Sigstore chain validation, Bun bundled-dependency runtime resolution, notarization, reproducible builds and trusted source-to-binary attestation remain unestablished. The unchanged Tailwind parent embeds versions differing from bundled-resolution labels; both parent bytes and separately resolved archives were inspected.

Darwin Developer ID signature verification passed: Can Boluk (VTLHGQC72S), hardened runtime. This authenticates the signer, not equivalence to reviewed source. Lock release/watchdog resume use finally; live prelude authorization is rechecked. Remaining caller/permission/runtime assurance gaps were disclosed and accepted.

## What it actually does

The updater separates accepted source from installed binary identity. Exact dependency evidence precedes chunk and complete final review. User exceptions require a completed held report, its exact SHA256, exact release commit and artifact digest, fresh metadata checks, and valid dependency evidence. The complete original report and separate acceptance record persist under release evidence. Activation verifies native platform, size, SHA256, version and native-read smoke, with rollback journaling.

## Evidence and verification

Baseline: 18.1.20 / 1bd60c6fbd0e800a75fd09b1e4804af5a5e6d63b.
Installed: 18.1.21 / a2501722aa05670eeab327ea1325e3fde55e51a9.
Artifact: 135972880 bytes; SHA256 e99a06d5741f13a5e161c88617cde2f5a65d422b2eec0cf1a69aecd093b2462f.
Accepted report SHA256: cffcdc7cda3287623bb3b786e32c3a0a0dbb0a211443f426f690ba70f938b12b.

Machine-local evidence: ~/.local/state/omp-upgrade/evidence/18.1.21/.
- accepted-report-<digest>.json and acceptance-<digest>.json: original HOLD and explicit user decision.
- external-review/: archives, registry metadata/signatures, provenance responses, release metadata, checksums and binary.
- supplemental-source.json and supplemental-review/: 14 full target-commit files and supplemental verdict.
- complete.diff and chunk/final inputs and verdicts.

Managed activation, version/native-read smoke and `omp --version` succeeded (exit 0). Live isolated model-smoke passed after ensuring health checks never use cached verdicts. A pinned current-version check returned CURRENT without model invocation or binary download (exit 0).

## Install recommendation

No further installation needed. For each new release, use the managed auditing-omp-upgrades skill and docs/knowledge/omp.md. Pin `check --version VERSION`; completed exact-input reviews are reusable, while `--context REPO_PATH` supplies missing source from the target commit. `--fresh-reviews` deliberately reruns reviews. Use `accept-reviewed` only after a new explicit user decision; `omp --upgrade-apply` retains activation safeguards. Never bypass the gate or inherit this release's exception.
