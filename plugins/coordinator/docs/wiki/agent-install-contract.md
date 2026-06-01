# Agent Install Contract

<!-- Single-Entry-Point Doctrine canonical home: docs/wiki/doctor-probe-design.md § Single-Entry-Point Consolidation Must Stay Addressable (+ coordinator/CLAUDE.md § Implementation Standards). Originated in archive/specs/2026-05-04-holodeck-umbrella-plugin.md §Single Entry-Point Doctrine (holodeck-side; not present in this repo) — canonicalized here 2026-05-27. -->
<!-- spec-backlink: archive/specs/2026-05-08-holodeck-install-chain-deps.md §3.1 -->
<!-- migration: doc moved here (coordinator-claude) from claude-unreal-holodeck on 2026-05-23 as the ecosystem-wide canonical home. Holodeck's copy becomes a one-line pointer redirect; project-rag-ue-addon and other consumers cite this file rather than mirroring it. -->

> This document is the single normative reference for the ecosystem-wide agentic install
> contract. Every repo in the dependency chain conforms to this contract. The contract was
> first implemented in `claude-unreal-holodeck` (chain leaf), authored bilaterally between
> holodeck and `project-rag-ue-addon`, and migrated to `coordinator-claude` (chain root) on
> 2026-05-23 as the canonical home. Per-repo schema files (`agent-install-manifest.schema.json`)
> remain in each repo; this doc is the single source of truth for the contract semantics they
> implement.

## Versioning

The contract is version-stamped via `agent_install_contract_version` in each repo's manifest.

| Version | Status | Summary |
|---|---|---|
| 1 | superseded by 2 | Initial contract: top-level `override_flags` upstream-authored, no consumer-authored per-dep arguments. |
| 2 | **current** | Adds optional `consumer_install_args` per-`DirectDep` (consumer-authored mode + version flags); formalises walker composition rules; tightens 92/93 exit-code semantics as walker-invocation bugs (not upstream failures). |

**Reader-widen-first sequencing.** Consumers reject manifests with a version they do not recognise. A safe v1→v2 rollout therefore widens each repo's manifest reader to accept the version *range* `{1,2}` in one commit per repo, confirms both green, then flips each repo's manifest literal `1 → 2` in lockstep. Whichever repo bumps its manifest first without the peer's reader-widen breaks the peer's walk — this is an install-surface-completeness trap. The same pattern applies to any future v2→v3 bump.

## Overview

Each repo in the install chain is **self-describing**: it declares its own direct upstream
dependencies, its canonical install entry-points, and the functional probes used to verify
each dependency. Discovery is dynamic — when a setup skill walks the chain, it reads each
upstream repo's manifest at walk-time rather than consulting any cached or centrally-maintained
registry.

The machine-readable structure lives in a JSON sidecar at a contracted path:

```
docs/install/agent-install-manifest.json
```

The human-facing companion (`docs/install/AGENT.md`) carries a one-line YAML frontmatter
pointer to the JSON sidecar and a human-readable prose body. The frontmatter is a pointer
only; all structured data lives in the JSON file.

The JSON Schema (draft 2020-12) governing `agent-install-manifest.json` is repo-local — each
conforming repo ships its own `docs/install/agent-install-manifest.schema.json` whose `$id`
field is the canonical schema identifier for that repo's manifest. The schemas are mirrors
(structurally identical modulo repo-specific defaults); this doc is the single source of
truth for what the schemas must encode.

---

## Authority boundary

Two distinct authorities meet inside the contract; the field-level split keeps them honest.

| Authority | Owned fields | Who declares the literal value |
|---|---|---|
| **Upstream-authored** | `override_flags.*`, `repo_id`, `setup_skill`, `doctor_skill`, `standalone_setup_script.*`, `required_env_vars` | The upstream repo, in its own manifest. The chain-walker reads these from the upstream's manifest at dispatch time. |
| **Consumer-authored** | Each `DirectDep` entry's `consumer_install_args` (v2+) | The consumer repo, in its own manifest, scoped to the specific upstream it's calling. |

**Why the split matters.** Two repos can declare the same schema key with different values — e.g. `override_flags.accept_hallucination_risk` is `--accept-hallucination-risk` in holodeck and `--accept-corpus-poisoning-risk` in `project-rag-ue-addon`. If a consumer hard-coded the upstream's gate spelling into its own manifest, that literal would drift the moment the upstream renamed its flag. The walker therefore reads override_flags from the **upstream's** manifest at dispatch time, never from the consumer's. `consumer_install_args` (mode + version selection) is the only consumer-authored part of the invocation.

---

## Schema reference

### Top-level fields

