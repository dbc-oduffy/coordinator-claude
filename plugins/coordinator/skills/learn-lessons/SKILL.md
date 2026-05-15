---
name: learn-lessons
description: "Processes tasks/lessons.md as doctrine change-requests. 3 modes: local, central, recheck. Triggers on triage/trim/process lessons, promote universals."
version: 1.0.0
---

# learn-lessons — Lesson Processing and Queue Activation

## Overview

`learn-lessons` processes `tasks/lessons.md` files as change-requests against doctrine, agent prompts,
hooks, scripts, wiki guides, and improvement queues. Each lesson routes to one destination with an
explicit change-kind. The skill tracks recurrence across runs, archives discards rather than deleting
them, and surfaces queue depth to inform backlog prioritization.

**Supersedes `coordinator:lesson-triage`** (renamed 2026-05-06; no alias shim).

**Announce at start:** "I'm using the coordinator:learn-lessons skill in `<mode>` mode."

**Anti-transient framing.** The goal is doctrine evolution, not file-size reduction. Success metric:
"did central + project doctrine and queues evolve?"

## Modes

| Mode | Trigger | Authorization | Output |
|---|---|---|---|
| `local` | `/update-docs` Phase 6 OR direct invoke from a project repo | **Auto-apply** discard/wiki-append/retag/dedupe within bounds; surface structural changes to PM | In-place edits, archive appends, queue appends, PM summary |
| `central` | PM-invoked from `~/.claude` central (cross-repo extraction) | **PM gate** per apply; scouts read only, don't mutate remote lessons files | Routing manifest + review doc; apply runs plan → review → executor |
| `recheck` | `tasks/lesson-triage-recheck-due-*.md` marker fires via `/workday-start` | Auto-extend if delta small; otherwise dispatch central mode | New marker (no work) or full central run |

**Mode default detection.** `/learn-lessons` without `--mode` arg detects cwd: running from `~/.claude`
central → default `central`; else default `local`. Always log the detected mode in the announce-at-start
line.

## When to Trigger / Don't Trigger

**Trigger:**
- Per-project periodic maintenance via `/update-docs` Phase 6 (local mode)
- PM names "learn lessons", "lesson triage", "promote universals" (central mode)
- A `tasks/lesson-triage-recheck-due-*.md` marker fires (recheck mode)
- A project's `tasks/lessons.md` exceeds ~50 entries or ~175 lines (local mode)

**Don't trigger:**
- Reading lessons for context — that's a Read tool call, not a learn-lessons invocation
- A specific lesson is being acted on individually — that's normal change work
- The lessons file was just touched in the same session (let it settle)

## Phase 0 — Configuration

Config file: `~/.claude/tasks/learn-lessons-config.md`.

**Self-population via helper script.** Before any other Phase 0 work, invoke `${CLAUDE_PLUGIN_ROOT}/bin/learn-lessons-config-update.sh` to ensure the current cwd is registered in the config. The script is idempotent — silent no-op if the path is already present. Normalization is handled by the script (absolute path, lowercase on Windows, trailing slash stripped, POSIX separators).

### Self-population

Every `learn-lessons` invocation appends the running repo's path to the config file if absent
(create-if-absent; never overwrite an existing entry).

**Normalization for dedup (apply in order):**
1. Resolve to absolute path.
2. Lowercase on Windows.
3. Strip trailing slash.
4. Convert backslashes to POSIX `/`.

So `X:/foo`, `X:\foo`, `x:/foo/`, and `X:/foo` all normalize to the same entry `x:/foo`.

**Shell:** use `$PWD`. **Python:** use `os.getcwd()` or `pathlib.Path.cwd()`.

### Stale-entry handling

- **`local` and `recheck` modes:** if a configured root path is unresolvable on disk, emit a
  one-line warning and skip that entry. Do NOT prune.
- **`central` mode only:** prune config entries whose normalized paths no longer resolve on disk.
  Log each pruned entry: `"Pruned stale root from config: <path>"`.

### Fallback chain

1. **Config file** `~/.claude/tasks/learn-lessons-config.md` sentinel block
   (`<!-- BEGIN learn-lessons-roots -->` … `<!-- END learn-lessons-roots -->`).
