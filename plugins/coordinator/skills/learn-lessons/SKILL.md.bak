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

**No-defer rule (load-bearing).** A `learn-lessons` run that classifies records and then defers
the actionable subset to "the next pass" is a doctrine violation. The defer-chain pattern —
each run pointing at the next-you to do the wiki work — is how lessons.md grows without
doctrine evolving. **If a record carries `change_kind: wiki-append` or `change_kind: wiki-new`
with a named destination file + section, apply it in THIS run.** The only legitimate deferrals
are (a) cross-mode handoffs that are structurally required (e.g. `strip-local` gated on a
central commit SHA that does not yet exist) and (b) records surfaced to the PM for product or
architectural authorization. "Time-budget" and "scope of this pass" are not legitimate
reasons to defer wiki promotions — the wiki promotion is the work.

## Routing Bias: Wikis Are the Default, CLAUDE.md Is Exceptional

Apply **extreme skepticism** to any routing record proposing a CLAUDE.md edit or a CLAUDE.md
pointer. The default destination for a captured lesson is **a wiki guide** — either an existing
one (`wiki-append`) or a new one (`wiki-new`). CLAUDE.md and pointer-only additions are the
exceptions, not the rule.

**Why.** CLAUDE.md is load-bearing at every session boot. It is not a knowledge base. Every
addition — even a one-line pointer — competes for finite boot-time attention. A plethora of
pointers is the same anti-pattern as a plethora of inline rules: both turn CLAUDE.md into an
index of indexes that nobody reads carefully.

**The mechanism that makes wiki-only lessons land** is the prior-art-checker pre-flight in
`coordinator:plan` (→ `docs/wiki/prior-art-checker.md`). It cross-references plans against the
wiki + lessons + queue corpus. A lesson living in `docs/wiki/<topic>.md` will be surfaced to the
planner when relevant — without consuming CLAUDE.md budget. **If a lesson can be found by
prior-art-check, it does not need to be in CLAUDE.md.**

### The CLAUDE.md justification gate

A `doctrine-edit` (CLAUDE.md content) or `memory-pointer` (CLAUDE.md/MEMORY.md pointer line) is
admissible **only** if the proposal can answer ALL of:

1. **Cross-cutting tripwire.** Does the rule apply to multiple, named surfaces that agents touch
   from cold boot? (Not "useful to know" — "wrong action taken without it.")
2. **Boot-time-greppable required.** Would a planner / EM realistically fail to find this via
   prior-art-check on a relevant plan? Wiki-routing fails ONLY if the lesson cannot be matched
   from a plan's claim surface.
3. **No existing wiki carries the topic.** Confirmed by `grep` against `docs/wiki/`. If a wiki
   exists, `wiki-append` is the correct route — even if the wiki would then need a one-line
   surfacing somewhere agents already look (which is almost never CLAUDE.md).
4. **No existing CLAUDE.md section already covers the shape.** Demotion of a near-duplicate
   into the proposed addition's home wiki is preferred over adding alongside it.

If any check fails, downgrade the change-kind: `doctrine-edit` → `wiki-append` / `wiki-new`;
`memory-pointer` → discard (the wiki already carries it; prior-art-check will surface it).

**Substance and proposed-target are independent.** The original logging EM's `proposed target:` is a suggestion, not a verdict on the lesson's worth. When the proposed target is CLAUDE.md (or a CLAUDE.md pointer) and fails the four-check gate, the default move is **reroute** — pick the right wiki / agent prompt / hook / script surface for the substance — NOT `discard`. Discard is reserved for lessons whose *substance* is ephemeral, already covered by existing doctrine, or factually wrong from the start. "Logger proposed a rule-breaking target, therefore archive" is a category error: it conflates the lesson with its suggested destination. Ask "what problem is this lesson trying to solve, and where does that problem actually live?" before routing.

**Default verdict on doctrine-edit and memory-pointer proposals is REJECT-AND-REROUTE.**
Surface accepted exceptions to the PM with the four checks answered inline. Do NOT auto-apply
either kind, regardless of mode.

### Pointer-pollution bound

The CLAUDE.md "→ `docs/wiki/<name>.md`" pointer is a tool, not a destination. A run that emits
more than **one** new CLAUDE.md pointer across all routing records is presumptively wrong —
the underlying lessons belong in their wikis, and the wikis are findable by prior-art-check
without a CLAUDE.md hand-hold. Surface to the PM with the full pointer list before applying.

## Modes