| Field | Type | Required | Description |
|---|---|---|---|
| `agent_install_contract_version` | `integer` | yes | Contract version. Readers MUST accept any version in the known range (currently `{1,2}`) and reject anything outside. Enables coordinated schema bumps across repos via reader-widen-first sequencing. |
| `repo_id` | `string` | yes | Canonical repo identifier — matches the GitHub repository name. Used as the visited-set entry key during chain-walk. |
| `setup_skill` | `string` | yes | The slash-command a human types to invoke the agentic setup flow (informational — not the agent dispatch primitive; see §Skill chain-walker). |
| `doctor_skill` | `string` | yes | The slash-command a human types to invoke the health-check flow (informational). |
| `standalone_setup_script.posix` | `string` | yes | Relative path (from repo root) to the POSIX (bash) standalone setup script. This is the actual agent dispatch target. |
| `standalone_setup_script.windows` | `string` | yes | Relative path (from repo root) to the Windows (PowerShell) standalone setup script. |
| `direct_deps` | `array<DirectDep>` | yes | Ordered list of direct upstream dependencies. The chain-walker processes these in declaration order. Does not include transitive deps — each upstream declares its own. |
| `required_env_vars` | `array<string>` | yes | Environment variables that must be set for install to succeed. The standalone script prompts for any that are missing in interactive mode and fails fast in non-interactive mode. |
| `override_flags.skip_dep_check` | `string` | yes | The first flag of the override flag pair (e.g., `--skip-dep-check`). Both flags must be passed together; one alone produces exit code 93. **Upstream-authored** — see Authority boundary. |
| `override_flags.accept_hallucination_risk` | `string` | yes | The second flag of the override flag pair. Each upstream declares its own value (e.g., holodeck uses `--accept-hallucination-risk`, project-rag-ue-addon uses `--accept-corpus-poisoning-risk`). Signals the caller explicitly accepts the risk of running without hard deps. **Upstream-authored**. |

### DirectDep fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `string` | yes | Canonical dep identifier — matches the upstream's `repo_id`. Used as the visited-set key during chain-walk. |
| `severity` | `enum` | yes | `hard`, `soft`, or `optional` — see §Severity semantics. |
| `sibling_dir_name` | `string` | yes | Expected directory name of the sibling clone, relative to the consumer repo's parent directory. The chain-walker checks for presence at `<parent>/<sibling_dir_name>` before running the functional probe. |
| `upstream_url` | `string` | yes | Canonical GitHub HTTPS URL for cloning this dep. |
| `functional_probe` | `FunctionalProbe` | yes | Verifies the dep is not only present but functional. See §Functional probe kinds. |
| `consumer_install_args` | `array<string>` | **no** (v2+) | Optional. Args the consumer wants passed to this upstream's standalone setup script — mode selection (e.g. `--consumer-only`) and version selection (e.g. `--ue-version 5.7`). Composed by the chain-walker with `--i-am-agent` and the **upstream's** `override_flags`; does NOT include the upstream's override flags (those are read from the upstream manifest at dispatch time). Omit version-tag literals (e.g. `--corpus-tag`) where the upstream supports a newest-for-line resolution convention — let the upstream resolve to avoid pin-to-deleted-tag skew. |

`DirectDep` retains `additionalProperties: false`. `consumer_install_args` is an additive optional property, so a v1 consumer manifest validates clean under the v2 schema (forward-compatible).

### FunctionalProbe fields

| Field | Type | Conditional | Description |
|---|---|---|---|
| `kind` | `enum` | always | One of `sibling_dir_exists`, `file_exists`, `python_import`, `command_succeeds`. |
| `path` | `string` | required when `kind` is `file_exists` | Path relative to the sibling repo root. |
| `expr` | `string` | required when `kind` is `python_import` | Python import expression evaluated via the resolved Python interpreter. |
| `cmd` | `string` | required when `kind` is `command_succeeds` | Shell command that must exit zero for the dep to be considered functional. |

---

## Severity semantics

| Severity | Chain-walker behavior |
|---|---|
| `hard` | Block install unless the override flag pair is passed and (in TTY mode) double-confirmation is satisfied. Hard-missing deps trigger the consent gate (§Consent gate). |
| `soft` | Warn loudly. Offer to walk the dep chain and install. If the user declines, proceed without the dep. |
| `optional` | Offer once. No warning if the user declines. Proceed silently. |

---

## Functional probe kinds

The chain-walker runs two checks for each dep, in order:

1. **Implicit sibling presence check** (`sibling_dir_exists`): does the directory `<parent>/<sibling_dir_name>` exist? This check is always implicit — it runs regardless of the declared `functional_probe.kind`.
2. **Functional probe** (declared in `functional_probe.kind`): is the dep actually usable?

The initial set of probe kinds (extensible — new kinds require a contract version bump):

