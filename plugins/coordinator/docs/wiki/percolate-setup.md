---
name: percolate-setup
spec_backlink: docs/plans/2026-05-09-skill-consolidation-pass.md
status: canonical
---

# Percolation Setup Procedure

<!-- spec backlink: docs/plans/2026-05-09-skill-consolidation-pass.md § T4 -->

Canonical reference for the percolation setup procedure — registering a publish target, auditing `.percolate-ignore`, and scaffolding hook directories. This wiki is the single source of truth; both `/percolate` (Branch 0) and `/setup` (percolation phase) walk it inline.

**Consumers:**
- `/percolate` Branch 0 — fires on first run against an unconfigured target; skips silently on subsequent runs.
- `/setup` percolation phase — fires when the repo is detected as a percolation source with no registered targets.

## Fresh-install path

Earlier readers of this wiki could assume `~/.claude/setup/publish.sh` already existed (the Claude-Prime-clone case). It now arrives via the coordinator-claude install path on any consumer machine — operator-local files do too:

- `setup/install.sh` (publish-repo fresh-install entry point) AND `/coordinator:setup` Phase 3 (ongoing maintenance, via `install-substrate.sh`) install `publish.sh`, `publish_sync.py`, and `publish-targets.example.sh` into `~/.claude/setup/`.
- Operator then registers targets (see Step 1a/1b/1c below — machine-local is preferred, `publish-targets.sh` is legacy).
- Operator authors `~/.claude/setup/.percolate-identity` from `.percolate-identity.example` with their own identity tokens.
- If org-slug rewrites are needed, operator copies `~/.claude/plugins/coordinator/bin/depersonalize-identity.sh.example` to `depersonalize-identity.sh` and edits it.

Spec backlinks:
- `docs/plans/2026-05-21-plugin-source-live-mirror-doctrine.md § Chunk 5` — `source_is_live` propagation model.
- `docs/wiki/coordinator-installer-shape.md § 2` — operator-local vs publish-target distinction (basis for non-circular framing).
- `docs/wiki/post-sync-hook-doctrine.md` — touched-file-list stdin contract for post-rsync hooks.

**Scaffold guards (prior-art entry 2026-05-08 — `**/` regression):**
- This wiki's header comment discloses the supported pattern subset: `**/` is NOT supported in `.percolate-ignore`. Directory patterns are already recursive without it.
- Before writing `.percolate-ignore`, walk the matcher against a fixture set (Step 3d) to verify patterns resolve as expected. Do not skip the pre-write verification pass.

---

## First Officer Obligation

`.percolate-ignore` is a **privacy/leakage boundary**, not a scratch-file convention. The EM does NOT write a generic stub and call setup "done" — that creates a false sense of security and abrogates First Officer doctrine. Every invocation that touches `.percolate-ignore` (creation OR re-run-against-existing) MUST:

1. Audit the source tree.
2. Classify entries (PUBLISH / IGNORE / GREY ZONE).
3. Surface grey-zone items for explicit PM decision via `AskUserQuestion`.
4. Only then write or confirm the file.

"Already exists, no changes made" is acceptable ONLY after a coverage-drift audit confirms the existing file still covers everything in the tree that shouldn't publish.

## Structural-vs-Content Split

`.percolate-ignore` filters **structural leaks** — categories of paths (`__pycache__/`, `_archived/`, `tasks/handoffs/`, peer-runtime dirs). It cannot catch **content leaks** that accumulate during normal authoring: a name slipping into a wiki body, a peer-repo reference embedded in a snippet, a machine name in a code comment, a token pasted into an example.

Content leaks are caught at publish time by `/percolate` Step 2c (content-leakage scan — regex sweep over the about-to-publish file set, three severity tiers, panel surfaces to PM gate). Do NOT try to encode content scans here — they belong in `/percolate` because authoring drift is continuous and the static ignore file ages out of sync.

The two surfaces divide labour: this procedure catches structural categories **once**; `/percolate` re-scans content on **every publish**.

---

## Announce at Start

When walking this procedure, open with:

> "Setting up percolation for target `<target>` — detecting existing config, auditing what should and should not publish, scaffolding what's missing."

---

## Step 1 — Detect or Scaffold the Publish Target Registry

> **2026-05-19 amendment — machine-local precedence.** The detection logic below was updated to mirror the preference order in `setup/publish.sh`'s `_load_targets` function (spec backlink: `docs/plans/2026-05-19-machine-local-registry.md § 5 Task 5b`). Machine-local registry is the primary path; `publish-targets.sh` is the legacy fallback; scaffolding now defaults to machine-local and offers legacy behind `--legacy`.

