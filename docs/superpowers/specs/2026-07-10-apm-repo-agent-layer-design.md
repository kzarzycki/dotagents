# Repository agent layer — APM and fnox design

Status: draft for pilot validation.

## 1. Outcome

A participating repository carries one reviewable agent layer for Claude Code
and OpenAI Codex. APM owns portable agent packages,
locked resolution, native target generation, and supply-chain audit. fnox binds
environment values when a process starts; native tools retain custody of their
own authentication state. The same repository
contract serves a solo developer, a company team, and a client engagement.

The common baseline contains only capabilities proven on both release targets.
Vendor-specific capabilities remain isolated target extensions. Machine paths,
credentials, client endpoints, and provider identities never enter APM packages.

## 2. Scope

The first release covers:

- a committed APM manifest and lockfile;
- a versioned company baseline package;
- repository-authored APM primitives;
- explicit generation for Claude Code and Codex;
- committed native target output;
- fnox profiles backed by local and managed providers;
- company policy and CI audit;
- mise as the repository task runner and executable pinning boundary.

The first release excludes:

- toolkit selection, meta-plugin composition, and fleet binding;
- SessionStart materialization;
- installation, generation, or secret retrieval triggered by directory entry;
- normalized runtime permissions across vendors;
- Cursor and GitHub Copilot generation and behavioral qualification;
- automatic environment replacement in an already-running editor;
- a custom package manager, secret store, or config compiler.

## 3. Architecture

### 3.1 Two contracts

**Repository contract.** APM resolves versioned packages, deploys primitives,
compiles native instruction files, records the lock, and audits generated state.
The repository commits sources and generated outputs so humans, CI, and cloud
agents inspect the same revision.

**Machine-binding contract.** Portable sources name each required machine
interface. `fnox.toml` declares environment-value profiles, missing-value
behavior, and provider references; fnox resolves those values into a fresh
process. Other interfaces use native tool authentication, files, sockets, or
workload identity. The launch task composes the declared interfaces without
rewriting APM output or taking custody of tool-managed credentials.

```text
company package ─┐
project sources ─┼─> APM lock/install/compile/audit ─> committed native targets
source policy ───┘                                      │
                                                        │ fresh launch
fnox profile ─> local/managed provider ─> child env ────┘
```

### 3.2 Component boundaries

| Component | Owns | Excludes |
|---|---|---|
| APM | Package graph, lock, deployment, compilation, package policy, drift audit | Resolved machine values, CLI binaries, runtime authorization |
| Company package | Shared portable instructions and capabilities | Client credentials, machine paths, mandatory target-only features |
| Repository sources | Project-specific APM primitives and fnox declarations | Hand-edited generated target files |
| fnox | Profiles, provider adapters, missing-value policy, child environment | Agent compilation, package resolution, runtime permissions |
| Secret provider | Credential custody, provider identity, access control, rotation, audit | Agent configuration generation |
| Agent harness | Native config loading and runtime permission decisions | Package and secret management |
| Authenticated CLI | Native authentication state and OS credential-store access | Credential export to APM or fnox |
| mise | Repository task interface, executable installation, version, checksum, and process environment | Agent primitives and secret custody |

### 3.3 Binding forms

Machine bindings use the first compatible form:

1. An environment variable resolved by fnox into the child process.
2. A native authenticated tool invocation; the tool may keep its credential in
   the OS credential store.
3. A file or socket reference available to the launched process.
4. A workload identity supplied by the execution platform.
5. A stable executable name resolved from the launched process's `PATH`, or an
   environment-consuming bridge for a field the target cannot expand, such
   as a machine-specific remote MCP URL.

A capability that fits none of these forms stays outside the portable baseline.
The two release targets may use different internal transports while exposing the same
user-visible capability.

## 4. Requirements

### 4.1 Repository and release

- **REP-01 — Committed repository contract.** A participating repository shall
  commit its APM manifest, APM lockfile, source policy when company-managed,
  repository-authored sources, and APM-generated native target outputs.
- **REP-02 — Locked frozen resolution.** Routine sync and CI shall resolve only
  dependency revisions already recorded in the committed APM lockfile.
- **REP-03 — One explicit two-target release.** Each release shall explicitly
  generate and validate Claude Code and Codex as one
  unit without relying on filesystem auto-detection.
- **REP-04 — Versioned company baseline.** A company repository shall lock a
  versioned company baseline package by immutable revision and content hash.