| Kind | Description | Required extra field |
|---|---|---|
| `sibling_dir_exists` | Implicit always-run check. No additional fields. Can be used as the declared probe when directory presence alone is sufficient. | none |
| `file_exists` | The file at `path` (relative to the sibling repo root) exists. | `path` |
| `python_import` | The Python import expression in `expr` succeeds via the resolved Python interpreter. | `expr` |
| `command_succeeds` | The shell command in `cmd` exits zero. Escape hatch for non-Python upstreams. | `cmd` |

A dep may be `present` (sibling dir exists, functional probe passes), `missing` (sibling dir absent), or `present-but-broken` (sibling dir exists, functional probe fails).

Probe-status returns must follow the closed remediation loop invariant: every status branch carries an explicit `remediation` field that names the next mutation step. See `holodeck-doctrine.md §7.4` and the doctor agent surface in `holodeck-install-prereq.md` for the broader doctor/probe contract that this manifest's probes plug into (holodeck-side references; consumers adapt the equivalent locally).

---

## Dual-mode script UX

Every conforming repo's standalone setup script operates in two modes: **human-interactive** (invoked by hand from a terminal) and **machine-parseable** (invoked by an agent). The (a)(b)(c)(d) sequence below defines both paths.

### Step (a) — Agent-or-human detection

On launch in a TTY context, the script prints a one-line preamble and waits for input:

```
Are you running this script as an autonomous agent rather than via /<setup-skill>? [y/N]
```

Responses:
- **y**: print the path to `docs/install/AGENT.md` and exit **92** (agent-direct-invocation-detected). The agent should dispatch the setup skill instead.
- **N** (or enter): continue as interactive human-mode.

Override mechanisms (suppress the prompt entirely):
- `--i-am-agent` flag: acts as y by itself (exit 92); paired with the upstream's `override_flags` pair, runs in agent mode (see §Walker composition).
- `--i-am-human` flag: acts as N (continue).
- Equivalent environment variable (e.g. `HOLODECK_RUN_MODE=agent` / `=human` in the holodeck reference impl; consumer repos may declare an analogous repo-scoped env var).

**Non-interactive contexts** (`--non-interactive` flag or non-TTY): step (a) prompt is skipped entirely — both are treated as implicit `--i-am-human`. This avoids prompt text appearing in CI logs.

### Read-only flag carve-out

Certain flags indicate the caller wants information only, not installation. When any of these flags is present, step (a) and the consent gate (steps b–d) are skipped entirely — the script services the request and exits without running Phase 0:

| Flag | Description |
|---|---|
| `--help` | Print usage and exit 0. |
| `--version` | Print version and exit 0. |
| `--phase-list` | List available install phases and exit 0. |
| `--last-status` | Print the last recorded install status and exit 0. |
| `--i-am-agent` | (documented here for completeness) exits 92 before Phase 0 when passed alone. |

This is the canonical read-only flag baseline. Repos that conform to this contract inherit this set and may extend it with repo-specific read-only flags. The set must be greppable from a single named function or allowlist comment block in the script.

### Read-only carve-out and install-status.json mutation

Flags in the read-only carve-out table MUST prevent any write to the install-status ledger (e.g. `~/.claude/holodeck/install-status.json` in holodeck; consumers adapt the path). The carve-out is not just a UX convenience — it is a safety boundary: doctor probes invoke the standalone script with `--last-status` to read phase state without triggering a new install or modifying the ledger.

**Enforcement:** every conforming repo's standalone script must gate install-status writes behind the read-only-carveout check. Any write path that bypasses this gate will corrupt the ledger during doctor-mode reads.

If a probe needs to inspect the install ledger while the write gate is active, it reads the file directly — it does not invoke the standalone script without `--last-status`.

### Step (b) — Dependency probing

For each declared dep, the script runs the implicit sibling check then the functional probe:
- `hard` dep missing or broken: capture for the consent gate (step d).
- `soft` dep missing: warn loudly, offer to clone-and-walk via gh CLI, proceed if declined.
- `optional` dep missing: print a one-line offer, proceed silently if declined.

### Step (c) — Required env var collection

Interactively prompt for any `required_env_vars` that are not already set. Validate each before proceeding. In non-interactive mode, fail fast if any required var is missing.

### Step (d) — Install with consent gate

Run the install. If hard-missing deps were found in step (b), the consent gate fires (§Consent gate below). If all hard deps are present and functional, the gate is not shown.

---

## Consent gate

The consent gate is the last barrier before installing without all hard deps. Its text is stored in a single file (`scripts/lib/dep_consent_banner.txt` in the holodeck reference implementation) — both script halves and the setup skill read from that file so the warning text has one source of truth.

**Example consent gate banner (holodeck concrete example):**