The wizard checks for publish target configuration in preference order, mirroring the runtime in `setup/publish.sh`:

### Step 1a — Check machine-local registry first (primary path)

```bash
machine-local has publish.targets
```

**If the key is set (exit 0):** report to the PM:

> _"Publish targets are configured via the machine-local registry (`publish.targets` key in `~/.claude/machine-local/`). No action needed — the runtime is already wired. Skipping scaffolding."_

Proceed directly to Step 2 without any scaffold action.

### Step 1b — Fall back to `setup/publish-targets.sh` (legacy path)

If `machine-local has publish.targets` returns non-zero (key not set), check for the legacy file:

```bash
test -f setup/publish-targets.sh && echo "exists" || echo "missing"
```

**If it exists:** source it in a sub-shell and list all registered targets:

```bash
bash -c '
  source setup/publish-targets.sh
  for t in "${TARGETS[@]}"; do
    IFS="|" read -r name mode src dest <<< "$t"
    echo "  $name ($mode)  $src  →  $dest"
  done
'
```

Report the list to the PM and note the legacy path is in use:

> _"Publish targets are configured via the legacy `setup/publish-targets.sh`. The runtime works — no immediate action required. When convenient, consider migrating to the machine-local registry: add a `publish.targets` key to `~/.claude/machine-local/registry.toml` (see `docs/wiki/machine-local-registry.md`). The current setup keeps working until you migrate."_

Proceed to Step 2.

### Step 1c — No source present: scaffold (machine-local by default)

If neither source is present, the wizard offers to scaffold. **By default, scaffold machine-local.** The legacy `publish-targets.sh` path is available behind an explicit `--legacy` flag for operators whose existing tooling (scripts, CI) does not yet know about machine-local.

**Default (machine-local scaffold):**

Ask the PM:

> _"No publish target configuration found. Shall I add a `publish.targets` entry to `~/.claude/machine-local/registry.toml`? [y/N] (Use `--legacy` to scaffold `setup/publish-targets.sh` instead.)"_

On `y`, open `~/.claude/machine-local/registry.toml` and prompt for the four target fields (same as Step 2), then append:

```toml
"publish.targets" = ["<name>|<mode>|<source_dir>|<dest_dir>"]
```

Report: _"`publish.targets` key added to machine-local registry."_

**Legacy scaffold (`--legacy` flag):**

Ask the PM:

> _"No `setup/publish-targets.sh` or example found. Shall I create a minimal stub? [y/N]"_

On `y`, create:

```bash
# setup/publish-targets.sh — stub created by percolation setup
# Each TARGETS entry: "name|mode|source_dir|dest_dir"
# mode: mirror (rsync full tree) or manifest (explicit list via publish-manifest.txt)
TARGETS=()
```

Report: _"Legacy `setup/publish-targets.sh` stub created. Fill in target entries before continuing. Note: the machine-local registry (`publish.targets` key) is now the preferred primary — see `docs/wiki/machine-local-registry.md`."_

Either way, stop after this step and tell the PM to add a target entry before re-running.

---

### Wizard-rerun scenario reference

| Scenario | `machine-local has publish.targets` | `publish-targets.sh` | Wizard outcome |
|---|---|---|---|
| **(a)** Machine-local configured | exit 0 (key set) | present or absent | Reports "configured via machine-local, no action needed"; skips scaffolding entirely |
| **(b)** Legacy fallback in use | exit 1 (key not set) | present | Lists targets; reports "legacy fallback, runtime works, migrate when convenient" |
| **(c)** Neither source present | exit 1 (key not set) | absent | Scaffolds machine-local by default; `--legacy` flag scaffolds `publish-targets.sh` instead |

---

## Step 2 — Walk PM Through Registering a Target

**If `$ARGUMENTS` names a target** (e.g. `/percolate coordinator-claude`): check whether that target name already appears in either the machine-local registry (`machine-local get publish.targets`) or the legacy `publish-targets.sh`. If found in either, skip to Step 3 — no need to re-register.

**If no argument provided, or the named target is not yet registered:** walk the PM through the four fields.

Default registration target is **`~/.claude/machine-local/` (canonical)** per Step 1c. The legacy `publish-targets.sh` path is reachable via `--legacy` only.

Ask (one question, all four fields in a single prompt):