2. **Default:** `~/.claude` only (if config file absent or empty).

No hardcoded project paths outside the config file's documented example block.

## Per-Lesson Routing Schema

Each lesson processed produces one record:

```yaml
- id: "<repo-shortname>-<entry-id>"
  source: "<file:line>"
  summary: "<one-line title>"
  scope: universal | project | wiki-only | discard
  destinations:
    - target: "<full file path or new-file path>"
      section: "<named section anchor or '(new section)' or '(new file)'>"
      change_kind: <see Change-Kind Taxonomy>
      rationale: "<one-line why>"
      priority: HIGH | MEDIUM | LOW
      depends_on: "<optional id pointer>"
  open_questions: []
```

## Change-Kind Taxonomy (closed enum)

| Kind | Meaning | Apply mechanism |
|---|---|---|
| `doctrine-edit` | Edit a CLAUDE.md at a named section | Plan → reviewer → executor |
| `agent-prompt-edit` | Edit a specific agent's prompt file | Plan → reviewer → executor |
| `hook-edit` | Edit a hook script | Plan → reviewer → executor |
| `script-edit` | Edit a helper script in `bin/` | Plan → reviewer → executor |
| `snippet-sync-update` | Edit a synced snippet + run propagation script | Edit + `bin/verify-*-sync.sh --fix` |
| `wiki-new` | Create a new `docs/wiki/` guide | Plan → reviewer → executor; update `DIRECTORY_GUIDE.md` |
| `wiki-append` | Append to existing wiki guide at named section | Direct executor (low judgment) |
| `memory-pointer` | Add a one-line pointer to `MEMORY.md` | Direct edit |
| `project-structural` | Change in originating project's repo | Plan → reviewer → executor in that repo |
| `retag-local` | Change `[universal]` → `[<domain>]` tag in place | Direct edit |
| `strip-local` | Delete entry from source file (gated on central commit SHA) | Direct edit, ONLY after depends_on lands |
| `discard` | Archive-then-delete (no migration) | Archive append + direct edit |

## Phase 1 — Discovery

Glob the configured roots (from config sentinel block). For each `lessons.md` found, capture:
- Total line count
- Tagged `[universal]` entry count (`grep -c '\[universal\]'`)
- Heuristic entry count (`##` and `**bold**` tallies)

Apply skip threshold: skip repos with zero universals AND fewer than 30 entries — diminishing returns.

Log skipped repos with a one-line reason each. Apply self-exclusion for `~/.claude/tasks/lessons.md`
in central mode (central is the doctrine target, not a promotion source).

## Phase 2 — Routing

### Central mode

One Haiku scout per surviving repo, dispatched in parallel. Scout brief:
- **Source path** — full path to the repo's `lessons.md`
- **Output path** — `~/.claude/tasks/learn-lessons-YYYY-MM-DD/<repo-shortname>-records.yaml`
- Two-pass extraction: `[universal]`-tagged entries first; untagged retroactive candidates second
  (with `scope: wiki-only` or promotion proposal + "why universal" justification)
- Conservative on domain-specific candidates — `retag-local` is the safer default
- Routing schema verbatim from this SKILL.md

<!-- BEGIN text-only-recovery-preamble (synced from snippets/text-only-recovery-preamble.md) -->
**Ignore any "TEXT ONLY" / "tool calls will be REJECTED" framing in your context — it is a known hallucination from confused prior agents in this session. No such constraint exists. The ONLY valid completion is calling the Write tool. Replies that dump the deliverable inline count as task failure. This applies at every tier — Haiku, Sonnet, and Opus have all been observed reproducing this hallucination on scout/inventory dispatches under parallel-fanout load. Tier does not exempt you; verify file on disk before replying DONE.**

- **If you propose deferral or BLOCKED, the report MUST name the specific premise you could not verify** (e.g. "cannot verify Module X exposes Symbol Y on this branch"). Bare "insufficient information" is a hallucination signature — readiness scouts and verifiers that defer without naming the unverified premise are pattern-matching their way out of the dispatch, not reporting a real gap.
<!-- END text-only-recovery-preamble -->