```
================================================================
WARNING — UNSAFE INSTALL REQUESTED

You are installing <repo-id> WITHOUT one or more of
its dependency-chain prerequisites:

  <list of missing hard deps, one per line>

Without these, agents using holodeck-control to mutate your
Unreal Engine project will operate with confident hallucination
at ~25% (Opus 4.7 baseline; smaller models are worse). UE
projects corrupted by hallucinated API calls are not always
recoverable from the editor's transaction log.

Canonical install order (do this first instead):
  1. coordinator-claude   (open-source, public)
  2. deep-research-claude (optional, recommended)
  3. project-rag
  4. project-rag-ue-addon
  5. claude-unreal-holodeck

To proceed anyway, you must confirm twice. The first prompt
asks whether you accept the missing-dep risk; the second asks
whether you specifically accept the ~25% hallucination risk.
================================================================
```

The verbatim warning text (including the ~25% figure) must not be paraphrased by the setup skill — the skill quotes it directly from the banner file.

### Consent gate behavior table

| Mode | Behavior |
|---|---|
| TTY, no flag pair | Banner → confirm 1 → confirm 2 → proceed. Either N → exit **91**. |
| Non-TTY, no flag pair | Banner to stderr → exit **90**. |
| TTY, both flags | Banner once → one-line acknowledgment → proceed. |
| Non-TTY, both flags | Banner once to stderr → proceed. |
| Either, only one of two flags | Exit **93** (override-flag-pair-incomplete). |

---

## Exit code table

| Code | Name | Semantics |
|---|---|---|
| 0 | `success` | Install completed; ledger updated. |
| 11 | `gh-unauth` | `gh` CLI is unauthenticated; chain-walker should surface remediation and halt the walk (**actionable-stop**). |
| 12 | `uv-missing` | `uv` is not installed/resolvable; chain-walker should surface remediation and halt the walk (**actionable-stop**). |
| 90 | `hard-dep-missing-non-tty` | A hard dep is missing in a non-interactive / non-TTY context and the override flag pair was not provided. |
| 91 | `double-confirm-declined-tty` | The user answered N to either of the two double-confirmation prompts under TTY. |
| 92 | `agent-direct-invocation-detected` | `--i-am-agent` was passed without the upstream's override-flag pair, OR agent-mode was detected via env. In a correctly-implemented v2 walker, **92 from an upstream dispatch is a walker-invocation bug, not an upstream install failure** — the walker built the command without composing override_flags. Surface as an internal walker error, not as a dep failure. |
| 93 | `override-flag-pair-incomplete` | Only one of the two override flags was provided. Both are required together. Same walker-bug interpretation as 92 when seen during an agent-mode walk. |

---

## Skill chain-walker

The setup skill (e.g., `/holodeck:setup`) is the agentic entry point. It walks the dependency chain dynamically, never consulting a cached or centrally-maintained registry.

**Important:** `setup_skill` in the manifest is informational metadata — it tells humans what to type. It is NOT the agent dispatch primitive. Dispatched subagents do not expand slash commands in their prompts. The canonical dispatch mechanism is: subagent + constructed prompt + standalone-script invocation.

### Walker composition (v2)

When the chain-walker iterates a consumer's `direct_deps` and dispatches a subagent to install an upstream, the constructed standalone-script invocation MUST be:

```
<upstream standalone_setup_script> \
  <consumer_install_args...> \      # from the consumer's DirectDep entry (may be empty)
  --i-am-agent \
  <upstream override_flags.skip_dep_check> \
  <upstream override_flags.accept_hallucination_risk>
```

Composition rules:

- **`consumer_install_args` come from the *consumer's* `DirectDep` entry for this upstream.** Mode + version selection only — never the upstream's gate-flag spelling.
- **`override_flags.*` are read from the *upstream's* manifest at dispatch time**, never literal-pinned in the consumer's manifest. Same schema key, different values across repos — the authority boundary depends on this.
- **`--i-am-agent` alone is exit 92.** In agent-mode chain-walk, bare `--i-am-agent` MUST always be accompanied by the upstream's override-flag pair. This makes the override flags an intrinsic property of agent-mode invocation, not a parallel mechanism.
- **Composition order is functionally irrelevant** — the standalone scripts parse all three in any order. The order above is for readability and consistency.

### Exit-code handling (Step 4 of the walker)

| Exit code | Walker classification | Action |
|---|---|---|
| 0 | `success` | Continue. |
| 11 / 12 | **actionable-stop** (upstream prerequisite missing on the host) | Surface remediation. Halt the walk. |
| 92 / 93 | **invocation bug** (walker built the command wrong) | Surface as an internal walker error, NOT an upstream install failure. With composition correctly implemented, these should be unreachable; if they fire, the composition logic regressed. |
| other non-zero | generic failure | Report last 20 lines of output; halt or continue per severity. |

### Constructed-prompt template

The chain-walker dispatches subagents using a rendered prompt template stored at a contracted path within each conforming repo:

```
scripts/lib/chain_walker_subagent_prompt.txt
```

(Path relative to the repo root. Each conforming repo stores its template at this contracted path so the dispatch mechanism is greppable.)

