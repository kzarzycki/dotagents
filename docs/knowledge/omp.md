# omp (oh-my-pi) in dotagents

## What is tracked

| Path | Installs to | Notes |
|---|---|---|
| `home/.omp/agent/config.yml` | `~/.omp/agent/config.yml` | the whole agent config: model roles, compaction, tool approval, display |
| `home/.omp/agent/rules/*.md` | `~/.omp/agent/rules/` | user-scope rules |
| `home/.omp/agent/extensions/*.ts` | `~/.omp/agent/extensions/` | herdr state extension |

Everything else under `~/.omp` is runtime state (sqlite dbs, sessions, logs,
`auth.json`, plugin cache, the 200 MB native binary) — machine-local, gitignored,
never linked.

`marketplaces.json` and `plugins/installed_plugins.json` are deliberately not
tracked: they carry absolute paths to per-machine checkouts.

Install mirrors directories and links files, so the live state next to
`config.yml` is untouched. Adding a *new* file under `home/.omp/` needs a
`dotagents install` on each machine to appear there.

Config edits made inside omp land in the linked repo file — `git status` in
dotagents is the review queue; commit and pull to move a setting between
machines. If omp ever replaces the symlink with a real file, the next install
reports it as a CONFLICT (nothing is clobbered); reconcile by hand and re-run.

## Audited upgrades (`lib/omp-upgrade/`)

omp's own `omp update` self-updates from GitHub releases with no review. The gate
in `lib/omp-upgrade/` replaces that with: audit the public source diff first,
activate only a pinned, approved release.

Wiring (per machine, once):

```sh
lib/omp-upgrade/install.sh                       # adopt the omp already on PATH
lib/omp-upgrade/install.sh --adopt-release 18.0.0   # or download + verify that release
lib/omp-upgrade/install.sh --uninstall           # put the real binary back on PATH
```

`--adopt-release` is for machines whose omp is not a release binary (macOS via
bun/npm, say): it downloads this platform's asset, checks it against the SHA256
GitHub publishes, and records it as the baseline. Adoption is the trust
baseline — adopt the version you already run, not the newest one, and let the
audit gate everything after it.

It needs python 3.11+ with a populated CA store; `install.sh` probes for one and
records the resolved interpreter in the shim (`PYTHON=` overrides). macOS's
`/usr/bin/python3` (3.9, no `tomllib`) and an uninitialised python.org framework
build are both rejected.

It moves the installed binary to `~/.local/lib/omp-upgrade/omp-real`, writes a
`~/.local/bin/omp` shim that execs `launcher.py`, and records the identity the
installed binary uses (version, source tag commit, sha256) in
`~/.local/state/omp-upgrade/installed.json`. `launcher.py` and `audit.py` are
symlinks into this repo, so a `git pull` updates the gate itself.

Day to day:

```sh
omp --upgrade-status   # last result, features and remaining risks
omp --upgrade-check    # background check, daily interval
omp --upgrade-apply    # activate a staged release; checksum, smoke and rollback still apply
omp update             # blocked: bypasses the gate
```

An interactive `omp` launch does three things: activates an already-approved
release (verifying size and sha256 against the approval, with a rollback
journal), prints the audit notice once per verdict, and kicks off the next
background check. Other non-interactive invocations never upgrade; `--upgrade-apply`
is the explicit exception and does not start an agent session.

The audit itself (`audit.py check`) fetches release metadata from the GitHub API,
shallow-fetches the upstream tag, diffs explicitly accepted source → target commit,
reviews the chunks with a model, and writes `approved.json` only after a complete,
SAFE final review or explicit target-specific user acceptance. Review is not attestation:
the binary digest and asset URL are pinned independently.

The asset is picked per platform (`omp-linux-x64`, `omp-darwin-arm64`, …); an
unrecognised platform gets no asset name and the gate refuses rather than
guessing.

Source trust and binary installation are separate. Record explicit acceptance with
`python3 -I lib/omp-upgrade/audit.py accept-source --version VERSION --commit COMMIT --detail REASON`.
This writes `accepted-source.json`, not an approval. Community trust must be
described as acceptance, never an independent audit. The newest accepted source
below the target is reviewed; the installed binary SHA256 still binds activation.

Changed dependencies HOLD until exact reviewed manifest bytes and artifact
digests are recorded with `audit.py record-evidence` (see `--help`). Records in
`dependency-evidence.json` clear only their exact commit/version/manifest tuple.
They do not skip model review or attest the release binary. Ledger capacity
errors preserve previous readable records.

Review retains the 1 MiB source, 64 KiB chunk, and 16-chunk limits; oversized
changes HOLD without truncation. `audit.py check --force` bypasses only the daily
cooldown, not security checks. Always check the report's installed version and
timestamp before attributing an older HOLD to a fresh request.

Complete chunk reviews collect concerns without deciding activation. Missing,
malformed, truncated or explicitly incomplete reviews still HOLD immediately.
The final coherence review receives the full diff, all prior reviews and each
identified concern. Approval requires a SAFE final verdict and an explicit,
evidence-grounded resolution for every concern. `chunk_findings` retains the
original findings and resolutions; `risks` contains unresolved final findings.
The composed final input retains its existing 1 MiB limit; overflow HOLDs without
truncating the diff or discarding concerns.

### Repeatable per-release audit

```sh
# Check now. Pin a version to avoid reviewing a moving "latest".
python3 -I ~/.local/lib/omp-upgrade/audit.py check --version VERSION
# Supply missing public helper code from that exact commit, not a working tree.
python3 -I ~/.local/lib/omp-upgrade/audit.py check --version VERSION --context packages/utils/src/file-lock.ts
# Deliberately discard model-review reuse, without weakening checks.
python3 -I ~/.local/lib/omp-upgrade/audit.py check --version VERSION --fresh-reviews
omp --upgrade-apply
omp --version
```

Complete reviews are cached by the exact input (source, identities, dependency
evidence, context and prior findings), policy, configured model, gate code and
reviewer binary digest. Changed input reruns that review. Adding final-review
context reuses unchanged chunks. Malformed/incomplete responses are never reused.
Unchanged installed releases need no model calls or binary download.

Stop after one complete review and, when needed, one context-supplement pass.
Separate evidence gaps from concrete behavior changes. Do not keep rewording the
prompt to chase SAFE. External dependency changes still need real static review;
neither cache nor a user exception bypasses that prerequisite.

### Explicit acceptance of a held release

Only after the user accepts all reported findings and remaining uncertainty:

```sh
python3 -I ~/.local/lib/omp-upgrade/audit.py accept-reviewed \
  --version VERSION --commit COMMIT --sha256 ARTIFACT_SHA256 \
  --report-sha256 REPORT_SHA256 --detail 'Explicit user decision and accepted risks'
omp --upgrade-apply
```

`REPORT_SHA256` is the digest of the exact `report.json` shown to the user.
Acceptance requires complete chunk and final reviews, valid dependency evidence,
and matching public tag/asset identities. It records the full held report and a
separate `user-accepted` record under `evidence/VERSION/`; the model verdict stays
HOLD. Source trust advances for the next delta, but the exception cannot authorize
another artifact or future finding. `ACCEPTED` means staged, not yet installed.

The audit used to be triggered through a systemd user unit; it is now a detached
child process (`request_audit` in `launcher.py`) — the audit serializes itself
with its own lock and daily interval, so the unit bought nothing.

Tests: `cd lib/omp-upgrade && python3 -m unittest test_launcher test_audit`.
