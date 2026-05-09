---
name: setup-percolate
description: Walk through registering a publish target, scaffolding .percolate-ignore, and scaffolding hook directories. Idempotent — re-runs detect what exists and scaffold what's missing.
triggers:
  - /setup-percolate
  - setup percolate
  - register publish target
  - configure percolation
argument-hint: "[<target-name>]"
version: 1.0.0
---

# /setup-percolate — Register a Publish Target and Scaffold Percolation Config

<!-- spec backlink: docs/plans/2026-05-08-percolation-improvements-surface-a.md § Component 3 -->

Idempotent setup skill for the percolation pipeline. Detects what already exists, scaffolds what's missing, never overwrites. Safe to re-run when adding a new publish target or checking that scaffolding is complete.

**Announce at start:** "Running `/setup-percolate` — detecting existing config, auditing what should and should not publish, scaffolding what's missing."

**First Officer obligation.** `.percolate-ignore` is a privacy/leakage boundary, not a scratch-file convention. The EM does NOT write a generic stub and call setup "done" — that creates a false sense of security and abrogates First Officer doctrine. Every invocation that touches `.percolate-ignore` (creation OR re-run-against-existing) MUST audit the source tree, classify entries, surface grey-zone items for explicit PM decision, and only then write/confirm the file. "Already exists, no changes made" is acceptable ONLY after a coverage-drift audit confirms the existing file still covers everything in the tree that shouldn't publish.

**Structural-vs-content split.** `.percolate-ignore` filters STRUCTURAL leaks — categories of paths (`__pycache__/`, `_archived/`, `tasks/handoffs/`, peer-runtime dirs). It cannot catch CONTENT leaks that accumulate during normal authoring: a name slipping into a wiki body, a peer-repo reference embedded in a snippet, a machine name in a code comment, a token pasted into an example. Content leaks are caught at publish time by `/percolate`'s Step 2c content-leakage scan (regex sweep over the about-to-publish file set, three severity tiers, panel surfaces to PM gate). Do NOT try to encode content scans here — they belong in `/percolate` because authoring drift is continuous and the static ignore file ages out of sync. The two skills divide labour: `/setup-percolate` catches structural categories once; `/percolate` re-scans content on every publish.

## When to Use / When NOT to Use

**Use `/setup-percolate` when:**
- Registering a new publish target for the first time on this machine.
- Scaffolding `.percolate-ignore` or hook directories for an existing target.
- `/percolate` emitted a "No `.percolate-ignore` found" nudge and you want to create one.
- Adding a second (or third) publish target to an existing `publish-targets.sh`.

**Do NOT use `/setup-percolate` when:**
- You want to *publish* files to a target — use `/percolate <target>` for that.
- You want to edit an existing registered target entry — edit `setup/publish-targets.sh` directly.
- You want general coordinator environment setup (git, env vars, plugins) — use `/setup` for that.

## What This Skill Does NOT Do

- Does **not** edit or overwrite existing entries in `publish-targets.sh` — append-only when adding.
- Does **not** run `/percolate` — setup only; publication is a separate invocation.
- Does **not** commit or push any scaffolded files — the PM commits when satisfied.
- Does **not** create the publish-repo itself or configure its remote — that's a one-time manual step.

---

## Step Sequence

### Step 1 — Detect or Scaffold `setup/publish-targets.sh`

Check whether `setup/publish-targets.sh` exists at the repo root:

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

Report the list to the PM. Proceed to Step 2.

**If it is missing:** check for the example file:

```bash
test -f setup/publish-targets.example.sh && echo "example_found" || echo "no_example"
```

- If the example exists: copy it into place and tell the PM to fill it in:
  ```bash
  cp setup/publish-targets.example.sh setup/publish-targets.sh
  ```
  Report: _"`setup/publish-targets.sh` was missing — copied from the example file. Open it and fill in your target entries before continuing. Re-run `/setup-percolate` after editing."_
  **Stop here** — the PM must edit the file before Step 2 can proceed meaningfully.

- If neither file exists: report that the repo does not appear to have a percolation setup yet, and offer to create a minimal stub:

  ```bash
  # setup/publish-targets.sh — stub created by /setup-percolate
  # Each TARGETS entry: "name|mode|source_dir|dest_dir"
  # mode: mirror (rsync full tree) or manifest (explicit list via publish-manifest.txt)
  TARGETS=()
  ```

  Ask the PM: _"No `setup/publish-targets.sh` or example found. Shall I create a minimal stub? [y/N]"_ Create only on confirmation. Either way, stop after this step and tell the PM to add a target entry before re-running.

---

### Step 2 — Walk PM Through Registering a Target

**If `$ARGUMENTS` names a target** (e.g. `/setup-percolate coordinator-claude`): check whether that target name already appears in `publish-targets.sh`. If it does, skip to Step 3 — no need to re-register.

**If no argument provided, or the named target is not yet registered:** walk the PM through the four fields:

Ask (one question, all four fields in a single prompt):