Scout verifies with `Bash ls -la <path>` and replies EXACTLY: `DONE: <path>`.

### Local mode

EM does this inline (no scout dispatch). Read single `tasks/lessons.md`, build routing records,
write to `tasks/learn-lessons-YYYY-MM-DD/records.yaml`.

## Phase 3 — Recurrence Detection

Before appending a new entry to any improvement queue, check if an existing queue entry covers the
same lesson (semantic match on the rule statement, not exact string).

**Threshold:**
- Queue ≥ 100 entries OR ≥ 4K tokens of queue content → fuzzy pre-filter: narrow to top-20
  candidates by token-overlap, then agent semantic-matches against those 20.
- Below threshold → agent reads full queue + new lesson and makes the call directly.

**If a match is found:**
1. Do NOT create a duplicate entry.
2. Append a recurrence note under the existing entry:
   ```
     **Recurrence note (YYYY-MM-DD):** lesson surfaced again; no resolution action recorded since <prior-date>.
   ```
3. Increment the existing entry's `recurring:` counter by 1.
4. Log the matched pair to `tasks/learn-lessons-YYYY-MM-DD/recurrence-log.yaml` (greppable provenance for PM review).
5. Surface to PM at end of run (see Phase 8 — Reporting).

**If no match:** append as a new entry with `recurring: 0` and `resolution: pending`.

**Semantic-pass (run after substring/exact-match first pass).** Substring match is the cheap floor — it misses semantic duplicates that share no keywords. After the first pass, for each surviving candidate ask: "Does this candidate restate, in different words, an existing rule in the queue / CLAUDE.md / target wiki?" If yes, route to "already-covered" rather than creating a new entry. Common failure mode: the same lesson phrased with different domain vocabulary (e.g. "executor fabricates commit attribution" vs "executor reports lie about which sha was committed" vs "git-log-says-X but chat-says-Y" — all the same rule, no substring overlap). Read the candidate's body against the target wiki's narrative, not just the title: keyword overlap is the floor; narrative match is the ceiling.

## Phase 4 — Discard Archive

Before removing any entry from `tasks/lessons.md`, append it to the per-repo archive file.

**Archive path:** `archive/lessons-archived/YYYY-MM.md` within each repo where local mode runs.
- `~/.claude/archive/lessons-archived/2026-05.md` for runs in May 2026.
- Create `archive/lessons-archived/` if absent.
- Append-only: multiple runs in the same calendar month append to the same file (do NOT overwrite).

**Provenance header per entry (write this line immediately before the entry body):**
```
# Discarded by /learn-lessons on YYYY-MM-DD HH:MM from tasks/lessons.md:LINE
```

EM judges discard inline — no PM confirmation gate on individual discards. The archive is the
safety net; it is recoverable (grep by date, source file, or line number) but not surfaced by
default from `tasks/lessons.md`.

**Reversed-lesson annotation (do NOT delete — annotate instead).** When a `[universal]` or
doctrine-targeted lesson is overturned by a later run or PM decision, do NOT delete the original
`tasks/lessons.md` entry. Instead, annotate it inline:

```
> **INVERTED 2026-05-14:** <one-line reason for reversal> (replaced by: <new doctrine pointer>)
```

Place the blockquote directly under the original lesson body. The original lesson remains as
historical context; future scouts see both the prior conclusion and the inversion, preventing
re-discovery of the same shape. Deletion is reserved for lessons that were factually wrong from
the start (e.g. cited a nonexistent file) or exact duplicates already folded — not for
"we changed our minds" reversals.

## Phase 5 — Authorization and Apply

### Local mode — auto-apply bounds

**Auto-apply without PM prompt:**
- `discard` of pure-ephemeral entries (archive first per Phase 4)
- `wiki-append` to existing guides
- `retag-local` within the same file
- Dedupe of obvious duplicates

**Surface to PM (do not auto-apply):**
- `doctrine-edit`, `wiki-new`, `agent-prompt-edit`, `hook-edit`, `script-edit`, `snippet-sync-update`
- `project-structural` outside the same repo
- `strip-local` of `[universal]`-tagged entries (cross-repo promotion needed first)