| Mode | Trigger | Authorization | Output |
|---|---|---|---|
| `local` | `/update-docs` Phase 6 OR direct invoke from a project repo | **Auto-apply** discard/wiki-append/retag/dedupe within bounds; surface structural changes to PM | In-place edits, archive appends, queue appends, PM summary |
| `central` | PM-invoked from `~/.claude` central (cross-repo extraction) | **PM gate** per apply; scouts read only, don't mutate remote lessons files | Routing manifest + review doc; apply runs plan → review → executor |
| `recheck` | `tasks/lesson-triage-recheck-due-*.md` marker fires via `/workday-start` | Auto-extend if delta small; otherwise dispatch central mode | New marker (no work) or full central run |

**Mode default detection.** `/learn-lessons` without `--mode` arg detects cwd: running from `~/.claude`
central → default `central`; else default `local`. Always log the detected mode in the announce-at-start
line.

**Morning-brief framing is advisory.** The skill body's mode-default logic above is authoritative — if cwd is a project repo, mode is `local` even if the morning brief surfaced the central queue depth. PM can override explicitly.

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
| `doctrine-edit` | **EXCEPTIONAL** — edit a CLAUDE.md at a named section. Must clear the four-check justification gate (§ Routing Bias). Default verdict on proposals: reroute to `wiki-append` / `wiki-new`. | Plan → reviewer → executor; PM surface mandatory |
| `agent-prompt-edit` | Edit a specific agent's prompt file | Plan → reviewer → executor |
| `hook-edit` | Edit a hook script | Plan → reviewer → executor |
| `script-edit` | Edit a helper script in `bin/` | Plan → reviewer → executor |
| `snippet-sync-update` | Edit a synced snippet + run propagation script | Edit + `bin/verify-*-sync.sh --fix` |
| `wiki-new` | Create a new `docs/wiki/` guide. **Default destination** for non-trivial cross-cutting lessons. | Plan → reviewer → executor; update `DIRECTORY_GUIDE.md` |
| `wiki-append` | Append to existing wiki guide at named section. **Default destination** for lessons covered by an existing wiki topic. | Direct executor (low judgment) |
| `memory-pointer` | **EXCEPTIONAL** — add a one-line pointer to MEMORY.md or CLAUDE.md. Same four-check gate as `doctrine-edit`; the prior-art-checker should be reached for first. | Direct edit; PM surface mandatory |
| `project-structural` | Change in originating project's repo | Plan → reviewer → executor in that repo |
| `retag-local` | Change `[universal]` → `[<domain>]` tag in place | Direct edit |
| `strip-local` | Delete entry from source file (gated on central commit SHA) | Direct edit, ONLY after depends_on lands |
| `discard` | Archive-then-delete (no migration) | Archive append + direct edit |

## Phase 0.5 — Dedupe Pass (central mode only)

Re-Read the queue from disk; build a hash-set of normalized one-line summaries; flag entries with semantic-duplicate matches for merge before Phase 3 routes them as independent entries.

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
3. Increment the existing entry's recurrence count. If the entry has no `[recurring: N]` suffix on the main line, append `[recurring: 1]`; otherwise bump N by 1. The standalone `  recurring:` sub-line schema is deprecated (DR-056 amended 2026-05-17) — do NOT add or update one.
4. Log the matched pair to `tasks/learn-lessons-YYYY-MM-DD/recurrence-log.yaml` (greppable provenance for PM review).
5. Surface to PM at end of run (see Phase 8 — Reporting).

**If no match:** append as a new entry — main line only. Do NOT write `recurring: 0` or `resolution: pending` sub-lines; the pruner strips them on the next `/update-docs` run anyway.

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

Before applying any queue entry, re-Read the queue from disk to catch concurrent edits since Phase 3 routing.

### Local mode — auto-apply bounds

**Auto-apply without PM prompt:**
- `discard` of pure-ephemeral entries (archive first per Phase 4)
- `wiki-append` to existing guides — **mandatory same-run apply when destination is named**
- `wiki-new` when (a) destination filename is named in the record, (b) the lesson's substance
  is concrete enough for the executor to draft a first version, and (c) the new file does not
  cross into doctrine surfaces (CLAUDE.md, agent prompts). Add `DIRECTORY_GUIDE.md` entry in
  the same executor dispatch. PM-surfacing on `wiki-new` is reserved for genuinely novel
  topics where the wiki home is itself a design call — not for every new-file creation.
- `retag-local` within the same file
- Dedupe of obvious duplicates

**Same-run apply is the default, not the exception.** When a record lands in the auto-apply
bucket, dispatch the apply this run. Emitting a "next local pass should fold these" line in
the end-of-run summary is the defer-chain anti-pattern. If parallel-dispatch budget is tight,
serialize — do not defer.

