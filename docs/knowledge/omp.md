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
audit diffs against (version, source tag commit, sha256) in
`~/.local/state/omp-upgrade/installed.json`. `launcher.py` and `audit.py` are
symlinks into this repo, so a `git pull` updates the gate itself.

Day to day:

```sh
omp --upgrade-status   # last audit verdict: CURRENT / HOLD / INSTALLED, features, risks
omp --upgrade-check    # request a background audit (at most one per day)
omp update             # blocked: bypasses the audit
```

An interactive `omp` launch does three things: activates an already-approved
release (verifying size and sha256 against the approval, with a rollback
journal), prints the audit notice once per verdict, and kicks off the next
background check. Non-interactive and piped invocations never upgrade.

The audit itself (`audit.py check`) fetches release metadata from the GitHub API,
shallow-fetches the upstream tag, diffs explicitly accepted source → target commit,
reviews the chunks with a model, and only writes `approved.json` when the verdict
holds. A model verdict is treated as review, not attestation: the binary digest
and asset URL are pinned independently.

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

Review retains the 512 KiB source, 64 KiB chunk, and 12-chunk limits; oversized
changes HOLD without truncation. `audit.py check --force` bypasses only the daily
cooldown, not security checks. Always check the report's installed version and
timestamp before attributing an older HOLD to a fresh request.

The audit used to be triggered through a systemd user unit; it is now a detached
child process (`request_audit` in `launcher.py`) — the audit serializes itself
with its own lock and daily interval, so the unit bought nothing.

Tests: `cd lib/omp-upgrade && python3 -m unittest test_launcher test_audit`.