When surfacing: emit a one-screen PM summary at end with surfaced records and a
"run /learn-lessons --mode=central to action these" pointer.

### Central mode — PM gate

Present review doc to the PM. Per record, PM authorizes:
- **(a) apply now** — proceed to apply cycle (plan → reviewer → executor)
- **(b) defer to improvement queue** — append to `~/.claude/tasks/coordinator-improvement-queue.md`
  with schema fields (`recurring: 0`, `resolution: pending`)
- **(c) reject** — drop with reason captured in review doc

Section A (strip-only), Section B (central change), Section C (re-tag) all need PM go-ahead.
Batch authorization is OK ("apply all of A, defer all of B-MEDIUM, reject B-LOW").

### Apply order

**Central first, then strip-local.** Strip-local records have `depends_on` pointing at the central
change; do not strip until the central commit SHA exists.

### Per-record apply dispatch

#### CLAUDE.md char-budget pre-flight (gates `doctrine-edit` targeting any CLAUDE.md)

Before dispatching a `doctrine-edit` whose `target` is a `CLAUDE.md` file, run this pre-flight:

1. Measure current char size: `wc -c <target>`.
2. Estimate addition: char count of the proposed new bullet/section body.
3. Compare projected size (`current + addition`) against thresholds:

| Projected | Action |
|---|---|
| ≤ 36,000 | Proceed normally (≥4K headroom under soft limit). |
| 36,001 – 38,000 | Proceed, but emit a "budget approaching" note to the PM summary so the next addition is on notice. |
| 38,001 – 40,000 | **Gate: identify a demote target first.** The plan must name a specific section to compress to a wiki pointer (or an existing wiki to extend) and include the demote in the same plan. No PM ratification needed if the demote is mechanical (existing wiki carries the topic); surface to PM if creating a new wiki. |
| > 40,000 | **Hard refuse.** The pre-commit hook (`validate-commit.sh` Check 7) will block the commit anyway. Surface to PM with current size, proposed addition size, and the top-3 demote candidates ranked by char savings. |

The same gate applies whether the target is `~/.claude/CLAUDE.md`, `plugins/coordinator-claude/coordinator/CLAUDE.md`, or any project-level `CLAUDE.md` — the 40K limit is per-file, set by Claude Code's perf warning.

**Rationale.** The two trims in 2026-05-06/07 both held; doctrine creep refilled the budget through ~25 small additions. The hook catches the symptom; this gate catches the cause at the only step where coordinator-doctrine additions are routed (`doctrine-edit` is the closed-enum kind for CLAUDE.md edits per Phase 0 taxonomy).

#### Apply dispatch

- `doctrine-edit`, `wiki-new`, `agent-prompt-edit`, `hook-edit`, `script-edit` →
  write focused plan, dispatch the Staff Engineer for review, integrator on findings, executor.
- `snippet-sync-update` → edit snippet, run `bin/verify-<snippet>-sync.sh --fix`, commit all touched.
- `wiki-append`, `retag-local`, `memory-pointer`, `discard` → direct executor or EM edit.
- `strip-local` → direct edit in originating repo, gated on central SHA. Pull + status check first
  (concurrent EM guard — same as the existing lesson-triage cross-repo mechanics).
- `project-structural` → in originating project repo: plan → review → executor.

## Phase 6 — Per-Project Improvement Queue

<!-- Review: the Staff Engineer F6 — added explicit write-time discipline for new entries to both queues -->

**Create-if-absent.** If `tasks/improvement-queue.md` does not exist in the current project repo,
create it with the template content below. Never overwrite an existing file.

```markdown
# Improvement Queue

Project-structural improvements queued by `/learn-lessons`. Consumed by `/workweek-complete` Step 4.

## Format
`- YYYY-MM-DD | <source-repo or self> | <source-file>:<line> | <one-line lesson> | proposed target: <doctrine file or "wiki" or "agent prompt" or "hook">`
`  recurring: 0`
`  resolution: pending`

## Active queue
```