**Surface to PM (do not auto-apply):**
- `doctrine-edit`, `memory-pointer` — **always** surface, regardless of mode, with the
  § Routing Bias four-check answers inline. EM's own first move is to attempt the reroute
  to `wiki-append` / `wiki-new` and present that as the recommended path.
- `wiki-new` ONLY when the wiki home is itself an unresolved design question (not the common
  case — most `wiki-new` records auto-apply per the bullet above).
- `agent-prompt-edit`, `hook-edit`, `script-edit`, `snippet-sync-update`
- `project-structural` outside the same repo
- `strip-local` of `[universal]`-tagged entries (cross-repo promotion needed first)

**Universals-pending escalation.** If a local-mode run finds ≥ 20 unactioned `[universal]`-tagged
entries that have accumulated since the last central-mode commit (`git log` on
`~/.claude/tasks/coordinator-improvement-queue.md` and `~/.claude/CLAUDE.md`), the run does NOT
exit with a "run central later" pointer. It surfaces the count to the PM with a single
question: *"Backlog of N universals — invoke central mode now?"* — and waits. Local mode
cannot strip these, but it can refuse to launder the backlog into another "next pass" notice.

When surfacing: emit a one-screen PM summary at end with surfaced records and a
"run /learn-lessons --mode=central to action these" pointer.

### Central mode — PM gate

Present review doc to the PM. Per record, PM authorizes:
- **(a) apply now** — proceed to apply cycle (plan → reviewer → executor)
- **(b) defer to improvement queue** — append a main-line-only entry to
  `~/.claude/tasks/coordinator-improvement-queue.md` (DR-056 amended 2026-05-17 —
  no `recurring:` / `resolution:` sub-lines)
- **(c) reject** — drop with reason captured in review doc

Section A (strip-only), Section B (central change), Section C (re-tag) all need PM go-ahead.
Batch authorization is OK ("apply all of A, defer all of B-MEDIUM, reject B-LOW").

### Apply order

**Central first, then strip-local.** Strip-local records have `depends_on` pointing at the central
change; do not strip until the central commit SHA exists.

### Per-record apply dispatch

#### CLAUDE.md justification pre-flight (gates `doctrine-edit` and `memory-pointer`)

**Run the § Routing Bias four-check gate FIRST.** Size is a backstop, not the primary
filter. If any of the four checks (cross-cutting tripwire / boot-time-greppable required /
no wiki carries it / no CLAUDE.md section already covers it) fails, the change-kind is
downgraded to `wiki-append` or `wiki-new` before any size measurement happens. A passing
gate-check must be recorded inline in the PM-surfacing block; "size fits" is not a
justification.

#### CLAUDE.md char-budget pre-flight (gates `doctrine-edit` targeting any CLAUDE.md)

After the justification gate clears, before dispatching a `doctrine-edit` whose `target` is a
`CLAUDE.md` file, run this pre-flight:

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
  write focused plan, dispatch Patrik for review, integrator on findings, executor.
- `snippet-sync-update` → edit snippet, run `bin/verify-<snippet>-sync.sh --fix`, commit all touched.
- `wiki-append`, `retag-local`, `memory-pointer`, `discard` → direct executor or EM edit.
- `strip-local` → direct edit in originating repo, gated on central SHA. Pull + status check first
  (concurrent EM guard — same as the existing lesson-triage cross-repo mechanics).
- `project-structural` → in originating project repo: plan → review → executor.

## Phase 6 — Per-Project Improvement Queue

<!-- Review: Patrik F6 — added explicit write-time discipline for new entries to both queues -->

**Create-if-absent.** If `tasks/improvement-queue.md` does not exist in the current project repo,
create it with the template content below. Never overwrite an existing file.

```markdown
# Improvement Queue

Project-structural improvements queued by `/learn-lessons`. Consumed by `/workweek-complete` Step 4.

## Format
`- YYYY-MM-DD | <source-repo or self> | <source-file>:<line> | <one-line lesson> | proposed target: <doctrine file or "wiki" or "agent prompt" or "hook">`

(Main-line only. Append ` [recurring: N]` to the line when N ≥ 1.)

## Active queue
```

**When appending a NEW entry to either queue (central or per-project), write the main line only.** DR-056 amended 2026-05-17: the `recurring:` and `resolution:` sub-lines are dropped from the schema (empirical data: 100% of central-queue entries had `recurring: 0` / `resolution: pending` — 266 lines of unchanging ceremony across 133 entries). `/update-docs` Phase 11i strips trivial sub-lines on every run regardless. If recurrence count matters, append ` [recurring: N]` to the main line when N ≥ 1.

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
3. **Structural-enforcement verification (run for each pending lesson that names a tripwire, wiki, or
   script artifact).** Before counting a lesson as "still ambient," check whether a completion entry
   citing the relevant artifact has been recorded since the lesson's capture date:
   ```bash
   bin/query-records --type completion --where "title~<tripwire-name>" --since "<lesson-date>"
   ```
   A returned record indicates the lesson is structurally enforced (a tripwire / wiki / skill edit
   shipped that codifies it) — exclude it from the delta count and log it as `[enforced]` in the
   recheck report. Absence of any record indicates the lesson is still ambient — count it normally.
   This drives the "is this lesson live?" question mechanically rather than by EM recall.