- **REP-05 — Portable baseline and isolated extensions.** The common baseline
  shall contain only behavior proven on both release targets; target-specific
  extensions shall not become prerequisites for another target.
- **REP-06 — Company source policy and audit.** A company repository shall apply
  its allowed-source policy and pass APM integrity, security, and drift audit in
  CI.
- **REP-07 — Supported compatibility matrix.** The release shall record the APM,
  fnox, Claude Code, Codex, OS, and architecture versions that passed conformance.

### 4.2 Machine and environment binding

- **ENV-01 — Named machine-binding contract.** Portable sources shall identify
  every machine binding by a stable name or interface, required/optional
  classification, and type: environment variable, native tool authentication,
  file, socket, or workload identity.
- **ENV-02 — Portable per-target binding.** Each machine-bound field shall compile
  to a target-native environment reference, authenticated tool invocation, file
  or socket reference, workload identity, stable command, or approved bridge
  without a resolved machine value in generated files.
- **ENV-03 — Required-value failure.** An unresolved required fnox value shall
  prevent creation of the agent child process.
- **ENV-04 — Provider-neutral config and launch.** Changing the selected fnox
  provider shall not change APM sources, generated target structure, or the agent
  launch interface.
- **ENV-05 — Explicit repository-scoped profiles.** Company, client, and CI
  launches shall explicitly select a profile whose fnox-managed values belong to
  that repository and execution context.
- **ENV-06 — Clean parent-environment boundary.** Client work shall launch through
  the clean-environment boundary selected by the company pilot because fnox does
  not scrub variables inherited from its parent process.
- **ENV-07 — Solo age and OS keychain.** The solo path shall store project values
  as committed age ciphertext and keep the age identity in the OS keychain.
- **ENV-08 — Managed company/client provider.** Company and client profiles shall
  use an approved managed provider that owns authentication, revocation,
  least-privilege access, and audit records.
- **ENV-09 — Headless CI.** CI shall resolve its test values without a GUI,
  interactive keychain, browser flow, or terminal prompt.
- **ENV-10 — Process-scoped delivery and restart.** Bound values shall enter only
  the fresh agent process and its children; profile changes and value rotation
  shall require a fresh process.
- **ENV-11 — Tool-managed native authentication.** The agent layer shall use a
  CLI's native authentication state, including credentials held in an OS
  credential store, only by invoking that CLI and without extracting, copying,
  or persisting the credential.

### 4.3 Trust and secret handling

- **SEC-01 — Inert repository discovery.** Clone, checkout, and directory entry
  shall perform no install, compile, provider access, project execution, or
  permission mutation.
- **SEC-02 — Explicit review, execution, and native trust.** First sync shall
  follow operator review and an explicit command; native harness trust controls
  shall remain enabled.
- **SEC-03 — Separate policy planes.** APM policy shall govern installed content,
  while each harness's native permission model governs runtime execution;
  installation shall grant no prompt-free runtime authority.
- **SEC-04 — No resolved-value persistence.** Resolved machine values shall be
  absent from tracked files, generated targets, lockfiles, process arguments,
  process listings, logs, diagnostics, and shell traces.

### 4.4 Operation and isolation

- **OPS-01 — Owned-path lifecycle.** APM shall identify its paths, refuse
  collisions with unclaimed files, detect hand edits and orphans, remove its
  stale files, and preserve adjacent unclaimed files.
- **OPS-02 — Deterministic order-independent regeneration.** Clean clones using
  the same supported inputs shall generate byte-identical output regardless of
  target compilation order, including files shared by multiple targets.
- **OPS-03 — Closed sync failure and recovery.** A failed sync stage shall stop
  later stages and block release; recovery shall restore committed last-known
  output before another sync or launch.
- **OPS-04 — Offline inspection and closed provider failure.** Committed target
  output shall remain inspectable offline, and an unavailable required provider
  shall fail before agent child creation with the provider named.
- **OPS-05 — Standard task and executable boundary.** Repository automation
  shall run as named mise tasks. Required external executables shall be pinned
  with mise, and agent launch shall use a tested mise→fnox→agent process chain
  that depends on neither shell activation nor direnv.
- **OPS-06 — Repository-mode and effect isolation.** No-manifest repositories
  shall remain untouched; APM-only repositories shall work without fnox;
  fnox-only directories shall access providers only after explicit invocation;
  syncing one repository shall not modify another repository or user-global
  agent state.
- **OPS-07 — Correct repository boundary.** Sync shall operate on the canonical
  innermost Git worktree root for normal, nested, linked-worktree, and symlinked
  checkout entry points.