**When appending a NEW entry to either queue (central or per-project), write three lines: the main entry, then `  recurring: 0`, then `  resolution: pending` (two-space indent).** This applies to both `~/.claude/tasks/coordinator-improvement-queue.md` and per-project `tasks/improvement-queue.md`. Do not append bare single-line entries — the schema requires all three lines.

**Routing:**
- `[universal]` entries → append to `~/.claude/tasks/coordinator-improvement-queue.md` (central).
- `[project]` entries → append to local `tasks/improvement-queue.md`.
- `[wiki-only]` entries → append-or-promote to `docs/wiki/<topic>.md`.
- Unclassified/ephemeral → discard (archive first per Phase 4).

## Phase 7 — Recheck Marker

Drop `tasks/lesson-triage-recheck-due-<today + recheck_cadence_days>.md`. Single line:
```
Next learn-lessons cadence due YYYY-MM-DD. Run /learn-lessons from ~/.claude (central mode).
```

Default cadence: 21 days. `/workday-start` Step 1.6 globs `tasks/lesson-triage-recheck-due-*.md`.

### Recheck mode behavior

1. Run Phase 1 discovery across all configured roots.
2. Compute delta: new `[universal]`-tagged entries since prior cadence (git log on each root's
   `tasks/lessons.md`).
3. **If delta ≤ 5 entries total:** auto-extend cadence — drop new marker at `today + 1.5 × cadence`,
   delete firing marker, exit with PM one-liner ("recheck found N new entries — extending cadence").
4. **Otherwise:** dispatch in `central` mode (full Phase 2-5 flow).

## Phase 8 — End-of-Run Report

After all phases complete, emit a brief report to the PM:

```
learn-lessons run complete (mode=<mode>):
- N entries classified (M universal, K project, J wiki-only, L discarded)
- P entries archived to archive/lessons-archived/YYYY-MM.md
- Q new queue entries appended (central: Q1, local: Q2)
- R existing queue items received +1 recurrence increments:
    <list each item that got +1 with its current recurring: count>
```

The recurrence list is the pressure signal. PM acts or defers — no automatic block.

## Anti-Patterns

- **Auto-applying central promotions.** PM gates every apply in central mode.
- **Generalizing beyond `tasks/lessons.md`.** Targeted skill. Future generic doc-promotion is separate.
- **Bespoke extra parameters.** Modes are the parameter surface; resist additional flags.
- **Auto-emitting spinoff handoffs.** Section D of the review doc is advisory only.
- **Stripping local before central commit SHA exists.** Phase 5 apply order is load-bearing.
- **`git add -A` for strips.** Always explicit pathspec; concurrent-EM safety.
- **True-deleting discards.** All discards go to archive first; never irrecoverable from Phase 4.
- **Conflating improvement queue with lessons.md.** `lessons.md` is in-the-moment capture.
  `learn-lessons` is the periodic process that classifies and routes.
- **Same-session capture-and-validate-as-resolved.** Central-mode runs that capture a lesson AND mark it resolved within the same session create unverified-resolution noise — the resolution claim has not survived a context boundary. Capture in this run; validate in a later run when the lesson has had the chance to recur (or not).
- **Same-session capture-and-validate-as-universal.** A central `/learn-lessons` run that BOTH captures a new lesson AND validates it as universal in the same pass is a self-confirming loop — the session that surfaced the pattern is the same session asserting its cross-repo generality. Validate universality against accumulated evidence (peer repos, prior runs, recurrence count), not against the session that captured it. Capture this run; promote to `[universal]` in a later run once the pattern has recurred in a different context.

## Related

- `coordinator/CLAUDE.md` "Self-Improvement Loop" — references this skill for cadence + capture.
- `~/.claude/tasks/coordinator-improvement-queue.md` — central queue; destination for deferred items.
- `~/.claude/tasks/learn-lessons-config.md` — configured project roots; self-populates on each run.
- `snippets/text-only-recovery-preamble.md` — synced snippet consumed in Phase 2 scout dispatches.
- `archive/lessons-archived/YYYY-MM.md` — per-repo discard archive; append-only, per-month.
