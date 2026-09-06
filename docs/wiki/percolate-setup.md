---
name: percolate-setup
spec_backlink: archive/specs/2026-05/2026-05-09-skill-consolidation-pass.md
status: active
---

# Percolation Setup Procedure

<!-- spec backlink: archive/specs/2026-05/2026-05-09-skill-consolidation-pass.md § T4 -->

Canonical reference for the percolation setup procedure — registering a publish target, auditing `.percolate-ignore`, and scaffolding hook directories. This wiki is the single source of truth; both `/percolate` (Branch 0) and `/setup` (percolation phase) walk it inline.

**Consumers:**
- `/percolate` Branch 0 — fires on first run against an unconfigured target; skips silently on subsequent runs.
- `/setup` percolation phase — fires when the repo is detected as a percolation source with no registered targets.

## Fresh-install path

Earlier readers of this wiki could assume `~/.claude/setup/publish.sh` already existed (the Claude-Prime-clone case). The bash engine that file named is retired — the percolate entrypoint is now `coordinator/bin/publish.py`, migrated to claude-klabauter wholesale (commit b644d5a9 — see § PERCOLATE_ROOT and CLAUDE_KLABAUTER_ROOT below) rather than copied into `~/.claude/setup/`. What still arrives via the coordinator-claude install path on any consumer machine — operator-local files do too:

- `setup/install.sh` (publish-repo fresh-install entry point) AND `/coordinator:install` Phase 3 (ongoing maintenance, via `install-substrate.py`) install `publish_sync.py` and `.percolate-identity.example` into `~/.claude/setup/` (single source of truth for this file list: claude-klabauter's `coordinator/lib/setup-templates-manifest.py`, migrated from DoE, commit b644d5a9). `publish.py` itself is NOT among them — it is invoked from `$REPO_CLAUDE_KLABAUTER` (see § PERCOLATE_ROOT and CLAUDE_KLABAUTER_ROOT below), never copied. `publish-targets.example.sh` and `test-publish-allowlist-builder.sh` are absent from this list — the legacy-fallback `TARGETS=( ... )` shape is documented next to claude-klabauter's `coordinator/lib/percolate/targets.py`'s `_parse_legacy_targets_array`.
- Operator then registers targets (see Step 1a/1b/1c below — the tracked `setup/publish-targets.portable` topology is preferred, machine-local registry is a per-machine supplement, and `publish-targets.sh` is a deprecated legacy fallback).
- Operator authors `~/.claude/setup/.percolate-identity` from `.percolate-identity.example` with their own identity tokens.
- If org-slug rewrites are needed, operator copies claude-klabauter's `coordinator/bin/depersonalize-identity.example.yaml` (migrated from DoE, commit b644d5a9) to `depersonalize-identity.yaml` and edits it.

Spec backlinks:
- `docs/plans/2026-05-21-plugin-source-live-mirror-doctrine.md § Chunk 5` — `source_is_live` propagation model.
- `docs/wiki/coordinator-installer-shape.md § 2` — operator-local vs publish-target distinction (basis for non-circular framing).
- `docs/wiki/post-sync-hook-doctrine.md` — touched-file-list stdin contract for post-rsync hooks.

**Scaffold guards (prior-art entry — `**/` regression):**
- This wiki's header comment discloses the supported pattern subset: `**/` is NOT supported in `.percolate-ignore`. Directory patterns are already recursive without it.
- Before writing `.percolate-ignore`, walk the matcher against a fixture set (Step 3d) to verify patterns resolve as expected. Do not skip the pre-write verification pass.

---

## PERCOLATE_ROOT and CLAUDE_KLABAUTER_ROOT — Two Roots, Not One Four-Rung Chain

**Canonical env-var naming (DR-087, `docs/decisions/DR-087-repo-repo-id-env-override-family-ratified.md`):**
`REPO_CLAUDE_KLABAUTER` (registry key `repos.claude_klabauter`) is the ratified canonical name for
the claude-klabauter root override — new prose and invocations in this doc and elsewhere should
teach `REPO_CLAUDE_KLABAUTER` first. `CLAUDE_KLABAUTER_ROOT` is retained forever as a readable legacy alias
(`docs/decisions/DR-087-repo-repo-id-env-override-family-ratified.md` ruling 2 —
documentation-only, no rename, no removal schedule) and
this section's heading keeps its existing name because it is cited by exact heading text from
several other wikis; the heading is a stable citation anchor, not an endorsement of `CLAUDE_KLABAUTER_ROOT`
as the primary idiom.

**Percolate resolves two roots, never a single chain a caller re-derives by hand.**
`coordinator/bin/publish.py` and `coordinator/lib/percolate/*` (`targets.py`, `resolve_target.py`,
`ignore.py`, `allowlist.py`, `phase4_audit.py`) live in **claude-klabauter**; `setup/`
(`publish-targets.portable`, `percolate-hooks/`, `.percolate-identity`, `percolate-state/`) lives
in **DoE-claude** — see `CLAUDE.md`.

- **`PERCOLATE_ROOT`** — the percolate root of the invoking repo (`setup/...` paths are
  `"$PERCOLATE_ROOT/setup/..."`). Resolved by the engine's own ladder,
  `coordinator_core.percolate.runtime_root.coordinator_percolate_runtime_root()`
  (`claude-klabauter/coordinator_core/percolate/runtime_root.py`), reached through the seam every
  caller uses, per the precedence ladder in `coordinator/snippets/resolve-coordinator-bin.md`
  (rung 0 / Shape W on a PowerShell host; Shape A resolving `percolate-gate resolve-root` on a
  POSIX host). Callers never re-derive this ladder or read a pointer file directly — they call
  the seam and use its stdout. The engine's four rungs, first match wins:
  1. `$COORDINATOR_PERCOLATE_ROOT` env override, if it contains `setup/publish-targets.portable`.
  2. The cwd's git root, if it contains the marker — excluded when that root IS the shared-install
     path (rung 4), so resolution continues to rung 3 rather than colliding with it.
  3. The registry-first DoE-root pointer (`coordinator_core.doe_root_pointer.read_doe_root_pointer()`
     — registry key `repos.doe_claude`, then the durable pointer-file mirror, then the legacy
     pointer file), accepted only if it contains the marker.
  4. `${CLAUDE_HOME:-$HOME}/.claude`, if it contains the marker.
  On no rung resolving, the seam fails loud with the same remediation text `coordinator_percolate_runtime_root()` raises.
- **`CLAUDE_KLABAUTER_ROOT`** (called `$_cc_claude_klabauter` in the shell idiom below) — the claude-klabauter clone
  root. `coordinator/bin/...` / `coordinator/lib/...` paths (`publish.py`, `percolate.targets`)
  are `"$CLAUDE_KLABAUTER_ROOT/coordinator/bin|lib/..."`. Resolves from `$CLAUDE_KLABAUTER_ROOT`/`$REPO_CLAUDE_KLABAUTER`
  env, falling back to `coordinator/hooks/scripts/_engine_root.py` (a probe over the coordinator
  settings-home registry/pointer).

**Resolve both once per invocation** via `coordinator/skills/percolate/SKILL.md` § Step 0.5 — the
canonical reference implementation every `/percolate` step (and this doc's own dry-run commands
below) calls back to.

`publish.py` itself needs `PYTHONPATH="$CLAUDE_KLABAUTER_ROOT"` on invocation — its
`from coordinator.lib.percolate.resolve_target import ...` (via `targets.py`) is an absolute
import needing `$CLAUDE_KLABAUTER_ROOT` itself on `sys.path`, and the script only inserts `coordinator/lib`
relative to its own location, not its own root.

### The one-level-offset trap

Both the live-install tree (`~/.claude/plugins/coordinator-claude/`) and this source repo's
plugin tree are called "coordinator-claude" — same name, different depth. In the live install,
`~/.claude` itself is `PERCOLATE_ROOT` and `bin/machine-local` sits one level below it. In
DoE-claude, the plugin root is the `coordinator/` **subdirectory** of the repo, so the equivalent
CLI is at `coordinator/bin/machine-local` — one level further down than the shared-install case.

The Python port centralizes this instead of re-deriving it at each call site: every percolate
consumer that needs the machine-local CLI calls `resolve_machine_local_bin(root)`
(claude-klabauter's `coordinator/lib/percolate/resolve_target.py`), which tries in order:

1. `$MACHINE_LOCAL_BIN` (env override; SECURITY-validated absolute-path, no `..` traversal —
   raises rather than silently falling through on a failed check)
2. `<root>/bin/machine-local` — the shared-install (`~/.claude`) shape
3. `<root>/coordinator/bin/machine-local` — the DoE-claude repo-root shape
4. `machine-local` resolved from `PATH`

Project-claude-klabauter's `coordinator/lib/percolate/targets.py`'s `load_targets()` is the primary caller — it uses this
resolution both to check for a supplemental `publish.targets` registry key and (on `MACHINE_LOCAL_BIN`
SECURITY failure) to abort target resolution outright. When adding a new percolate call site that
needs the machine-local CLI, import and call `resolve_machine_local_bin` rather than hardcoding
either rung — the offset between the two trees is the single most common source of confusion in
this system, precisely because both are named "coordinator-claude."

### Verifying resolution on a fresh machine

A run that resolved correctly reports, for the `coordinator-claude` allowlisted target:

```
Allowlist enforcement: bin, lib, hooks, skills, agents, commands, docs/wiki/<name>.md (curated seed — the ratified count is whatever `coordinator/schemas/seed-wikis.json` carries, never a number quoted in prose), .claude-plugin, cockpit-contract/schema
Restricted source: <tmp path>
```

and does **not** print `machine-slug detection net is DOWN for '<target>'` (that warning fires
when `setup/.percolate-identity` is missing or its `PERSONAL_REVIEW_PATTERNS` array is empty —
see § Per-operator identity below). A run that instead reports "version-consistency gate not
found" or silently skips a target is not evidence of a clean run; both the gate-invocation
interpreter and the missing-gate-file path now fail closed by default (opt out only via
`COORDINATOR_OVERRIDE_VERSION_CONSISTENCY=1`).

## Per-operator identity — provisioning and the settings-home orphan

`.percolate-identity` (real machine codenames, used to build `PERSONAL_REVIEW_PATTERNS` for the
Phase 4 machine-slug audit) is per-operator and gitignored — it is never committed to any tracked
`setup/` tree. `publish.py` reads it from `setup_dir / ".percolate-identity"`
(`claude-klabauter/coordinator/bin/publish.py:1765`), where `setup_dir` is whatever its own
`resolve_percolate_root()` resolved — per § PERCOLATE_ROOT and CLAUDE_KLABAUTER_ROOT above, that self-resolution
is presently unreliable post-`b644d5a9`, so the file it actually reads on a given machine tracks
whatever `setup_dir` that section's hazard describes, not a guaranteed constant. In the working
model this doc otherwise assumes (`PERCOLATE_ROOT` = the DoE-claude clone root), provision it at
**`setup/.percolate-identity` at this repo's root** — copying
`coordinator/templates/setup/.percolate-identity.example` and populating
`PERSONAL_REVIEW_PATTERNS` with this machine's real codenames. This is a manual, per-operator step;
nothing in the installer can infer codenames it hasn't been told.

**Do not confuse this with `~/.coordinator-claude-settings/.percolate-identity`.** That file is a
distinct artifact from the older shared-install (`~/.claude`-rooted) topology: commit `2f534a6f`
ratified that its durable home is the **settings-home root**, not a `setup/` subdirectory
underneath it, and that nothing reads `.percolate-identity` from a `setup/` tree inside
settings-home. `~/.coordinator-claude-settings/setup/` is a **retired orphan** left over from
before that ratification — any copy of `publish-targets.portable` found there predates the
`cockpit-contract/schema` allowlist addition and must never be cited as a live surface
or used as a restore source. If you find that orphan `setup/` tree on a machine, its presence is
not evidence percolation needs it — the repo-local `setup/.percolate-identity` above is the file
`publish.py` is intended to source when run against this repo (subject to the resolution caveat
above).

## First Officer Obligation

`.percolate-ignore` is a **privacy/leakage boundary**, not a scratch-file convention. The EM does NOT write a generic stub and call setup "done" — that creates a false sense of security and abrogates First Officer doctrine. Every invocation that touches `.percolate-ignore` (creation OR re-run-against-existing) MUST:

1. Audit the source tree.
2. Classify entries (PUBLISH / IGNORE / GREY ZONE).
3. Surface grey-zone items for explicit PM decision via `AskUserQuestion`.
4. Only then write or confirm the file.

"Already exists, no changes made" is acceptable ONLY after a coverage-drift audit confirms the existing file still covers everything in the tree that shouldn't publish.

## Structural-vs-Content Split

`.percolate-ignore` filters **structural leaks** — categories of paths (`__pycache__/`, `_archived/`, `state/handoffs/`, peer-runtime dirs). It cannot catch **content leaks** that accumulate during normal authoring: a name slipping into a wiki body, a peer-repo reference embedded in a snippet, a machine name in a code comment, a token pasted into an example.

Content leaks are caught at publish time by `/percolate` Step 2c (content-leakage scan — regex sweep over the about-to-publish file set, three severity tiers, panel surfaces to PM gate). Do NOT try to encode content scans here — they belong in `/percolate` because authoring drift is continuous and the static ignore file ages out of sync.

The two surfaces divide labour: this procedure catches structural categories **once**; `/percolate` re-scans content on **every publish**.

---

## Codename Genericization at Publish Time

Internal sibling-repo codenames (`example-game-repo`, `example-sim-repo`, `example-cockpit-repo`, etc.) appear in coordinator wikis and skills as provenance or incident case-citations. Without remediation they leak private repo names to any OSS user who reads the publish tree. The content-transform sweep runs via claude-klabauter's `coordinator_core.percolate.engine` `depersonalize` hook — no operator action required.

### Built-in codename seed

**`coordinator/bin/codename-provenance-seed.sh` does not exist on disk.** The description below documents what the seed's replacement must cover, not a present file to inspect — treat it as the spec for the seed's content, not as a pointer to a live path.

The seed's content is:

- A `CODENAME_TO_PLACEHOLDER` assoc array and a `CODENAME_ORDERED_KEYS` indexed array seeded with coordinator-author private-repo codenames → `example-*-repo` placeholders (longest-match-first, case variants enumerated as separate keys per the `Dónal O'Duffy`/`Donal O'Duffy` committed precedent in the transform).
- Consumed by the **optional-sibling guard** (identical pattern to `depersonalize-identity.yaml`): `if [[ -f "$_SEED" ]]; then source "$_SEED"; fi`. The content-transform sweep runs via claude-klabauter's `coordinator_core.percolate.engine` `depersonalize` hook.
- **Does NOT ship to the OSS mirror.** Listed in `plugins/coordinator-claude/.percolate-ignore` (same entry form as `coordinator/bin/depersonalize-identity.yaml`). An OSS consumer who sources an absent file gets a silent no-op — identical to a fresh operator with no `depersonalize-identity.yaml`.

The seed is the home for **coordinator-authored repo codenames** (names that appear in coordinator wikis/skills as provenance) — NOT for an individual operator's own private project names, which belong in the per-operator gitignored `depersonalize-identity.yaml` (Class-2 slot). See `DoE-claude coordinator/docs/wiki/depersonalize-doctrine.md` § Codename Provenance for the vocabulary-vs-attribution classification that governs which surface owns what.

**Keep-set — not genericized.** `project-rag` (live MCP server namespace, accepted-exposure PM decision) and shipped plugin names (`deep-research`, `game-dev`, `web-dev`, `data-science`, `coordinator`) are intentionally absent from the seed map. Rewriting them would corrupt functional identifiers in agent definitions and skill routing tables. See `DoE-claude coordinator/docs/wiki/depersonalize-doctrine.md` § Codename Provenance for the keep-set rationale.

### Scan/Substitution Division of Labor

Two distinct gates defend against codename leaks — one for the expected case (codenames already in the map), one for the unexpected case (new private repos not yet mapped). This is the Scan/Substitution Division of Labor described in `plugin-extraction-and-distribution.md` § Scan/Substitution Division of Labor.

**Expected case — `--check` residual gate (mapped codenames only).** The `coordinator_core.percolate.engine` `depersonalize` hook's check mode greps the publish tree for the `PATTERN` built from `ORDERED_KEYS`. Once codenames appear in `CODENAME_ORDERED_KEYS`, any residual occurrence post-`--fix` fails loud. **Scope limit:** `--check` detects only codenames already in `ORDERED_KEYS`. A genuinely-new private repo cited in a new wiki entry passes `--check` clean — `PATTERN` is built from the existing map keys, not from the full registry. The novel-leak guard below closes this gap.

**Unexpected case — registry-derived novel-leak guard.** `coordinator_core.ops.check_registry_codename_leak` is the coverage for the `coordinator-claude` and `deep-research-claude` targets, resolved into the round through the store's guard rows (`setup/percolate-hooks/percolate-store.yaml`, `claude-klabauter`). It:

1. Reads every `repos.*` key from the machine-local registry (`machine-local keys | grep '^repos\.'`).
2. Subtracts the keep-set (`project-rag`, `deep-research`, `game-dev`, `web-dev`, `data-science`, `coordinator`).
3. For each remaining key, derives the prose codename form: strips `repos.` prefix → slug; converts `_`→`-` → hyphenated form (e.g. `example_cockpit_repo` → `example-cockpit-repo`); greps the publish tree for **both** forms case-insensitively (`grep -ri`). **Bare underscore-slug grep alone is insufficient** — registry keys use underscores but prose codenames use hyphens; every multi-word codename has this skew (`example_stats_repo`/`example-stats-repo`, `example_repo`/`example-repo`); grepping only the underscore form silently passes the exact leak class the guard exists to catch.
4. Fails loud (non-zero exit) if any hit is found — the codename is not yet in the seed map.

This guard derives its codename set from data that already exists (the machine-local registry), catches a genuinely-new private repo citation before it ships, and requires no human awareness of the omission. It is the complement to `--check`: `--check` is a post-fix residual gate for mapped codenames; the registry guard is a pre-ship novel-leak gate for unmapped ones.

### Operator action

**None required for built-in codenames.** The seed fires at every publish via the
`coordinator_core.percolate.engine` `depersonalize` hook, and the registry guard fires at publish
time from its store guard row. Operators author and configure nothing.

**If a new private sibling repo is later cited in a coordinator wiki:** the registry guard will catch it at publish time and fail loud. The fix is to add the new codename and placeholder to the seed that replaces `coordinator/bin/codename-provenance-seed.sh` (confirm the current location before acting — see § Built-in codename seed) and commit it. This is an EM engineering call; no per-operator file changes are needed for coordinator-authored codenames.

---

## Announce at Start

When walking this procedure, open with:

> "Setting up percolation for target `<target>` — detecting existing config, auditing what should and should not publish, scaffolding what's missing."

---

## Step 1 — Detect or Scaffold the Publish Target Registry

> **Python-port 3-tier resolution.** The detection logic below mirrors `coordinator/lib/percolate/targets.py`'s `load_targets()` (spec backlink: `docs/plans/2026-06-22-portable-registry-resolved-publish-targets.md`; port: `docs/plans/2026-07-21-percolate-python-port.md`). The tracked `setup/publish-targets.portable` topology is the PRIMARY tier; the machine-local registry `publish.targets` key is a per-machine SUPPLEMENT (dedup'd by target name against the portable tier); the deprecated `setup/publish-targets.sh` bash-array file is a LEGACY fallback, consulted only if the first two tiers together resolve nothing.

The wizard checks for publish target configuration in preference order, mirroring the runtime in `coordinator/bin/publish.py` (via `load_targets`):

### Step 1a — Check the tracked portable topology first (primary path)

```bash
test -f setup/publish-targets.portable && echo "exists" || echo "missing"
```

`setup/publish-targets.portable` is a tracked, machine-agnostic file of pipe-delimited rows — safe to commit because it carries only dest-key sigils and relative subdirs, never absolute paths:

```
name|mode|<dest-sigil>|source_subdir|dest_subdir[|native_slugs[|allowlist]]
```

- `mode` — `mirror` | `flat-mirror` | `manifest`
- `<dest-sigil>` — `repo:<key>` (working-repo dest, resolved via `machine-local get repos.<key>`) or `publish-mirror:<key>` (OSS-mirror dest, resolved via `machine-local get publish.mirrors.<key>.path`)
- `source_subdir` — meta-repo-relative path, or a `plugin-source:<key>[/subpath]` sigil (registry-resolved, falling back to `<meta-root>/plugins/<key>[/subpath]`)
- `dest_subdir` — subdirectory inside the dest repo; empty means repo root
- `native_slugs` (optional) — comma-separated marketplace slugs treated as expected content by the personal-data audit
- `allowlist` (optional) — comma-separated source subpaths; when set, `publish.py` builds a fail-closed restricted temp source tree containing ONLY the listed subpaths

**If the file exists and has rows:** report to the PM:

> _"Publish targets are configured via the tracked `setup/publish-targets.portable` topology. No action needed — the runtime is already wired. Skipping scaffolding."_

List the registered rows (name, mode, resolved dest sigil) and proceed directly to Step 2 without any scaffold action.

### Step 1b — Check the machine-local registry supplement

Independent of Step 1a's result, `load_targets()` also folds in any per-machine `publish.targets` registry key (rows here dedup against the portable tier by target name — first tier wins on a name collision):

```bash
machine-local has publish.targets
```

**If the key is set (exit 0):** report to the PM that supplemental per-machine targets are present, and list them alongside the portable-tier rows from Step 1a.

Proceed to Step 2.

### Step 1c — Neither present: scaffold, or fall back to legacy

If `setup/publish-targets.portable` is absent (or empty) AND `machine-local has publish.targets` is non-zero, the wizard offers to scaffold. **By default, scaffold a new row in the tracked portable file.** The deprecated `setup/publish-targets.sh` bash-array path is available behind an explicit `--legacy` flag for operators whose existing tooling (scripts, CI) does not yet know about the portable topology — `load_targets()` only reaches this legacy tier if steps 1a+1b together resolved nothing, and prints a `DEPRECATED` warning to stderr when it does.

**Default (portable-file scaffold):**

Ask the PM:

> _"No publish target configuration found. Shall I add a row to the tracked `setup/publish-targets.portable`? [y/N] (Use `--legacy` to scaffold the deprecated `setup/publish-targets.sh` instead.)"_

On `y`, prompt for the four target fields (same as Step 2), then append a row in the `name|mode|<dest-sigil>|source_subdir|dest_subdir` shape shown in Step 1a.

Report: _"Row appended to `setup/publish-targets.portable`."_

**Legacy scaffold (`--legacy` flag):**

Ask the PM:

> _"No `setup/publish-targets.sh` or example found. Shall I create a minimal stub? [y/N]"_

On `y`, create:

```bash
# setup/publish-targets.sh — DEPRECATED stub created by percolation setup.
# Migrate to setup/publish-targets.portable (tracked) or the machine-local
# registry publish.targets key — see docs/wiki/machine-local-registry.md.
# Each TARGETS entry: "name|mode|source_dir|dest_dir"
# mode: mirror (rsync full tree) or manifest (explicit list via publish-manifest.txt)
TARGETS=()
```

Report: _"Legacy `setup/publish-targets.sh` stub created. Fill in target entries before continuing. Note: the tracked `setup/publish-targets.portable` file is the preferred primary — see `docs/wiki/machine-local-registry.md`."_

Either way, stop after this step and tell the PM to add a target entry before re-running.

---

### Wizard-rerun scenario reference

| Scenario | `setup/publish-targets.portable` | `machine-local has publish.targets` | `publish-targets.sh` | Wizard outcome |
|---|---|---|---|---|
| **(a)** Portable topology configured | present, non-empty | either | present or absent | Reports "configured via portable topology, no action needed"; skips scaffolding entirely |
| **(b)** Machine-local supplement only | absent/empty | exit 0 (key set) | present or absent | Reports supplemental per-machine targets present; no scaffolding |
| **(c)** Legacy fallback in use | absent/empty | exit 1 (key not set) | present | Lists targets; reports "legacy fallback, runtime works, migrate when convenient" |
| **(d)** Neither source present | absent/empty | exit 1 (key not set) | absent | Scaffolds the portable file by default; `--legacy` flag scaffolds `publish-targets.sh` instead |

---

## Step 2 — Walk PM Through Registering a Target

**If `$ARGUMENTS` names a target** (e.g. `/percolate coordinator-claude`): check whether that target name already appears in `setup/publish-targets.portable`, the machine-local registry (`machine-local get publish.targets`), or the legacy `publish-targets.sh`. If found in any, skip to Step 3 — no need to re-register.

**If no argument provided, or the named target is not yet registered:** walk the PM through the four fields.

Default registration target is **the tracked `setup/publish-targets.portable` file (canonical)** per Step 1c. The deprecated `publish-targets.sh` path is reachable via `--legacy` only.

Ask (one question, all four fields in a single prompt):

> I'll add a new row to `setup/publish-targets.portable`. I need four values:
>
> 1. **Target name** — a short slug (e.g. `coordinator-claude`, `my-plugin`). Used as the argument to `/percolate`.
> 2. **Sync mode** — `mirror` (rsync the full source tree), `flat-mirror` (rsync into a dest subdirectory), or `manifest` (explicit list via `publish-manifest.txt`). Most plugin publishes use `mirror`.
> 3. **Source path** — the meta-repo-relative source subdir you're publishing FROM (e.g. `plugin-source:coordinator-claude`), or an absolute path if not resolvable via a registry sigil. This is where `.percolate-ignore` will live.
> 4. **Destination** — the `publish-mirror:<key>` or `repo:<key>` sigil for the local clone of the publish repo (e.g. `publish-mirror:coordinator_claude`, resolved via `machine-local get publish.mirrors.coordinator_claude.path`).
>
> Please provide all four, or type `cancel` to abort.

Wait for PM input. On `cancel`, exit 0 with "Setup cancelled."

Once values are collected, show the proposed row and ask for confirmation:

```
Proposed row (setup/publish-targets.portable):
  coordinator-claude|mirror|publish-mirror:coordinator_claude|plugin-source:coordinator-claude||

Append this row to setup/publish-targets.portable? [y/N]
```

On confirmation, append the row to the tracked file (and remind the PM that the `publish-mirror:`/`repo:` sigil must already resolve via `machine-local get`, per § PERCOLATE_ROOT and CLAUDE_KLABAUTER_ROOT above, before a real publish will succeed).

Report: _"Target `<name>` registered in `setup/publish-targets.portable`."_

**`--legacy` flag** — appends to `setup/publish-targets.sh` instead (per Step 1c). Use only when the operator explicitly requests the legacy path (e.g. migrating an existing fleet):

```bash
TARGETS+=("<name>|<mode>|<source>|<dest>")
```

---

## Step 3 — Audit + Author `.percolate-ignore` at the Source Plugin Root

Resolve `<source_dir>` from the row registered for the target being set up (`setup/publish-targets.portable`, the machine-local registry supplement, or the legacy `publish-targets.sh` — whichever tier resolved it; the named argument, or the just-registered target from Step 2, or ask if ambiguous when multiple targets exist).

**No "default stub" path.** The EM never writes a 4-line generic ignore and moves on. Every code path through Step 3 produces an ignore file the EM has audited against the actual tree, with grey-zone items surfaced to PM for explicit decision.

Check whether `.percolate-ignore` already exists:

```bash
test -f "<source_dir>/.percolate-ignore" && echo "exists" || echo "missing"
```

### Step 3a — Inventory the source tree

Regardless of whether the file exists, walk `<source_dir>` to ground the audit in reality:

```bash
ls -A "<source_dir>"                       # top-level entries (incl. dotfiles)
find "<source_dir>" -mindepth 1 -maxdepth 2 -type d | sort | head -100
find "<source_dir>" -maxdepth 3 -type f \( -name '*.json' -o -name '*.yml' -o -name '.env*' -o -name 'settings*' -o -name '.last-*' -o -name '*-status*' -o -name '*-profile*' \) | sort
```

Read suspicious-looking dirs more carefully (`tasks/`, `docs/`, `setup/`, `state/`, `.local*`, anything that looks like authoring scratch, install state, machine-config, or session memory).

**Dispatch a `general-purpose` Sonnet audit subagent when:** (a) the source tree has more than ~30 top-level entries, OR (b) it's a multi-plugin root (contains nested plugin directories), OR (c) the EM is uncertain about classifications after a 5-minute manual walk. The audit prompt MUST end with a `DONE: <path>` disk-verify clause and an explicit "Do NOT modify files. Read-only." block. Output goes to `~/.claude/tasks/scratch/percolate-ignore-audit-<target>-<YYYY-MM-DD>.md`.

For small single-purpose source trees (one skill bundle, ≤20 files), the EM may classify directly — but the classification step (3b) is non-optional even then.

### Step 3b — Classify what was found

For every observed top-level path (and any second-level path that's load-bearing for the boundary call), assign one of:

- **PUBLISH** — canonical plugin payload that USERS need: skills, commands, agents, hooks, bin, lib, schemas, pipelines, snippets, README, CLAUDE.md (the plugin's), routing tables, capability catalogs, plugin-bundled `docs/wiki/`. Reference: `docs/wiki/plugin-extraction-and-distribution.md`.
- **IGNORE** — authoring/state/personal content that MUST NOT leak. Sub-buckets:
  - *personal-docs:* private wikis, internal-only notes
  - *session-state:* `state/handoffs/`, `state/lessons/`, `state/distillation-log.md`, `state/review-trail/`, project trackers, daily-review logs, improvement queues, archived specs
  - *install-state:* `install-profile.json`, `install-status.json`, `.last-cleanup`, similar machine-local state
  - *machine-config:* `settings.json`, `settings.local.json`, `.mcp.json` containing secrets/tokens, environment-specific configs
  - *scratch:* `scratch/`, `_archived/`, `*.bak`, `*.tmp`, orphan `.tmp.<pid>.<nanos>` files
- **GREY ZONE** — flag explicitly. Examples that historically need PM judgment: `examples/`, `CONTEXT.md`, `ARCHITECTURE.md`, top-level READMEs, decision records (`docs/decisions/`), plan archives, anything under a name the EM doesn't recognize.

### Step 3c — Surface grey-zone to PM for decision

Before writing the file, present a structured framing:

```
.percolate-ignore audit for target '<target>' — source: <source_dir>

Classified PUBLISH (will sync — N entries): <compact list>
Classified IGNORE (will be excluded — N entries, grouped by sub-bucket): <list>
GREY ZONE (need your call):
  - <path> — <one-line reason it's ambiguous>
  - <path> — <reason>
  ...
```

Use `AskUserQuestion` (multiSelect) to collect publish/ignore decisions on the grey-zone list. Do NOT default-resolve grey items silently.

If `.percolate-ignore` already exists, ALSO show:
- Its current content.
- A diff: "Patterns the existing file DOES cover: ...  Coverage gaps the audit found: ..."
- Ask: _"Update existing `.percolate-ignore` to close these gaps? [y/N]"_ A `n` answer is acceptable but must be explicit — the existing file is then preserved with no edits, and Step 5's summary reports `kept existing (PM-confirmed coverage adequate)`.

### Step 3d — Write the audited file

**Scaffold guard — pre-write matcher walk:** Before writing, verify each pattern resolves correctly against the inventory from Step 3a. For each non-trivial pattern (directory suffix `/`, extension glob `*.ext`), confirm at least one inventory entry would match. Patterns that match nothing are not errors (prophylactic exclusions are valid), but patterns that were intended to match something but don't (e.g., wrong path depth) must be corrected before writing.

**Pattern subset reminder:** `**/` is NOT supported. Multi-depth matches need explicit listing. Directory patterns (trailing `/`) are already recursive — they match the directory at any depth in the source tree.

**Coordinate-system reminder (mirror mode, multi-plugin source roots):** in `publish_sync.py::sync_mirror`, patterns are matched against the **SOURCE_DIR-relative (plugin-qualified) path** — e.g. `coordinator/bin/tests/`, `data/` — NOT the sub-plugin-relative path. Author patterns with the sub-plugin name prefix when the source root contains multiple plugins (`coordinator/`, `data/`, `web-dev/`…). A pattern at the wrong root (`bin/tests/` when you meant `coordinator/bin/tests/`, or vice-versa) is a **silent no-op** — the exclusion never fires and the files leak. The 2026-05-30 leak of operator-identity + runtime-state files onto the public OSS repo was exactly this class. Claude-klabauter's `coordinator/tests/test_percolate_allowlist_ignore_propagation.py` regression test now fails loud on a dead pattern; the Step 3d pre-write matcher walk is the author-time guard.

Compose the file with comment-grouped sections so future readers (and the next re-run at Branch 0 / `/setup`) can see the reasoning:

```
# .percolate-ignore — paths under this source plugin that should NOT publish.
# gitignore-shaped: directories with trailing /, file globs without.
# '**/' is not supported — multi-depth matches need explicit listing.
# Audited by /percolate Branch 0 on YYYY-MM-DD against <source_dir>.

# --- Authoring scratch ---
_archived/
scratch/
*.bak
*.tmp

# --- Session state (handoffs, lessons, trackers, review trail) ---
<entries>

# --- Install / machine state ---
<entries>

# --- Personal docs / internal notes ---
<entries>

# --- PM-decided grey-zone exclusions ---
<entries>
```

Show the proposed body to the PM and ask for final confirmation before writing. On `y`, write the file. On `n`, report what would have been written and exit without overwriting.

Report what changed: _"`.percolate-ignore` written/updated at `<source_dir>/.percolate-ignore` with N total patterns across M categories, audited against <count> source-tree entries on <date>."_

---

## Step 4 — Scaffold Hook Directories

Resolve `<target_name>` (same as Step 3). The hook base is `setup/percolate-hooks/<target_name>/`.

For each of the three hook points — `pre-rsync`, `post-rsync`, `pre-ci` — check whether the directory exists and create it with a `.gitkeep` if missing:

```bash
for hook_point in pre-rsync post-rsync pre-ci; do
  dir="setup/percolate-hooks/<target_name>/$hook_point"
  if [[ -d "$dir" ]]; then
    echo "  $hook_point/  already exists"
  else
    mkdir -p "$dir"
    touch "$dir/.gitkeep"
    echo "  $hook_point/  created"
  fi
done
```

Report which directories were created vs. already in place.

Note to PM: _"Hook directories are empty by default. Place executable `*.sh` scripts in any hook directory to register them. `publish.py` discovers and runs them in lexical order. See `docs/wiki/plugin-extraction-and-distribution.md` for hook contract details (arguments, stdin, failure semantics)."_

---

## Step 5 — Drift Detection on Existing `.percolate-ignore`

**This step applies when `.percolate-ignore` already exists and the gate in Branch 0 / `/setup` detected coverage gaps (i.e., setup is running because hook dirs were absent, not because the ignore file was missing).**

After the hook scaffolding in Step 4, perform a drift check: are there source-tree entries that have appeared since the ignore file was last audited?

```bash
find "<source_dir>" -type f -newer "<source_dir>/.percolate-ignore" | sort | head -50
```

If the result is non-empty, surface under a "Coverage drift since last audit:" panel:

```
Coverage drift since last audit (<date from ignore file header>):
  New files / dirs since last percolate-ignore audit:
    <path>
    <path>
    ...

Re-audit recommended. Run /percolate <target> — Branch 0 will re-evaluate.
```

For each new path, classify it (PUBLISH / IGNORE / GREY ZONE) using the same taxonomy as Step 3b. Present grey-zone additions via `AskUserQuestion` (multiSelect) and offer to append new IGNORE entries to the existing file.

If no new files are found since the last audit: report `"Coverage drift check: clean — no new files since last audit."` and proceed.

---

## Step 5 (Summary) — Summary and Next Step

Print a summary of what was created vs. already in place:

```
Percolation setup for <target> — DONE

  publish-targets.portable:  <row added|target already registered|legacy publish-targets.sh created (--legacy)>
  .percolate-ignore:         <audited+written|audited+updated to close N gaps|kept existing (PM-confirmed coverage adequate)>
  pre-rsync/ dir:        <created|already existed>
  post-rsync/ dir:       <created|already existed>
  pre-ci/ dir:           <created|already existed>

Setup complete. Run `/percolate <target>` to publish.
```

If any step was skipped due to an existing artifact, note it explicitly so the PM can audit.

---

## Failure Modes

| Failure | Symptom | Recovery |
|---|---|---|
| `setup/publish-targets.portable` missing, no machine-local supplement, no legacy file | Step 1 exits after stub-creation prompt | Add a row to the portable file (default) or scaffold `publish-targets.sh` via `--legacy`; re-run |
| Target not registered in any of the three tiers | Step 2 prompts for registration; cannot auto-detect source path | Provide all four fields at the prompt |
| Source path does not exist | Step 3 `ls -A` returns empty or error | Verify `<source_dir>` in the resolved target row |
| PM declines grey-zone item write | `.percolate-ignore` not written; step exits with proposed content shown | PM edits manually or re-runs with explicit decisions |
| Hook dir creation fails (permissions) | `mkdir -p` exits non-zero | Fix permissions at `setup/percolate-hooks/`; re-run (Step 4 is idempotent) |
| Pattern in `.percolate-ignore` uses `**/` | Matcher silently ignores the pattern (unsupported syntax) | Replace with explicit directory listing or remove `**/` prefix |
| Drift check finds no ignore file | `find -newer` returns nothing (file missing, not just no drift) | Treat as missing; run full Step 3 audit |
| Sonnet audit subagent TEXT-ONLY failure | Deliverable not written to disk; subagent returned summary inline | Re-dispatch with `snippets/text-only-recovery-preamble.md`; verify `DONE: <path>` |
| Partial hook scaffold (dirs partially created) | Some `pre-rsync`/`post-rsync`/`pre-ci` present, others missing | Step 4 is idempotent — re-run; it creates missing dirs and skips existing ones |

---

## Known Hazards

**`/percolate` dry-run file-count is inflated by the depersonalization-delta — not a signal of real changes.** A dry-run may report 200+ "UPDATE" files when the real run syncs only 2-3 genuinely-changed files and re-depersonalizes the rest (the dest is already depersonalized; the source is not, so every file reads as "changed" in a naive diff). Percolate scope is what the dest repo's working tree shows after the real run, not the dry-run UPDATE count. The content-leakage scan result (0 hits) is the real safety signal.

*Note on depersonalize scope:* the depersonalize hook strips identity tokens (Dónal/oduffy/paths) but does NOT convert reviewer-persona display names (the Staff Engineer/the Game Dev Reviewer/the Data Science Reviewer/the Front-End Reviewer/the UX Reviewer/the Director of Engineering) to role labels — that is a separate `check-persona-names` CI gate. When editing `dist/publish-repo-toplevel/` or any OSS-shipped doc, use role labels, not persona names, or CI will catch it.

*Source: meta-repo `state/lessons/`.*

**Fail-closed publish allowlist silently strips new top-level dirs.** Re-homing a package into DoE is NOT sufficient to make percolate ship it — the coordinator-claude mirror row carries a fail-closed allowlist (`bin,lib,hooks,skills,agents,commands,docs/wiki,.claude-plugin` — `docs/wiki` here is illustrative of the *shape*; it is narrowed to a curated seed, see below), and a new top-level dir absent from that allowlist is silently dropped. The re-home *looks* done but the mirror won't carry it. Detection: always run `python "$CLAUDE_KLABAUTER_ROOT/coordinator/bin/publish.py" --dry-run` (`publish.py` migrated to claude-klabauter in `b644d5a9`) and grep the write-set to confirm the new dir appears before declaring the re-home complete. Fix: add the dir to the allowlist in `~/.claude/setup/publish-targets.portable`. (This is the allowlist twin of the `.percolate-ignore` denylist hazards above — one gate ships what's listed, the other blocks what's listed; both fail silently when a path is mis-classed.)

**The OSS mirror ships a curated wiki SEED, not the whole `docs/wiki/` tree — a bare `docs/wiki` allowlist entry is the drift, not a fix** (PM ruling, `docs/decisions/DR-080-oss-mirror-publishes-a-curated-seed-wiki-not-the-whole-tree.md`). Left unchecked, the public `coordinator-claude` mirror's deliberate curated seed silently drifts toward publishing every wiki, because nobody re-narrows the allowlist as new wikis are authored — the admission bar quietly goes from "curated" to "everything by default." Read this before ever widening a wiki allowlist entry back to a bare `docs/wiki`:

- **Admission bar: "stable conceptual core that does not move often."** Adding a wiki to the seed is a **DR-080 amendment** — a ratified decision, never a default and never an opportunistic add during unrelated work. Every wiki looks universal to its author; that pull is exactly the counter-pressure that produced the 200-wiki drift. A soft bar is the failure mode, not an edge case of it.
- **THE TRAP — two rows publish wikis in `~/.claude/setup/publish-targets.portable`, and both must move together.** The `coordinator-claude|mirror` row's field-7 allowlist and the `coordinator-claude-toplevel-wiki|flat-mirror` row's allowlist are independent lists over the same source tree. Narrowing only one changes nothing observable in the mirror — the other row still ships the full tree unrestricted. A fix that looks correct after editing one row and changes nothing in the published set is the primary failure mode here.
- **Verify against the round's own published set, never by reading the config.** Reading the allowlist and confirming it "looks narrow" does not prove the mirror agrees — the second row is invisible unless you check the actual write-set. Diff the round's wiki entries against the seed before declaring a narrowing complete.
- **Allowlist entries are exact-path, per-entry — not a prefix match or a glob.** File-level entries (`docs/wiki/rag-bait-conventions.md`) work standalone; there is no shorthand for "this directory except these files."
- **An allowlist entry naming a file that does not exist is silently skipped** — publishing nothing for that entry, with no error. A typo'd seed filename drops a wiki from the mirror with zero signal.
- **`task-tier-guidance.md` is publish-native, not source-tracked** — authored mirror-side, absent from this DoE source tree, restored by the post-rsync hook allowlist (`setup/percolate-hooks/coordinator-claude-toplevel-wiki/post-rsync/publish-native-allowlist.txt`), not by either publish-target allowlist. Do not add it to a publish-target allowlist as a "fix" for its apparent absence — that changes nothing; the published-wiki total is 8, the two publish-target allowlists carry 7.
- **A second, untracked copy of the allowlist file can silently govern the real publish.** `setup/publish-targets.portable` is tracked in *this* repo, but `publish.py` actually reads whichever copy sits beside it at `$PERCOLATE_ROOT/setup/`, and per § PERCOLATE_ROOT and CLAUDE_KLABAUTER_ROOT above, rung 4 (`${CLAUDE_HOME:-$HOME}/.claude`) is the usual winner on both macOS and Windows when no repo-local clone or DoE-root pointer resolves first — a live-install copy, not this DoE-source one. Narrowing the seed here changes nothing on a typical publish run unless that live copy is narrowed too; see the residual gap noted in DR-080 §Consequences.

**One-way mirror percolate silently reverts direct edits in publish repo** (self). The mirror step overwrites publish-repo content from source without checking whether the publish repo has received direct edits (e.g., a hotfix applied while the source repo was out of reach). Any commit in the publish repo that post-dates the last percolate run is silently deleted by the next mirror pass. Detection step: before running the mirror, run `git log --since=<last-percolate-sha> -- <synced-paths>` in the publish repo; if non-empty, surface to PM before proceeding. Implementation: add this check to `/percolate` before the mirror/rsync step fires.

**An empty-but-present restricted-source top-level dir does not trip the orphan sweep — the per-file delete loop still walks it and destroys real mirror content.** `sync_mirror`'s top-level orphan-plugin-dir sweep only fires when a dir is *absent* from the restricted source; when the dir exists but is *empty*, the sweep is silent and phase-2's per-file delete loop takes over — it walks every file already present under that dir in the mirror and deletes each one as unmatched-against-source, because the restricted source has nothing to match it against. This is a general bug class in `sync_mirror`, not specific to `bin`/`lib` — any top-level dir that goes hollow at the source while the mirror still carries content from before the migration is exposed to it.

**Concrete instance, mitigated.** `coordinator/bin/` and `coordinator/lib/` are present-but-empty in this repo — zero tracked files, `.percolate-ignore` preserves nothing under either. The `coordinator-claude|mirror` row carries a `source_map` composing `bin`/`lib` from claude-klabauter's `coordinator/` alongside everything else from this repo's `coordinator/`, so those dirs are populated in the composed restricted source and the per-file delete loop does not treat them as empty.

- **Detection — the dry-run write-set diff, not the config.** Run `python "$CLAUDE_KLABAUTER_ROOT/coordinator/bin/publish.py" --dry-run coordinator-claude` (or the skill's Step 2 `percolate-gate`/`percolate-parse-dryrun` path) and grep the write-set for `DELETE` entries under `bin/` or `lib/`. A non-empty hit list under either path now indicates a `source_map` misconfiguration or a fresh instance of this bug class on a different dir, not a normal drift signal — cross-check the composed write-set against `git ls-files coordinator/bin coordinator/lib | wc -l` in this repo (currently `0`, expected, now that those dirs are claude-klabauter-sourced) before trusting any dry-run read.
- **The general lesson still applies to any newly-hollowed top-level dir.** The natural instinct on seeing a mirror that looks behind is to re-run `/percolate` and let it catch up — for a dir that has gone hollow at the source without a compensating `source_map` entry, that is precisely the action that fires the phase-2 delete loop. A stale-looking dir in the mirror is not evidence the publish is behind; check whether the source went hollow before republishing.
- **The naive two-row split (one DoE-sourced row minus bin/lib, one claude-klabauter-sourced row with only bin/lib, same mirror destination) is UNSAFE, not merely incomplete** — verified by tracing `sync_mirror`'s orphan-dir sweep against the actual row/allowlist arithmetic. Two mirror-mode rows sharing one destination root evaluate "orphan" per-row, with no cross-row awareness of a sibling row publishing into the same dest; whichever row's restricted source lacks a given top-level dir treats it as orphaned and `shutil.rmtree`s it, and neither ordering of the two rows escapes this (percentage math against the mass-deletion guard threshold puts a bin/lib-added-back row's own dirs safely under the 50% guard, so it fires with no protection). Do not reach for this shape as a self-service fix.
- **Real fix's shape.** `build_allowlisted_source` (`claude-klabauter/coordinator/lib/percolate/allowlist.py`) is multi-source-aware: it composes per-root `.percolate-ignore` files, applies copy-time ignore filtering per contributing root, runs an entry-collision preflight before any copy, and `assert_allowlist_applied` takes a root set rather than a single root — so one publish row pulls `bin/`+`lib/` from claude-klabauter's `coordinator/` while pulling everything else from this repo's `coordinator/`, in a single `sync_mirror` call with one coherent orphan-sweep view. A pre-rsync staging-merge alternative is rejected as a shape: it would re-implement the fail-closed source-construction gate a second time, and break `assert_allowlist_applied`'s post-condition. The `coordinator-claude|mirror` row in `setup/publish-targets.portable` carries a `source_map` field routing `bin,lib` to `plugin-source:claude-klabauter/coordinator` (see that file's header for the field's semantics and why `plugin-source:` rather than `repo:` was chosen). The `source_map` field is live, not a fallback to `real_src`. The regression gate `coordinator/tests/test_publish_allowlist_source_populated.py` is `source_map`-aware — it resolves each allowlist entry against its actual contributing root rather than assuming everything lives under this repo's `coordinator/`. A fail-loud top-level-presence guard against the destructive delete path lives in `DoE-claude/setup/publish_sync.py` (and its `coordinator/templates/setup/` parity copy): it fires on ANY non-empty orphan set, reuses `COORDINATOR_OVERRIDE_ORPHAN_SWEEP=1` as its override, and preserves dry-run-never-aborts. **Before any real publish under this engine: `--dry-run`, read the diff, and treat the OSS mirror commit as staged for human review before push** — a first-of-kind run against a stale mirror can delete and add hundreds of files in one shot, which is not a diff anyone should push unreviewed.

**Multi-source composition — per-root `.percolate-ignore`, and a failure mode this introduces.** Once a row's `source_map` names ≥2 distinct contributing roots, single-source's tolerant "absent `.percolate-ignore` is fine" behaviour does not apply to that row. Each contributing root must carry its own `.percolate-ignore`; a root with none aborts the build rather than publishing unfiltered (this is deliberate — see `coordinator/.percolate-ignore`'s block, which points bin/lib exclusion authorship at `claude-klabauter/coordinator/.percolate-ignore` rather than this file). A composed ignore file is written at the restricted-source root for the destination-side orphan/delete-skip logic, built by keeping each root's rules for its own entries plus any root-agnostic basename/glob pattern; a rule from one root naming a path the other root doesn't contribute must never be allowed to shadow that path in the other root's tree. Single-source rows (no `source_map`, or every value equal) are byte-for-byte unaffected — this paragraph does not change behaviour for any row except the multi-source ones.

**Top-level presence invariant — restated for multi-source rows specifically.** The general invariant (below) already governs every mirror row: a top-level dir present at the destination and absent from the restricted source is deleted by the orphan sweep regardless of `.percolate-ignore`, because the sweep never consults it. Multi-source rows do not get a pass on this — the restricted-source tree the sweep evaluates is the *composed* tree after all contributing roots have copied in, so a top-level dir is safe only if *some* contributing root actually populates it. An entry-collision preflight (no two source_map entries may resolve to the same or a nesting restricted-tree path across roots) runs before any copy, so a same-name collision between two roots aborts loudly rather than one root silently shadowing the other.

*Source: `state/subagent-share/41c1917d-53d5-49f9-9e70-cf281768cc5d/coordinatorexecutor-ce8e8bec.md`; regression gate at `coordinator/tests/test_publish_allowlist_source_populated.py`; evidence commits `b644d5a9`, `8a28a6ca`.*

## Vocabulary and schema renames — OSS mirror consequence

**Occasion:** DR-084 (`docs/decisions/DR-084-handoff-lifecycle-vocabulary-overhaul-open-claimed-continued-closed.md`) renamed handoff-lifecycle vocabulary (`owner`→`repo_owner`, `consumed`→`claimed`, `abandoned`→`closed`/`continued`) and added fields to `coordinator/schemas/handoff.schema.json`. Several of those plans mutate percolation-source files under `coordinator/` without stating the OSS-mirror consequence. Verified:

- **`skills/`, `commands/`, `agents/` are default-inclusive** under the `coordinator-claude|mirror` row's fail-closed allowlist (`setup/publish-targets.portable`, field 7 — those three dirs are listed wholesale, not per-file). A vocabulary rename *inside* an already-listed directory needs **no new allowlist entry** — it is a content edit within an already-published path, not the "new top-level dir silently dropped" hazard documented above (that hazard is about admitting a *new path*, not editing an existing one). It ships on the next real `/percolate` run automatically.
- **`coordinator/schemas/handoff.schema.json` is NOT in the allowlist at all** (no `schemas` entry exists — only the unrelated `cockpit-contract/schema` path is listed). The new/renamed schema fields do not reach the OSS mirror today, renamed or not — this is a pre-existing gate, not something the rename changes. Adding `schemas` to the allowlist would be a deliberate scope-widening call (DR-080-shaped), out of scope of a vocabulary rename.
- **`docs/wiki/**` is gated by the curated `publish-targets.portable` allowlist (two rows, both must move together per DR-080's THE TRAP note above), NOT by `.percolate-ignore`.** `handoff-tracker-system.md` and `spinoff-handoffs.md` — the wikis most likely to document the new vocabulary — are absent from the current 7-wiki seed and will not publish even after editing, until explicitly added to both rows as a ratified DR-080 amendment.
- **`.percolate-ignore` patterns are SOURCE_DIR-relative and carry no `coordinator/` prefix** (see this file's header) — a stray `coordinator/schemas/` pattern would double-prefix and silently match nothing. Not relevant here since no `.percolate-ignore` edit is needed, but worth restating so the next author doesn't reach for this file reflexively.

**Verdict: no `.percolate-ignore` or `publish-targets.portable` action required for the vocabulary rename itself.** The one open item is a separate, PM-gated decision (not urgent, not caused by the rename): whether `coordinator/schemas/` should ever join the allowlist so schema consumers get the new fields.