Recovery of committed output is part of `OPS-03`. Direnv independence is part of
`OPS-05`.

## 5. Repository contract and ownership

### 5.1 Committed sources and artifacts

| Path class | Role | Commit policy |
|---|---|---|
| APM manifest and lock | Dependency source and immutable resolution | Commit |
| Company APM policy | Allowed package sources and install controls | Commit in company repositories |
| Repository APM sources | Project-authored primitives | Commit when present |
| APM-generated native files | Exact Claude Code and Codex runtime input | Commit |
| `fnox.toml` | Names, profiles, provider references, ciphertext, non-secret defaults | Commit when machine values exist |
| `fnox.local.toml` | Machine-only overrides | Ignore |
| APM package cache | Rebuilt from lock | Ignore |
| `mise.toml` and lock | Task interface and external executable selection | Commit |
| Provider state and credentials | Machine or managed provider state | Never commit |

APM owns only paths supported by its lock metadata or generated markers. It does
not own entire `.claude`, `.codex`, `.cursor`, `.agents`, `.github`, or `.vscode`
trees. Unclaimed native files may coexist outside APM-owned paths.

### 5.2 Generated-output policy

Generated outputs are committed build artifacts. Contributors change the APM
manifest, repository sources, or package versions, then regenerate both
targets and review the diff. CI compiles from a clean clone, validates native
schemas, compares output with the committed tree, and runs APM audit.

Multiple targets may contribute to a shared root file such as `AGENTS.md`.
Generation must produce the same shared file for every target order. Target
selection is explicit in the release workflow rather than inferred from local
directories or files.

## 6. Machine binding and trust

### 6.1 fnox profiles

`fnox.toml` is required only when the repository declares environment values for
fnox to resolve.
It declares the complete name set, required-value behavior, profiles, and
provider references. Project config stops parent-directory inheritance. Company
and client secrets do not live in fnox's always-loaded global secret table.

Profiles isolate values managed by fnox. They do not remove arbitrary variables
from the parent process. Before the company gate passes, the pilot selects and
tests one concrete client launch boundary: an environment allowlist, container,
VM, or separate OS identity. The same boundary applies to all company client
launches in the first release.

### 6.2 Solo and managed providers

The solo conformance path uses age ciphertext in `fnox.toml` and one age identity
stored in the OS keychain. Every declared desktop platform must pass the same
local-provider scenario.

The company conformance path uses one selected managed provider. Provider
authentication, revocation, access policy, and audit remain provider concerns.
The repository contains references and stable binding names, not credentials.
CI uses a non-interactive identity and non-production values.

Native CLI authentication remains outside fnox. The launch task invokes the CLI,
which reads its own authentication state; the task does not export or duplicate
the credential.

### 6.3 Sync and launch behavior

The repository exposes sync, check, Claude launch, and Codex launch as named mise
tasks. Sync has five logical stages: locked install, two-target compile, native-schema
validation, audit/clean-tree comparison, and fnox declaration validation when
`fnox.toml` exists. Each failed stage returns non-zero, names the stage, and
prevents later stages.

A failed sync can leave a visible working-tree diff. Recovery restores committed
last-known outputs, reruns the complete sync, and passes CI. The workflow never
launches against a partially generated tree. CI compile and schema checks are
mandatory for every agent-layer change; Claude Code and Codex behavioral smoke tests run
in the pilot and each release qualification.

Routine agent launch consumes committed native output and does not resolve
packages. A profile switch, secret rotation, or harness restart
creates a fresh effective process before new values are expected.

## 7. Conformance gates

### 7.1 Core two-agent gate

Every participating repository passes scenarios AC-01 through AC-05, AC-07,
AC-16 through AC-27, and AC-28. The gate proves a locked, deterministic, auditable
Claude Code and Codex release with repository-scoped effects.

### 7.2 Company managed-provider gate

A company repository also passes AC-06, AC-08 through AC-11, and AC-13 through
AC-15 using the selected managed provider and clean-environment launcher.

### 7.3 Solo local-provider gate

A solo repository also passes AC-08, AC-12, and AC-15 on every desktop platform
declared as supported. Company source policy and the managed-provider scenario
do not apply to the solo gate.

## 8. Acceptance scenarios

### AC-01 — Repository forms.

A local-source fixture, a locked-package-only
  fixture, an APM-only value-free fixture, and a machine-bound fixture each
  contain the required committed source/artifact subset and generate both
  targets.
### AC-02 — Frozen clean clone.