4. **If delta ≤ 5 entries total (after excluding enforced lessons):** auto-extend cadence — drop new
   marker at `today + 1.5 × cadence`, delete firing marker, exit with PM one-liner ("recheck found N
   new entries (M enforced, K ambient) — extending cadence").
5. **Otherwise:** dispatch in `central` mode (full Phase 2-5 flow).

## Phase 8 — End-of-Run Report

After all phases complete, emit a brief report to the PM:

```
learn-lessons run complete (mode=<mode>):
- N entries classified (M universal, K project, J wiki-only, L discarded)
- P entries archived to archive/lessons-archived/YYYY-MM.md
- Q new queue entries appended (central: Q1, local: Q2)
- R existing queue items received +1 recurrence increments:
    <list each item that got +1 with its current [recurring: N] count>
```

The recurrence list is the pressure signal. PM acts or defers — no automatic block.

**Forbidden report shapes.** The end-of-run report must NOT include:
- "N candidates for the next local pass" or similar defer-chain language.
- "Run /learn-lessons later to action these" as a substitute for action this run.
- "Modest by design" / "scope limited to this pass" framing that justifies non-apply on
  records that match the auto-apply contract.

If the report would otherwise have included such a line, the corresponding records belong in
one of three buckets: (a) applied this run, (b) PM-surfaced with a decision request, (c) mode
escalated (universals-pending → central mode invocation request). Any record that does not fit
those three is a routing error — fix the routing, not the report.

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
- **Default-routing a lesson to CLAUDE.md or to a CLAUDE.md pointer.** Wikis are the default;
  `doctrine-edit` and `memory-pointer` are exceptional and must clear the four-check gate
  (§ Routing Bias). "It's small, it'll fit" is not a justification — the prior-art-checker
  is the mechanism that ensures wiki-only lessons land, and adding a pointer per lesson is
  the same pollution as inlining the rule.
- **Archiving a lesson because its proposed target violates policy.** The lesson's substance
  and the logger's proposed target are independent. A `proposed target: CLAUDE.md` that fails
  the lean-and-mean gate is a routing problem, not a substance problem — reroute to the right
  wiki / agent prompt / hook / script. Only `discard` when the substance itself is ephemeral,
  already covered, or wrong. → § Routing Bias "Substance and proposed-target are independent."
- **Defer-chaining wiki promotions to "next pass."** A run that classifies records with named
  wiki destinations and then writes "next local pass should fold these via wiki-append" in the
  end-of-run summary is the pattern this skill exists to prevent. The "next pass" never happens
  because each successor inherits the same defer-bias. Wiki-append/wiki-new with named destinations
  apply IN THIS RUN — that is the auto-apply contract from Phase 5. The only legitimate same-run
  non-apply for a wiki record is PM authorization gate (genuinely novel wiki home) or a missing
  precondition that is itself in-flight in the same run.
- **End-of-run summary listing "candidates for the next pass."** Any line in the Phase 8 report
  that names records the current run did not apply but "should be folded by next run" is a
  doctrine violation. Either apply them (auto-apply bucket), surface them to the PM with a
  decision request (gated bucket), or escalate the mode (universals-pending escalation). The
  three buckets are exhaustive; "informational candidates for later" is not a fourth.
- **Same-session capture-and-validate-as-universal.** A central `/learn-lessons` run that BOTH captures a new lesson AND validates it as universal in the same pass is a self-confirming loop — the session that surfaced the pattern is the same session asserting its cross-repo generality. Validate universality against accumulated evidence (peer repos, prior runs, recurrence count), not against the session that captured it. Capture this run; promote to `[universal]` in a later run once the pattern has recurred in a different context.

## Related

- `coordinator/CLAUDE.md` "Self-Improvement Loop" — references this skill for cadence + capture.
- `~/.claude/tasks/coordinator-improvement-queue.md` — central queue; destination for deferred items.
- `~/.claude/tasks/learn-lessons-config.md` — configured project roots; self-populates on each run.
- `snippets/text-only-recovery-preamble.md` — synced snippet consumed in Phase 2 scout dispatches.
- `archive/lessons-archived/YYYY-MM.md` — per-repo discard archive; append-only, per-month.
