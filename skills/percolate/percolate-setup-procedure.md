# Percolation Setup Procedure

Interactive walk for registering a new publish target, auditing what should and should not
publish, and scaffolding per-target hook directories. `/percolate` Branch 0 runs this walk the
first time a target is invoked and is unconfigured; it is silently skipped on every subsequent
run against that target.

**Announce at start:**

> "Setting up percolation for target `<target>` — detecting existing config, auditing what
> should and should not publish, scaffolding what's missing."

---

## Step 1 — Detect or Scaffold the Publish Target Registry

Target configuration resolves in two tiers, checked in order:

### Step 1a — Tracked portable topology (primary)

```bash
test -f setup/publish-targets.portable
```

(Exit 0 means the file exists; non-zero means it's missing.)

`setup/publish-targets.portable` is a tracked, machine-agnostic file of pipe-delimited rows —
safe to commit because it carries only dest-key sigils and relative subdirs, never absolute
paths:

```
name|mode|<dest-sigil>|source_subdir|dest_subdir[|native_slugs[|allowlist]]
```

- `mode` — `mirror` | `flat-mirror` | `manifest`
- `<dest-sigil>` — `repo:<key>` (working-repo dest, resolved via `machine-local get repos.<key>`)
  or `publish-mirror:<key>` (OSS-mirror dest, resolved via
  `machine-local get publish.mirrors.<key>.path`)
- `source_subdir` — meta-repo-relative path, or a `plugin-source:<key>[/subpath]` sigil
- `dest_subdir` — subdirectory inside the dest repo; empty means repo root
- `native_slugs` (optional) — comma-separated marketplace slugs treated as expected content by
  the personal-data audit
- `allowlist` (optional) — comma-separated source subpaths; when set, the runtime builds a
  fail-closed restricted temp source tree containing ONLY the listed subpaths

**If the file exists and has rows:** report — _"Publish targets are configured via the tracked
`setup/publish-targets.portable` topology. No action needed — skipping scaffolding."_ List the
registered rows (name, mode, resolved dest sigil) and proceed to Step 2 (below, the audit step)
without any scaffold action.

### Step 1b — Machine-local registry supplement

Independent of Step 1a's result, a per-machine `publish.targets` registry key can supply
additional rows (deduplicated against the portable tier by target name — first tier wins on a
name collision):

```bash
machine-local has publish.targets
```

If set, report that supplemental per-machine targets are present and list them alongside the
portable-tier rows. Proceed to Step 2.

### Step 1c — Neither present: scaffold a new row

If `setup/publish-targets.portable` is absent (or empty) AND no machine-local supplement is set,
offer to scaffold a new row in the tracked portable file:

> _"No publish target configuration found. Shall I add a row to the tracked
> `setup/publish-targets.portable`? [y/N]"_

On `y`, walk the PM through the four fields below (same as Step 2), then append a row and report:
_"Row appended to `setup/publish-targets.portable`."_ On `n`, stop and tell the PM to add a
target entry before re-running.

### Step 2 — Walk the PM Through Registering a Target

**If a target name was already resolved and already appears** in `setup/publish-targets.portable`
or the machine-local registry supplement, skip straight to Step 3 (the audit) — no need to
re-register.

**Otherwise**, ask (one question, all four fields in a single prompt):

> I'll add a new row to `setup/publish-targets.portable`. I need four values:
>
> 1. **Target name** — a short slug (e.g. `my-plugin`). Used as the argument to `/percolate`.
> 2. **Sync mode** — `mirror` (rsync the full source tree), `flat-mirror` (rsync into a dest
>    subdirectory), or `manifest` (explicit list). Most plugin publishes use `mirror`.
> 3. **Source path** — the source subdir you're publishing FROM. This is where
>    `.percolate-ignore` will live.
> 4. **Destination** — the `publish-mirror:<key>` or `repo:<key>` sigil for the local clone of
>    the publish repo.
>
> Please provide all four, or type `cancel` to abort.

On `cancel`, exit with "Setup cancelled." Otherwise show the proposed row and confirm before
appending:

```
Proposed row (setup/publish-targets.portable):
  <name>|<mode>|<dest-sigil>|<source_subdir>||

Append this row to setup/publish-targets.portable? [y/N]
```

On confirmation, append the row and remind the PM that the destination sigil must already
resolve via `machine-local get` before a real publish will succeed. Report: _"Target `<name>`
registered in `setup/publish-targets.portable`."_

---

## Step 3 — Audit + Author `.percolate-ignore` at the Source Plugin Root

**`.percolate-ignore` is a privacy/leakage boundary, not a scratch-file convention.** Never write
a generic stub and call setup "done" — that creates a false sense of security. Every invocation
that touches `.percolate-ignore` (creation OR re-run-against-existing) MUST:

1. Audit the source tree.
2. Classify entries (PUBLISH / IGNORE / GREY ZONE).
3. Surface grey-zone items for explicit PM decision.
4. Only then write or confirm the file.

"Already exists, no changes made" is acceptable ONLY after a coverage-drift audit confirms the
existing file still covers everything in the tree that shouldn't publish.

Resolve `<source_dir>` from the row just registered (or the row that already named this target).
Check whether `.percolate-ignore` already exists:

```bash
test -f "<source_dir>/.percolate-ignore"
```

(Exit 0 means the file exists; non-zero means it's missing.)

### Step 3a — Inventory the source tree

Regardless of whether the file exists, walk `<source_dir>` to ground the audit in reality.
First, the top-level listing:

```bash
ls -A "<source_dir>"
```

Then the directory tree, two levels deep (sort and cap the output yourself when reading — each
fence below is a single command):

```bash
find "<source_dir>" -mindepth 1 -maxdepth 2 -type d
```

Then config-shaped files that often carry machine state or secrets:

```bash
find "<source_dir>" -maxdepth 3 -type f \( -name '*.json' -o -name '*.yml' -o -name '.env*' -o -name 'settings*' -o -name '.last-*' -o -name '*-status*' -o -name '*-profile*' \)
```

Read suspicious-looking dirs more carefully (anything that looks like authoring scratch, install
state, machine-config, or session memory).

Dispatch a read-only, general-purpose Sonnet audit subagent when: (a) the source tree has more
than ~30 top-level entries, OR (b) it's a multi-plugin root (contains nested plugin
directories), OR (c) classification is uncertain after a 5-minute manual walk. The audit prompt
must end with an explicit disk-verify pointer and a "Do NOT modify files. Read-only." block. For
small single-purpose source trees (one skill bundle, ≤20 files), classify directly — but Step 3b
is non-optional even then.

### Step 3b — Classify what was found

For every observed top-level path (and any second-level path load-bearing for the boundary
call), assign one of:

- **PUBLISH** — canonical plugin payload that USERS need: skills, commands, agents, hooks, bin,
  lib, schemas, pipelines, snippets, README, the plugin's own CLAUDE.md, routing tables,
  capability catalogs.
- **IGNORE** — authoring/state/personal content that MUST NOT leak. Sub-buckets:
  - *personal-docs* — private wikis, internal-only notes
  - *session-state* — handoffs, lessons, review-trail, project trackers, daily-review logs,
    improvement queues, archived specs
  - *install-state* — install-profile/status files, last-cleanup markers, similar
    machine-local state
  - *machine-config* — settings files, MCP configs containing secrets/tokens,
    environment-specific configs
  - *scratch* — `scratch/`, `_archived/`, `*.bak`, `*.tmp`, orphan temp files
- **GREY ZONE** — flag explicitly. Examples that historically need PM judgment: `examples/`, a
  domain glossary, an architecture doc, top-level READMEs, decision records, plan archives,
  anything under a name you don't recognize.

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

Collect an explicit publish/ignore decision on each grey-zone item — do NOT default-resolve
grey items silently.

If `.percolate-ignore` already exists, ALSO show its current content, a diff of what it covers
vs. the coverage gaps the audit found, and ask: _"Update existing `.percolate-ignore` to close
these gaps? [y/N]"_ A `n` answer is acceptable but must be explicit — the existing file is then
preserved with no edits.

### Step 3d — Write the audited file

**Scaffold guard — pre-write matcher walk.** Before writing, verify each pattern resolves
correctly against the Step 3a inventory. For each non-trivial pattern (directory suffix `/`,
extension glob `*.ext`), confirm at least one inventory entry would match. A pattern that was
intended to match something but doesn't (e.g. wrong path depth) must be corrected before
writing — a silently-dead pattern is a leak, not a routine miss.

**Pattern subset reminder:** `**/` is NOT a supported pattern in this matcher. Multi-depth
matches need explicit listing. Directory patterns (trailing `/`) are already recursive — they
match the directory at any depth in the source tree.

**Coordinate-system reminder for a multi-plugin source root.** Patterns are matched against the
source-directory-relative (plugin-qualified) path, not a sub-plugin-relative path. Author
patterns with the sub-plugin name prefix when the source root contains multiple plugins. A
pattern anchored at the wrong root is a silent no-op — the exclusion never fires and the files
leak.

Compose the file with comment-grouped sections so future readers can see the reasoning:

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

Show the proposed body and ask for final confirmation before writing. On `y`, write the file.
On `n`, report what would have been written and exit without overwriting.

Report what changed: _"`.percolate-ignore` written/updated at `<source_dir>/.percolate-ignore`
with N total patterns across M categories, audited against <count> source-tree entries on
<date>."_

---

## Step 4 — Scaffold Hook Directories

Resolve `<target_name>` (same target as Step 3). The hook base is
`setup/percolate-hooks/<target_name>/`.

For each of the three hook points — `pre-rsync`, `post-rsync`, `pre-ci` — first check what
already exists:

```bash
find "setup/percolate-hooks/<target_name>" -mindepth 1 -maxdepth 1 -type d
```

Compare the output against the three expected names to note which are already scaffolded. Then,
for the `pre-rsync` point, create the directory — idempotent, safe to run even if it already
exists:

```bash
mkdir -p "setup/percolate-hooks/<target_name>/pre-rsync"
```

and its attachment marker:

```bash
touch "setup/percolate-hooks/<target_name>/pre-rsync/.gitkeep"
```

Repeat the same `mkdir -p` / `touch` pair for `post-rsync` and `pre-ci`, substituting the
hook-point name in both paths.

Report which directories were created vs. already in place (from the inventory above). Hook
directories are empty by default — they exist as a registered attachment point, not a
requirement to populate.

---

## Step 5 — Drift Detection on Existing `.percolate-ignore`

**Applies when `.percolate-ignore` already exists and setup is running because hook directories
were absent, not because the ignore file was missing.**

After hook scaffolding, check for source-tree entries that appeared since the ignore file was
last audited (sort and cap the output yourself when reading — this is a single-command fence):

```bash
find "<source_dir>" -type f -newer "<source_dir>/.percolate-ignore"
```

If non-empty, surface under a "Coverage drift since last audit:" panel and classify each new
path (PUBLISH / IGNORE / GREY ZONE) using the same taxonomy as Step 3b. Present grey-zone
additions for explicit decision and offer to append new IGNORE entries to the existing file.

If no new files are found: report "Coverage drift check: clean — no new files since last audit."
and proceed.

---

## Summary

Print a summary of what was created vs. already in place:

```
Percolation setup for <target> — DONE

  publish-targets.portable:  <row added|target already registered>
  .percolate-ignore:         <audited+written|audited+updated to close N gaps|kept existing (PM-confirmed coverage adequate)>
  pre-rsync/ dir:        <created|already existed>
  post-rsync/ dir:       <created|already existed>
  pre-ci/ dir:           <created|already existed>

Setup complete. Run `/percolate <target>` to publish.
```

If any step was skipped due to an existing artifact, note it explicitly so the PM can audit.

---

## Structural-vs-Content Split

`.percolate-ignore` filters STRUCTURAL leaks — categories of paths (cache dirs, archived
scratch, session-state dirs, peer-runtime dirs). It cannot catch CONTENT leaks that accumulate
during normal authoring: a name slipping into a doc body, a peer-repo reference embedded in a
snippet, a machine name in a code comment, a token pasted into an example. Content leaks are
caught separately, at publish time, by a per-publish scan over the about-to-publish file set —
do not try to encode content scans into `.percolate-ignore`; a static ignore file ages out of
sync with continuous authoring drift.

---

## Failure Modes

| Failure | Symptom | Recovery |
|---|---|---|
| No target configuration found | Step 1 prompts for scaffolding | Add a row to the portable file; re-run |
| Target not yet registered | Step 2 prompts for registration; cannot auto-detect source path | Provide all four fields at the prompt |
| Source path does not exist | Step 3 `ls -A` returns empty or error | Verify `<source_dir>` in the resolved target row |
| PM declines grey-zone item write | `.percolate-ignore` not written; step exits with proposed content shown | Edit manually or re-run with explicit decisions |
| Hook dir creation fails (permissions) | `mkdir -p` exits non-zero | Fix permissions at `setup/percolate-hooks/`; re-run (idempotent) |
| Pattern in `.percolate-ignore` uses `**/` | Matcher silently ignores the pattern (unsupported syntax) | Replace with explicit directory listing or remove `**/` prefix |
| Drift check finds no ignore file | `find -newer` returns nothing (file missing, not just no drift) | Treat as missing; run full Step 3 audit |
| Audit subagent returns a summary but writes nothing to disk | Deliverable not on disk despite an apparent completion report | Re-dispatch and verify the file actually exists on disk before trusting the summary |
| Partial hook scaffold (some dirs present, others missing) | Some hook-point dirs present, others missing | Step 4 is idempotent — re-run; it creates missing dirs and skips existing ones |