Template substitution variables:

| Variable | Value |
|---|---|
| `$UPSTREAM_ID` | The dep's `id` field from the manifest. |
| `$SIBLING_PATH` | The resolved absolute path of `../<sibling_dir_name>`. |
| `$SESSION_ID` | The UUID generated at top-level invocation start. |
| `$CONSUMER_INSTALL_ARGS` (v2+) | The space-joined `consumer_install_args` array from the consumer's `DirectDep` entry, or empty string if absent. |

The template instructs the subagent to: read the visited-set file (see below), check for the dep before cloning, append to visited-set before dispatching further subagents, compose the v2 invocation (`$CONSUMER_INSTALL_ARGS` + `--i-am-agent` + upstream override_flags), and recurse for the upstream's own `direct_deps`.

### Visited-set protocol

To handle diamond-DAG and cycle detection across recursive subagent dispatches (which share no EM context), the chain-walker uses a **disk-resident visited-set file** at:

```
~/.claude/<repo-id>/chain-walk-<session-id>.json
```

**Example (holodeck concrete example):** `~/.claude/holodeck/chain-walk-<session-id>.json`

**Why disk, not memory:** each dispatched subagent runs as an independent process with its own EM context. The parent EM's in-memory state is invisible to subagents. A visited-set held only in the parent's memory will not prevent a subagent from re-dispatching a dep the parent has already claimed — because the subagent has no parent-memory access. Disk is the only shared state that survives the process boundary.

#### Visited-set file schema

```json
{
  "session_id": "<uuid>",
  "started_at": "<ISO8601 timestamp>",
  "visited": ["<dep-id-1>", "<dep-id-2>"]
}
```

| Field | Type | Description |
|---|---|---|
| `session_id` | `string` (UUID) | Generated once at top-level invocation. Propagated to all recursive subagents via the constructed-prompt template (`$SESSION_ID` substitution variable). |
| `started_at` | `string` (ISO8601) | Timestamp of visited-set creation. Used for stale-file detection. |
| `visited` | `array<string>` | Dep IDs already claimed for walking. A dep found here is skipped — "already walking <id>, skipping". |

#### Lifecycle

1. **Top-level invocation start:** delete any `chain-walk-*.json` files in `~/.claude/<repo-id>/` older than 1 hour (stale-cleanup). Then create a new `chain-walk-<session-id>.json` with an empty `visited` array.
2. **Before each clone+walk:** read the visited-set file. If the dep ID is already in `visited`, log "already walking <dep-id>, skipping" and continue to the next dep.
3. **Before dispatching the subagent:** atomically append the dep ID to the `visited` array using a stdlib-only read-modify-write (Python `json` module — no `pyyaml` or other non-stdlib dep):
   ```
   python -c "import json, os, sys; p=sys.argv[1]; d=json.load(open(p)); d['visited'].append(sys.argv[2]); json.dump(d, open(p,'w'), indent=2)" <path-to-visited-set> <dep-id>
   ```
4. **Subagents** read the same file (path derived from `$SESSION_ID` passed in the constructed prompt) and follow steps 2–3 for their own deps.

#### Stale-cleanup

At top-level invocation start, delete `chain-walk-*.json` files older than 1 hour. This ensures a crashed or abandoned previous session does not block a new walk.

---

## Install-spinoff layer — durable multi-repo install under coordinator

> Added 2026-06-01. The §Skill chain-walker model dispatches recursive subagents within a single
> session. That holds for a short walk, but installing several repos in one vanilla session overruns
> its context — the first real field failure was exactly this: a session asked to install a whole
> chain lost the thread and looped. The install-spinoff layer makes a multi-leg install **durable**
> by handing the work to a coordinator-ified session that has a flight recorder, the Tasks API, and
> saved-to-disk handoffs/spinoffs. The recursive walker and this layer are not alternatives — the
> walker is how a single repo locates and probes its direct deps; this layer is how *several legs*
> are sequenced across the load-bearing coordinator reboot without losing state.

**The shape is one spine, N spinoffs** — exactly what `coordinator:roadmap-planning` produces.
Coordinator onboarding (`continue-onboarding-and-installation.md`) is the **handoff**: the genuine
continuation across the reboot, same workstream. Each *other* repo the operator queued is a
**spinoff**: a fork of a different install topic, `predecessor: none`. Continuation vs. fork — each
in its proper folder, each with its native semantics (no lineage exception to explain).

**Coordinator is standalone-first and chain-agnostic.** It installs and runs on its own; it is the
root that other repos *can* build on, not part of any mandatory chain. Coordinator knows exactly one
downstream by name — `deep-research`, its own bundled OSS add-on. Every other leg is whatever the
operator queued. Nothing in the coordinator surface hardcodes a particular chain, order, or leaf
repo — that knowledge lives in each downstream repo and arrives only as the spinoff that repo seeds.