From an empty package cache, frozen resolution
  installs only locked revisions, leaves manifest and lock unchanged, and
  regenerates the committed outputs without a diff.
### AC-03 — Explicit two-target release.

The release invocation resolves
  exactly Claude Code and Codex; omitting one target
  fails validation.
### AC-04 — Portable capability parity.

The instruction, skill, agent, stdio
  MCP, and authenticated remote MCP fixtures execute their sentinel behavior in
  both harnesses; the validation report accounts for every required
  primitive and target.
### AC-05 — Target-extension isolation.

Adding one declared Claude-only
  extension leaves Codex generated hashes and portable
  sentinel results unchanged.
### AC-06 — Company package policy and audit.

The company fixture pins the
  baseline revision/hash, rejects a disallowed source, rejects modified locked
  content, and reports generated drift.
### AC-07 — Compatibility matrix.

The release record names exact APM, fnox,
  harness, OS, and architecture versions; a run outside the supported matrix
  fails compatibility validation before sync.
### AC-08 — Binding coverage and native output.

Bindings extracted from
  portable sources and generated targets equal the repository declaration set,
  and fnox-managed environment names equal the fnox declaration set. Each
  generated field contains a native environment reference, authenticated tool
  invocation, file or socket reference, workload identity, stable command, or
  approved bridge and no resolved value.
### AC-09 — Required-value failure.

Removing one required value makes fnox name
  the missing value and profile, return non-zero, and create no child-process
  start marker.
### AC-10 — Provider substitution.

Local and managed test profiles produce the
  same probe result through the same launch interface while APM source and target
  hashes remain unchanged.
### AC-11 — Client isolation boundary.

Client A and B profiles expose only their
  fnox-managed canaries; the selected clean-environment launcher removes a
  parent-process canary before fnox starts.
### AC-12 — Solo local provider.

On every supported desktop platform, fnox
  decrypts committed age ciphertext through the OS-keychain identity; scans find
  no plaintext value or private identity in the repository.
### AC-13 — Managed provider control.

The selected company provider resolves
  the declared canary, denies an adjacent decoy, records the access event, and
  prevents launch after identity revocation.
### AC-14 — Headless CI provider.

CI resolves non-production values with no GUI,
  keychain prompt, browser flow, terminal prompt, or stdin interaction.
### AC-15 — Process scope and rotation.

The fresh agent and its child read the
  selected value; the parent shell does not gain it; an existing process retains
  its old value after rotation and a new process receives the new value.
### AC-16 — Inert discovery.

Instrumented clone, checkout, and directory entry
  produce zero APM, fnox, mise, provider, project-process, file-write, network,
  and permission-mutation events.
### AC-17 — Review and native trust.

The first sync begins only after recorded
  operator review and explicit invocation; each harness presents its enabled
  native repository-trust control on first launch.
### AC-18 — Permission-plane separation.

Installing the test package changes
  no native runtime permission file and creates no prompt-free authorization.
### AC-19 — Resolved-value canary.

A unique canary is absent from tracked and
  generated files, locks, process arguments/listings, command output, CI logs,
  failure diagnostics, and shell traces.
### AC-20 — Owned-path lifecycle.

A collision leaves the unclaimed file
  unchanged and fails with its path; direct edits and orphans fail audit;
  dependency cleanup removes only stale APM-owned files.
### AC-21 — Deterministic shared output.

Two clean clones and both target
  compilation order produce byte-identical APM-owned output, including shared
  root instruction files.
### AC-22 — Failure and committed recovery.

Fault injection at each sync stage
  returns non-zero, names that stage, starts no later stage, and blocks release;
  restoring committed outputs and rerunning the full workflow returns a clean
  passing tree.
### AC-23 — Offline behavior.

With network disabled, committed targets remain
  readable and hash-verifiable; a managed-provider launch fails before child
  creation and names the unavailable provider.
### AC-24 — Standard task and executable process chain.

Sync, check, Claude
  launch, and Codex launch run through the committed mise task interface. The
  executable fixture exposes the locked path/version inside the agent and MCP
  child without shell activation, and the value-free fixture passes without
  direnv installed.
### AC-25 — Repository modes and effect isolation.

No-manifest use has zero
  effect; APM-only use needs no fnox; fnox-only use contacts a provider only after
  explicit invocation; syncing repository A leaves repository B and user-global
  agent state byte-identical.
### AC-26 — Repository boundary.

Normal, nested, linked-worktree, and symlinked
  entry points resolve the canonical innermost worktree root and modify only that
  root.