> I'll add a new target entry to `setup/publish-targets.sh`. I need four values:
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
Proposed entry:
  TARGETS+=("coordinator-claude|mirror|~/.claude/plugins/coordinator-claude/|~/code/coordinator-claude")

Add this to setup/publish-targets.sh? [y/N]
```

On confirmation, append to `setup/publish-targets.sh`:

```bash
TARGETS+=("<name>|<mode>|<source>|<dest>")
```

Report: _"Target `<name>` registered."_

---

### Step 3 — Audit + Author `.percolate-ignore` at the Source Plugin Root

Resolve `<source_dir>` from the TARGETS entry for the target being set up (the named argument, or the just-registered target from Step 2, or ask if ambiguous when multiple targets exist).

**No "default stub" path.** The EM never writes a 4-line generic ignore and moves on. Every code path through Step 3 produces an ignore file the EM has audited against the actual tree, with grey-zone items surfaced to PM for explicit decision.

Check whether `.percolate-ignore` already exists:

```bash
test -f "<source_dir>/.percolate-ignore" && echo "exists" || echo "missing"
```

#### Step 3a — Inventory the source tree

Regardless of whether the file exists, walk `<source_dir>` to ground the audit in reality:

```bash
ls -A "<source_dir>"                       # top-level entries (incl. dotfiles)
find "<source_dir>" -mindepth 1 -maxdepth 2 -type d | sort | head -100
find "<source_dir>" -maxdepth 3 -type f \( -name '*.json' -o -name '*.yml' -o -name '.env*' -o -name 'settings*' -o -name '.last-*' -o -name '*-status*' -o -name '*-profile*' \) | sort
```

Read suspicious-looking dirs more carefully (`tasks/`, `docs/`, `setup/`, `state/`, `.local*`, anything that looks like authoring scratch, install state, machine-config, or session memory).

**Dispatch a `general-purpose` Sonnet audit subagent when:** (a) the source tree has more than ~30 top-level entries, OR (b) it's a multi-plugin root (contains nested plugin directories), OR (c) the EM is uncertain about classifications after a 5-minute manual walk. The audit prompt MUST end with a `DONE: <path>` disk-verify clause and an explicit "Do NOT modify files. Read-only." block. Output goes to `~/.claude/tasks/scratch/percolate-ignore-audit-<target>-<YYYY-MM-DD>.md`.

For small single-purpose source trees (one skill bundle, ≤20 files), the EM may classify directly — but the classification step (3b) is non-optional even then.

#### Step 3b — Classify what was found

For every observed top-level path (and any second-level path that's load-bearing for the boundary call), assign one of:

- **PUBLISH** — canonical plugin payload that USERS need: skills, commands, agents, hooks, bin, lib, schemas, pipelines, snippets, README, CLAUDE.md (the plugin's), routing tables, capability catalogs, plugin-bundled `docs/wiki/`. Reference: `docs/wiki/plugin-extraction-and-distribution.md`.
- **IGNORE** — authoring/state/personal content that MUST NOT leak. Sub-buckets:
  - *personal-docs:* private wikis, internal-only notes
  - *session-state:* `tasks/handoffs/`, `tasks/lessons.md`, `tasks/distillation-log.md`, `tasks/review-trail/`, project trackers, daily-review logs, improvement queues, archived specs
  - *install-state:* `install-profile.json`, `install-status.json`, `.last-cleanup`, similar machine-local state
  - *machine-config:* `settings.json`, `settings.local.json`, `.mcp.json` containing secrets/tokens, environment-specific configs
  - *scratch:* `scratch/`, `_archived/`, `*.bak`, `*.tmp`, orphan `.tmp.<pid>.<nanos>` files
- **GREY ZONE** — flag explicitly. Examples that historically need PM judgment: `examples/`, `CONTEXT.md`, `ARCHITECTURE.md`, top-level READMEs, decision records (`docs/decisions/`), plan archives, anything under a name the EM doesn't recognize.

#### Step 3c — Surface grey-zone to PM for decision

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

#### Step 3d — Write the audited file

Compose the file with comment-grouped sections so future readers (and the next `/setup-percolate` re-run) can see the reasoning:

```
# .percolate-ignore — paths under this source plugin that should NOT publish.
# gitignore-shaped: directories with trailing /, file globs without.
# '**/' is not supported — multi-depth matches need explicit listing.
# Audited by /setup-percolate on YYYY-MM-DD against <source_dir>.

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

### Step 4 — Scaffold Hook Directories

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

### Step 5 — Summary and Next Step

Print a summary of what was created vs. already in place:

```
/setup-percolate <target> — DONE

  publish-targets.sh:    <created|already existed|target added|target already registered>
  .percolate-ignore:     <audited+written|audited+updated to close N gaps|kept existing (PM-confirmed coverage adequate)>
  pre-rsync/ dir:        <created|already existed>
  post-rsync/ dir:       <created|already existed>
  pre-ci/ dir:           <created|already existed>

Setup complete. Run `/percolate <target>` to publish.
```

If any step was skipped due to an existing artifact, note it explicitly so the PM can audit.