### Authorization — the pre-restart question is the spinoff gate

Spinoffs are normally PM-authorized and keyword-gated (`/spinoff`); EM-initiated spinoffs are
forbidden (`docs/wiki/spinoff-handoffs.md`). Install-leg spinoffs are the **one sanctioned
non-`/spinoff` creation path**, and they do not erode that gate: the authorization is captured at the
install's **pre-restart question** ("what else do you want to install?"). The operator selecting a
leg there *is* the human authorizing that fork — the same authorization `/spinoff` captures, captured
at a different but equally explicit moment. A leg never appears as a spinoff unless the operator chose
it; the script merely materializes a choice the human already made. (Full carve-out: `spinoff-handoffs.md`.)

### The rendezvous: the standard handoff folder

```
~/.claude/tasks/handoffs/
```

Install legs are ordinary `/pickup`-valid **spinoffs** (`kind: spinoff`, `predecessor: none`) dropped
into the **standard handoff folder** — the *same* place `/spinoff` and `coordinator:roadmap-planning`
already write spinoffs. This is the load-bearing reason for the spinoff frame: `query-records --type
handoff` globs `tasks/handoffs/*.md`, `/pickup` Step 1.5 classifies a `kind: spinoff` file there as a
spinoff, and `/workday-start` surfaces it under "spinoffs awaiting pickup" — all unchanged. There is
**no new folder and no new convention**: a downstream repo's whole obligation is "drop a `kind:
spinoff` baton (carrying `install_chain_order:`) into `~/.claude/tasks/handoffs/`." The
`install_chain_order:` tag is what distinguishes an install leg from the coordinator onboarding
handoff in the same folder. They do not linger as stale batons because coordinator's Step 0 builds an
install-chain spine that drives every leg to conclusion before the install workstream is completed
(see `coordinator/templates/plans/install-chain-tracking.md`).

> Do **not** invent a `tasks/spinoffs/` (or `tasks/install-chain/`) directory: no coordinator
> machinery scans it, so a baton dropped there is invisible to `/pickup`, `query-records`, and
> `/workday-start`. The standard `tasks/handoffs/` folder is the only surface all three already read.

### Spinoff frontmatter contract

Each conforming repo seeds ONE spinoff per install leg, with `/pickup`-valid spinoff frontmatter plus
two install-chain fields:

| Field | Type | Required | Description |
|---|---|---|---|
| `repo` | `string` | yes | The leg's `repo_id` (matches the manifest). The spine key for the leg. |
| `install_chain_order` | `integer` | no | Relative install position (lower = installed earlier; coordinator = 0). The coordinator EM sorts the spine by this; **absent → discovered order**. Also the tag the Step 0 sweep greps to distinguish install legs from the onboarding handoff, so include it. |
| `plan` | `string` | no | Relative path to a leg plan file, when the leg warrants one. Plans live in the seeding repo's `docs/plans/`; the spinoff names the path. |

Base spinoff fields are required per the canonical spinoff schema (`spinoff-handoffs.md` § Frontmatter
schema): `title`, `created`, `kind: spinoff`, `status: active`, `predecessor: none`,
`authoring_session:` (the audit trail back to origin that replaces the predecessor link — for an
install leg, name the install + the operator's opt-in), `workstream:`, plus `deployment_state:
ready_to_fire`, `pickup_ready: true`, `scope:`. See
`coordinator/templates/handoffs/install-deep-research.md` for the reference shape.

### The two roles

- **Downstream repos SEED.** A conforming repo's installer drops its `kind: spinoff` baton into
  `~/.claude/tasks/handoffs/`. Seeding is a cheap `cp`/`sed`/`curl`, not a heavy install — it can run
  for every chosen leg *before* the coordinator reboot (per the pre-restart question in
  `agent-install.md`), so the durable session sees the whole chain at once. Idempotent
  (overwrite-on-reseed). Seed via `cp`/`sed`, **not the Write tool** — a Write into `tasks/handoffs/`
  without an active authoring skill trips the unauthorized-handoff nudge; `cp` does not.
  `deep-research` is the exception that proves the rule: it ships in the coordinator bundle, so
  coordinator seeds *its* spinoff from a shipped template
  (`templates/handoffs/install-deep-research.md`) rather than the DR repo seeding it — but the drop
  target and contract are identical.
- **Coordinator STITCHES + DRIVES.** Post-reboot, `continue-onboarding-and-installation.md` Step 0
  greps `tasks/handoffs/` for `install_chain_order:` legs, writes a lightweight install-chain spine
  listing every leg found, and drives each to conclusion via `/pickup`. This is the durability a
  vanilla session lacked — and it is agnostic: it tracks whatever spinoffs are present, asserting no
  fixed set.

### Guidance for conforming (downstream) repos

This is the "teach the other side in a wiki, don't code their ceremony" half of the contract (per
`cross-repo-communication.md` § When lifting a cross-repo primitive). To align:

1. Add a **seed step** to your standalone setup script that writes a `kind: spinoff` baton (with
   `repo`, `install_chain_order`, `authoring_session`) into `~/.claude/tasks/handoffs/` via `cp`/`sed`
   (not the Write tool). Idempotent. If coordinator is not yet installed, drop the spinoff first, then
   run the coordinator install — so it is waiting when the durable session starts.
2. If your leg needs a plan, write it to your `docs/plans/` and name it via the spinoff's `plan:`
   field.
3. Adopt the **coordinator-lite-before-reboot** pattern: verify a minimal coordinator surface (all
   pre-reboot dependencies present) before instructing the operator to restart, so the durable
   session can follow the coordinator-style pickup flow.
4. If your addon wants to supersede another repo's orientation, add `supersedes: <orientation-id>` to
   the spinoff baton you seed in step 1. Use the same `cp`/`sed` seeding discipline — **not the Write
   tool** — and seed before the coordinator reboot (same gate as step 1) so the baton is present when
   Step 0 builds the spine. Publish your own orientation as a normal spinoff leg. The superseded repo's
   orientation file is not modified; it remains the correct default when your baton is absent. Neither
   side codes the other's ceremony: your addon seeds the `supersedes:` assertion; coordinator's
   spine-builder resolves it at Step 0.

Coordinator owns only the agnostic stitch (sweep + spine + drive); each downstream repo owns its own
seeded spinoff and its own install steps. Neither side codes the other's ceremony.

### Orientation-supersession

An addon-seeded `kind: spinoff` baton MAY carry a `supersedes:` field to assert that its orientation
should be preferred over another repo's orientation **when that baton is present at spine-build time**.

```yaml
supersedes: <repo>-orientation   # e.g. project-rag-orientation
```

The value is an **orientation identifier** — an opaque id the superseded repo publishes. The
conventional form is `<repo>-orientation` (for example, `project-rag-orientation`), but that example
is illustrative; the coordinator treats the value as an opaque string and asserts no canonical form.
This keeps coordinator agnostic: no single consumer id reads as the reference shape.

**No new `kind`.** Orientation-supersession rides the existing `kind: spinoff` frame. The
`supersedes:` field is additive frontmatter on a normal install-leg spinoff. No new baton type,
no new folder, no new sweep.

**Conditional and live — this is the load-bearing semantic.** The superseded orientation is **never**
marked `status: superseded`, and there is **no** `superseded_by:` back-pointer written to it.
The superseded orientation remains the correct default when the declaring baton is absent. Supersession
is **resolved at spine-build time** (Step 0 of `coordinator/templates/handoffs/continue-onboarding-and-installation.md`)
by the presence or absence of the declaring baton in `tasks/handoffs/` — not by a status flip, not by
a pointer, not by a registry entry. Contrast this with the existing memo/handoff `status: superseded`,
which is a terminal mutation: the superseded artifact is dead and stays dead. Orientation-supersession
is different: it is live and conditional on baton presence. Removing or not seeding the baton restores
the default orientation exactly as if the field had never existed.

**Seed-before-reboot discipline.** A conforming repo that wants its baton to be in effect MUST seed it
**before** the coordinator reboot — the same pre-reboot seeding discipline already required for install
legs (§ Guidance for conforming repos, step 1). The install-chain spine is built once at Step 0 of the
durable session; a baton that arrives after Step 0 is not visible to the spine for that session.

**Legibility convention — `summary:` field.** Orientation legs SHOULD include the word "orientation"
in their `summary:` frontmatter field so the spine is human-readable at a glance (e.g.,
`summary: "project-rag orientation"`). The `supersedes:` field already carries the supersession
MECHANISM — this `summary:` note is legibility only. It is NOT a new mechanism and NOT a new `kind`.

### Provision sub-axis

Install, provision, and orient are three distinct sub-steps, not one monolithic phase:

- **Install** — the synchronous chain: fetch, wire, validate. Completes in one session. Gate-bound:
  the spine will not advance past an install leg that hasn't reached `status: complete`.
- **Provision** — long-running background work triggered by install (example: project-rag's
  ~1-hour index build). A slow provision step runs in the **background** and does **not** block
  the synchronous install chain. The spine does not wait on it; install completes, the session
  continues, and provision catches up asynchronously.
- **Orient** — the coordinator's first durable session after install; it **opens with co-writing
  `CLAUDE.md` together** (the first customization of the contract), then walks the operator through
  what was installed. See `continue-onboarding-and-installation.md` for the install → reload → orient
  flow.

**Per-leg state the spine tracks** reflects this three-step structure. A leg that has been installed
but whose background provision has not yet finished is in a distinct intermediate state:

| State | Meaning |
|---|---|
| `installed` | Synchronous chain complete; no background work pending |
| `installed / provisioning (ETA ~Xm)` | Synchronous chain complete; background provision in flight |
| `not-yet-oriented` | Install and provision complete; first-orient session not yet run |

The long-lived state a human-readable spine entry carries is one of these three — not the generic
"in progress" of the install phase. Conforming repos that trigger a slow provision step SHOULD
write their install-leg baton with an estimated ETA in the `provision_eta:` frontmatter field so
the spine can surface a human-readable estimate.

## Runtime vs. test-time validation

**Runtime** (Phase 0 manifest read in the standalone script): uses stdlib Python `json` module only. Validates structure shape minimally — presence of required top-level fields. No `jsonschema` import at runtime; `jsonschema` is NOT a runtime dependency.

**Test-time** (each conforming repo's `test_agent_install_contract.py` or equivalent): uses `jsonschema` to validate that repo's `agent-install-manifest.json` against its `agent-install-manifest.schema.json`. The `jsonschema` library is acceptable as a test-only dependency. The contract test also verifies that this doc's referenced semantics match the schema file's actual constraints (versions accepted, required fields, additive-only property changes between v1 and v2).

### JSON Schema for install-status.json

Each conforming repo's install-status ledger (e.g. `~/.claude/holodeck/install-status.json` in holodeck) is validated at read time by any consumer that imports it (doctor probes, recovery scripts). The validation uses JSON Schema Draft 2020-12.

**Strict unknown-property rejection.** Consumers MUST reject install-status.json objects with unknown top-level or phase-level properties loudly (raise / exit non-zero with a schema-violation message) rather than silently ignoring them. Silent-skip on unknown shapes masks schema drift across repo versions.

**Schema location:** Each repo stores its install-status schema at `docs/install/install-status.schema.json`. The repo's contract test verifies that the schema `$id` matches the file path; divergence fails CI.

**Draft 2020-12 gotcha — sibling_dir_exists then-block:** JSON Schema Draft 2020-12 has a known behavior difference from Draft 07 in `if`/`then`/`else` evaluation when `additionalProperties` is in the then-block. Verify schema behavior against the 2020-12 spec if extending the schema with conditional branches.

---

## v1 → v2 migration playbook

For consumers and upstreams adopting v2:

1. **Reader-widen first** (per repo, one commit): change the manifest reader's version check from `version == 1` to `version in {1, 2}`. Land + confirm green on both sides of every bilateral consumer/upstream pair.
2. **Schema mirror** (per repo, one commit): add the optional `consumer_install_args` array to `$defs/DirectDep`. Preserve `additionalProperties: false`. The `agent_install_contract_version` schema constraint widens to accept both values (the literal stays whatever the manifest declares).
3. **Manifest bump** (per repo, in lockstep with bilateral peer): flip the literal `agent_install_contract_version: 1` to `2`. Populate `consumer_install_args` for any `DirectDep` that needs mode/version selection (often a small subset of deps).
4. **Walker composition update** (per repo): update `scripts/lib/chain_walker_subagent_prompt.txt` to substitute `$CONSUMER_INSTALL_ARGS` and compose per §Walker composition. Update exit-code handling per §Exit-code handling.
5. **Contract test update** (per repo): assert v2 manifest validates; assert `consumer_install_args` is optional + forward-compatible (a v1-shaped manifest still passes under the v2 schema).

The reader-widen-first step is the install-surface-completeness trap if skipped — see §Versioning.

---

## Historical migration note

This contract was first authored and implemented in `claude-unreal-holodeck` (the chain leaf), bilaterally co-developed with `project-rag-ue-addon`, and migrated to `coordinator-claude` (the chain root) on **2026-05-23** as the ecosystem-wide canonical home. Prior to that date, the doc lived in `claude-unreal-holodeck/docs/wiki/agent-install-contract.md`.

Post-migration:
- This file at `~/.claude/plugins/coordinator/docs/wiki/agent-install-contract.md` (published outward via `setup/publish.sh` to consumer projects) is the single canonical source.
- `claude-unreal-holodeck/docs/wiki/agent-install-contract.md` becomes a one-line pointer redirect to this file.
- `project-rag-ue-addon` and other consumers (`project-rag`, `deep-research-claude`) cite this file rather than mirroring it.
- Per-repo `docs/install/agent-install-manifest.schema.json` files **stay in each repo** — the schema is the per-repo implementation of this contract; this doc is the contract spec. Moving schemas would change every `$id` URL and is deferred until a third consumer makes the duplication pressure obvious (current state: holodeck + addon are the only two repos with schemas).
- Doctrine for cross-repo doc moves of this shape: `~/.claude/plugins/coordinator/docs/wiki/cross-repo-communication.md` § Doctrine seeding vs. code/install-surface change.