> I'll add a new target entry to the machine-local registry (`~/.claude/machine-local/`). I need four values:
>
> 1. **Target name** — a short slug (e.g. `coordinator-claude`, `my-plugin`). Used as the argument to `/percolate`.
> 2. **Sync mode** — `mirror` (rsync the full source tree) or `manifest` (explicit list via `publish-manifest.txt`). Most plugin publishes use `mirror`.
> 3. **Source path** — absolute path to the directory you're publishing FROM (e.g. `~/.claude/plugins/coordinator-claude/`). This is where `.percolate-ignore` will live.
> 4. **Destination path** — absolute path to the local clone of the publish repo (e.g. `~/code/coordinator-claude`).
>
> Please provide all four, or type `cancel` to abort.

Wait for PM input. On `cancel`, exit 0 with "Setup cancelled."

Once values are collected, show the proposed entry and ask for confirmation:

```
Proposed entry (machine-local registry):
  publish.targets.coordinator-claude = "mirror|~/.claude/plugins/coordinator-claude/|~/code/coordinator-claude"

Add this to ~/.claude/machine-local/registry.local.toml? [y/N]
```

On confirmation, write via the registry CLI:

```bash
machine-local set "publish.targets.<name>" "<mode>|<source>|<dest>"
```

Report: _"Target `<name>` registered in machine-local registry."_

**`--legacy` flag** — appends to `setup/publish-targets.sh` instead (per Step 1c). Use only when the operator explicitly requests the legacy path (e.g. migrating an existing fleet):

```bash
TARGETS+=("<name>|<mode>|<source>|<dest>")
```

---

## Step 3 — Audit + Author `.percolate-ignore` at the Source Plugin Root

Resolve `<source_dir>` from the TARGETS entry for the target being set up (the named argument, or the just-registered target from Step 2, or ask if ambiguous when multiple targets exist).

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
  - *session-state:* `tasks/handoffs/`, `tasks/lessons.md`, `tasks/distillation-log.md`, `tasks/review-trail/`, project trackers, daily-review logs, improvement queues, archived specs
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

Note to PM: _"Hook directories are empty by default. Place executable `*.sh` scripts in any hook directory to register them. `publish.sh` discovers and runs them in lexical order. See `docs/wiki/plugin-extraction-and-distribution.md` for hook contract details (arguments, stdin, failure semantics)."_

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

  publish-targets.sh:    <created|already existed|target added|target already registered>
  .percolate-ignore:     <audited+written|audited+updated to close N gaps|kept existing (PM-confirmed coverage adequate)>
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
| `setup/publish-targets.sh` missing, no example | Step 1 exits after stub-creation prompt | Fill in stub or copy example; re-run |
| Target not in `publish-targets.sh` | Step 2 prompts for registration; cannot auto-detect source path | Provide all four fields at the prompt |
| Source path does not exist | Step 3 `ls -A` returns empty or error | Verify `<source_dir>` in the TARGETS entry |
| PM declines grey-zone item write | `.percolate-ignore` not written; step exits with proposed content shown | PM edits manually or re-runs with explicit decisions |
| Hook dir creation fails (permissions) | `mkdir -p` exits non-zero | Fix permissions at `setup/percolate-hooks/`; re-run (Step 4 is idempotent) |
| Pattern in `.percolate-ignore` uses `**/` | Matcher silently ignores the pattern (unsupported syntax) | Replace with explicit directory listing or remove `**/` prefix |
| Drift check finds no ignore file | `find -newer` returns nothing (file missing, not just no drift) | Treat as missing; run full Step 3 audit |
| Sonnet audit subagent TEXT-ONLY failure | Deliverable not written to disk; subagent returned summary inline | Re-dispatch with `snippets/text-only-recovery-preamble.md`; verify `DONE: <path>` |
| Partial hook scaffold (dirs partially created) | Some `pre-rsync`/`post-rsync`/`pre-ci` present, others missing | Step 4 is idempotent — re-run; it creates missing dirs and skips existing ones |

---

## Known Hazards

**One-way mirror percolate silently reverts direct edits in publish repo** (2026-05-16 self). The mirror step overwrites publish-repo content from source without checking whether the publish repo has received direct edits (e.g., a hotfix applied while the source repo was out of reach). Any commit in the publish repo that post-dates the last percolate run is silently deleted by the next mirror pass. Detection step: before running the mirror, run `git log --since=<last-percolate-sha> -- <synced-paths>` in the publish repo; if non-empty, surface to PM before proceeding. Implementation: add this check to `/percolate` before the mirror/rsync step fires.