### AC-27 — Release smoke.

The qualified repository launches both pinned
  harness versions and each harness executes the common instruction, skill, and
  MCP sentinel suite against the committed target files.
### AC-28 — Native tool authentication.

With `GITHUB_TOKEN` absent and `gh`
  authenticated through its native credential store, the launch check invokes
  `gh auth status`. Instrumentation confirms that it never invokes
  `gh auth token`, places no credential in fnox configuration, and does not copy
  or persist the credential.

## 9. Requirement traceability

| Requirement | Acceptance scenarios |
|---|---|
| REP-01 | AC-01, AC-20 |
| REP-02 | AC-02 |
| REP-03 | AC-03, AC-27 |
| REP-04 | AC-06 |
| REP-05 | AC-04, AC-05 |
| REP-06 | AC-06 |
| REP-07 | AC-07, AC-27 |
| ENV-01 | AC-08 |
| ENV-02 | AC-04, AC-08 |
| ENV-03 | AC-09 |
| ENV-04 | AC-10 |
| ENV-05 | AC-11 |
| ENV-06 | AC-11 |
| ENV-07 | AC-12 |
| ENV-08 | AC-13 |
| ENV-09 | AC-14 |
| ENV-10 | AC-15 |
| ENV-11 | AC-28 |
| SEC-01 | AC-16 |
| SEC-02 | AC-17 |
| SEC-03 | AC-18 |
| SEC-04 | AC-19 |
| OPS-01 | AC-20 |
| OPS-02 | AC-02, AC-21 |
| OPS-03 | AC-22 |
| OPS-04 | AC-23 |
| OPS-05 | AC-24 |
| OPS-06 | AC-25 |
| OPS-07 | AC-26 |

Every requirement maps to at least one scenario, and every scenario participates
in at least one conformance gate.

## 10. Pilot decisions and findings

The pilot must close these decisions before company conformance:

- **OD-01 — Package source.** Select the authenticated package host or registry
  and company source allowlist.
- **OD-02 — Supported matrix.** Select the exact APM, fnox, harness, OS, and
  architecture versions qualified by the pilot.
- **OD-03 — Managed provider.** Select the company provider and its
  non-production CI identity.
- **OD-04 — Client environment boundary.** Select one concrete allowlisted
  launcher, container, VM, or separate-identity pattern for client work.
- **OD-05 — Generated-output review.** Select code ownership and review policy
  for manifest, lock, policy, and generated-target changes.

Exact APM/fnox target paths, CLI flags, merge behavior, cleanup behavior, and
native parser commands are pilot findings. The acceptance harness records the
verified behavior for the selected versions; this design does not invent
unverified syntax.

## 11. Deferred extensions

### DEX-001 — Credential gateway

A remote or separately isolated gateway can keep a long-lived upstream secret
out of the agent process. It requires operation allowlists, short-lived client
identity, access audit, and blocked direct egress to the upstream service. A
same-UID local proxy hides credential bytes but is not an authority boundary.
DEX-001 has no first-release acceptance scenario.

### DEX-002 — Omnigent integration

Omnigent's recommended first role is UI, launcher, and session manager. It
consumes the native configuration APM generated in the workspace. It neither
compiles agent config nor stores secrets.

A future optional session field, `environment_profile`, may persist an opaque
fnox profile name and pass it to the launch boundary. Omnigent currently shares
bundle skills and its MCP bridge across Claude and Codex; native plugins remain
harness-specific. Global environment passthrough is unsuitable for secrets.

### DEX-003 — Cursor and GitHub Copilot qualification

Cursor and GitHub Copilot are deferred release targets. Their qualification
shall reuse the repository and machine-binding contracts, add native generation
and behavioral acceptance coverage, and must not weaken the Claude Code and
Codex conformance gates.

### DEX-004 — Toolkits, meta-plugins, and fleet binding

Personal capability grouping and automatic repository binding may consume the
same company APM packages later. It is independent of the repository standard
and machine-binding contract.

## 12. Definition of done

The first release is done when:

1. The core two-agent gate passes in a real repository.
2. The company pilot passes the managed-provider gate.
3. The solo fixture passes the local-provider gate on every supported desktop
   platform.
4. All 29 requirements map to passing scenarios and all 28 scenarios are in a
   conformance gate.
5. A second team reproduces the company gate from a clean clone using the
   published package, policy, provider, and compatibility matrix.
6. Project startup depends on no SessionStart materializer, toolkit pointer,
   direnv hook, or dotagents runtime code.
