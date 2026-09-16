# omp (oh-my-pi) in dotagents

## What is tracked

| Path | Installs to | Notes |
|---|---|---|
| `home/.omp/agent/config.yml` | `~/.omp/agent/config.yml` | the whole agent config: model roles, compaction, tool approval, display |
| `home/.omp/agent/rules/*.md` | `~/.omp/agent/rules/` | user-scope rules |
| `home/.omp/agent/extensions/*.ts` | `~/.omp/agent/extensions/` | herdr state extension |

Everything else under `~/.omp` is runtime state (sqlite dbs, sessions, logs,
`auth.json`, plugin caches, plugin registry files under `~/.omp/plugins/`, the
200 MB native binary, and lock files) — machine-local, gitignored, never
linked.

Install mirrors directories and links files, so the live state next to
`config.yml` is untouched. Adding a *new* file under `home/.omp/` needs a
`dotagents install` on each machine to appear there. To install OMP without
the other agent payloads, use `dotagents install --only omp --no-pull`; this
generic subset mode skips profiles, hooks, shell startup files, and generated
Claude settings.

The VPS OMP setup enables the public npm plugin
`@czottmann/pi-automode@1.15.0` (Claude Code-style auto-mode guardrails).
Install that plugin on each machine with:

```sh
patches/omp/bootstrap.sh
```

The bootstrap runs `omp plugin install @czottmann/pi-automode@1.15.0` only
when that exact enabled version is absent. It does not copy OMP's package or
lock files, because OMP owns and updates those files alongside `node_modules`.
The plugin's source is `https://github.com/czottmann/pi-automode`.

For a colleague's existing OMP installation, a pre-existing real
`~/.omp/agent/config.yml` is reported as a CONFLICT and left untouched. Preserve
any local settings, move the file aside, and rerun the subset install. Provider
credentials and model access still need to be configured on that machine.

Config edits inside OMP land in the linked repo file. That makes shared config
changes reviewable and reproducible, but personal provider or model changes
must not be committed to the shared clone. `omp config path` exposes one user
config directory, and the CLI help exposes no config-overlay option; use a
separate clone for personal variants.

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

Interactive launches never install; they print the notice and schedule the
background check. A successful lightweight check writes `approved.json`; run
`omp safe-update` to synchronously recheck the artifact and activate the staged
candidate. `omp --upgrade-apply` activates an already-staged candidate without
rechecking. Other non-interactive invocations never upgrade.

The default audit (`audit.py check`) is deliberately lightweight: it fetches stable
release metadata from the GitHub API, resolves the tag commit, downloads the exact
asset, and verifies its size and SHA256 before staging it. On macOS it also requires
`codesign --verify --strict` and the candidate's TeamIdentifier to match the
installed binary. It does not claim the source or embedded runtime is safe. Use
`deep-check` for the opt-in source diff, dependency evidence and model review; that
path may HOLD on behavioral findings. Review is not binary attestation.

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

Only source that ships in the binary is gated. `INFORMATIONAL` in `audit.py`
routes `.github/`, `infra/`, `nix/`, `docs/`, Dockerfiles, changelogs/readmes,
test/bench directories and `*.test`/`*.spec` files to `informational.diff` and
`informational_files`; the model never sees them and cannot HOLD on them.
Package-local build code (`packages/*/scripts/`, `build.ts`) and dependency
manifests stay gated: they shape the bytes in `__BUN`. A pipeline-only compromise
is therefore report-only. The gate does not compensate for that; the manual
per-release check does, and the audit skill must repeat it on the downloaded
asset: `codesign --verify --strict` and team `VTLHGQC72S` continuity with the
installed binaries, then compare Mach-O segments against the official
`bun-darwin-aarch64.zip` for the embedded Bun version (`strings | grep Bun/`) —
`__TEXT`, `__DATA`, `__DATA_CONST` match except the load-command bytes; only
`__BUN` and `__LINKEDIT` differ. Evidence goes under
`evidence/VERSION/focused-binary-review/`. `gated.diff` is what was reviewed;
`complete.diff` is the full delta; both and `informational.diff` are digested in
the report. A release with no gated changes HOLDs rather than approving unreviewed.

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
# Default: lightweight artifact identity check; no source/model review.
python3 -I ~/.local/lib/omp-upgrade/audit.py check --version VERSION
# Optional: full source/dependency/model review.
python3 -I ~/.local/lib/omp-upgrade/audit.py deep-check --version VERSION
# Optional helper context for strict mode.
python3 -I ~/.local/lib/omp-upgrade/audit.py deep-check --version VERSION --context packages/utils/src/file-lock.ts
# Optional: rerun strict reviews without cache reuse.
python3 -I ~/.local/lib/omp-upgrade/audit.py deep-check --version VERSION --fresh-reviews
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
