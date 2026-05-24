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

If any check fails (during DoE adjudication of a worker-flagged escalation, or during DoE
self-review of a proposed doctrine-edit plan), downgrade: `doctrine-edit` → `wiki-append` /
`wiki-new` + `doe_escalation: true` (preserve the signal for DoE's separate downstream
consideration — NOT for further apply steps in the current run); `memory-pointer` →
`wiki-append` to the wiki that already carries the topic (the prior-art-checker will surface
it from there — no separate pointer needed).

**Substance and proposed-target are independent.** The original logging EM's `proposed target:` is a suggestion, not a verdict on the lesson's worth. When the proposed target is CLAUDE.md (or a CLAUDE.md pointer) and fails the four-check gate, the default move is **reroute** — pick the right wiki / agent prompt / hook / script surface for the substance — NOT `discard`. Discard is reserved for lessons whose *substance* is ephemeral, already covered by existing doctrine, or factually wrong from the start. "Logger proposed a rule-breaking target, therefore archive" is a category error: it conflates the lesson with its suggested destination. Ask "what problem is this lesson trying to solve, and where does that problem actually live?" before routing.

**Workers MUST NOT emit `change_kind: doctrine-edit` or `change_kind: memory-pointer`.** Route
to `wiki-append` / `wiki-new` and set `doe_escalation: true` (with a one-line
`escalation_reason:`) when the worker believes CLAUDE.md placement deserves DoE consideration.
The EM/consolidator treats any record arriving with either change-kind as a routing error
and downgrades it to the corresponding `wiki-*` before the record reaches PM surfacing.
DoE-authored exceptions (a separate downstream plan, not lifted from worker output) require
all four justification checks answered inline. **Do NOT auto-apply `doctrine-edit` or
`memory-pointer` records, regardless of mode** — they always require DoE authoring, the Staff Engineer
review, and PM surface.

### DoE-only adjudication on CLAUDE.md edits

CLAUDE.md loads at every session boot across every project — blast radius is maximum. The receive-side gate must match that asymmetry.

**Workers / scouts MUST NOT propose `change_kind: doctrine-edit` or `change_kind: memory-pointer`.** These are reserved for the DoE (the Director of Engineering or the EM at Claude Central with explicit DoE authority). Worker records using either change-kind are downgraded by the consolidator before PM surfacing:

- Worker sets `doe_escalation: true` on a `wiki-append`/`wiki-new` record with a one-line `escalation_reason:`. The wiki edit lands regardless — escalation is a DoE attention flag, not a blocker.
- If the DoE accepts the escalation, they author a separate `doctrine-edit` plan (NOT lifted from worker output), reviewed by the Staff Engineer, gated on the four-check justification gate + char-budget pre-flight. Many gates before any CLAUDE.md byte changes.

EMs proposing CLAUDE.md targets in `tasks/lessons.md` is expected and inevitable — the load-bearing gate is on the receive side, not at capture time. The four-check justification gate still applies to DoE-authored proposals; the DoE does not bypass it.

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
  doe_escalation: false           # workers set true on a wiki-* record when they
                                  # believe DoE should reconsider CLAUDE.md placement
  escalation_reason: ""            # one-line; only meaningful if doe_escalation: true
```

`doe_escalation` is the worker-side flag for "this might be CLAUDE.md-worthy — DoE please
look." It rides on a `wiki-append` or `wiki-new` record; the wiki edit lands regardless.
Workers MUST NOT use `change_kind: doctrine-edit` or `change_kind: memory-pointer` (see
§ Routing Bias). Records arriving with those change-kinds are treated as routing errors
and downgraded by the consolidator.

## Change-Kind Taxonomy (closed enum)

| Kind | Meaning | Apply mechanism |
|---|---|---|
| `doctrine-edit` | **DoE-ONLY** — edit a CLAUDE.md at a named section. Workers MUST NOT propose; reserved for DoE authoring after escalation review. Must clear the four-check justification gate AND char-budget pre-flight (§ Routing Bias). | DoE-authored plan → the Staff Engineer review → executor; PM surface mandatory |
| `agent-prompt-edit` | Edit a specific agent's prompt file | Plan → reviewer → executor |
| `hook-edit` | Edit a hook script | Plan → reviewer → executor |
| `script-edit` | Edit a helper script in `bin/` | Plan → reviewer → executor |
| `snippet-sync-update` | Edit a synced snippet + run propagation script | Edit + `bin/verify-*-sync.sh --fix` |
| `wiki-new` | Create a new `docs/wiki/` guide. **Default destination** for non-trivial cross-cutting lessons. | Plan → reviewer → executor; update `DIRECTORY_GUIDE.md` |
| `wiki-append` | Append to existing wiki guide at named section. **Default destination** for lessons covered by an existing wiki topic. | Direct executor (low judgment) |
| `memory-pointer` | **DoE-ONLY** — add a one-line pointer to MEMORY.md or CLAUDE.md. Workers MUST NOT propose; reserved for DoE authoring. Same four-check gate as `doctrine-edit`; prior-art-checker should be reached for first. | DoE-authored edit; PM surface mandatory |
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

**Routing has two layers, split along the determinism seam:**

- **Extraction (deterministic, no LLM):** parse each `lessons.md` into verbatim records via `bin/extract-lessons.py`. Faithful extraction of source text is a parse, not a judgment call — running it through an LLM is what produced the 2026-05-24 fabrication failure (3/3 Haiku scouts invented plausible-but-nonexistent records to fill the routing shape we'd demanded). With a parser, fabrication of source content is *structurally impossible*, not just less likely. The script also empirically out-performs hand extraction: on the 2026-05-24 dogfood it found 77 dated delta entries vs. an Opus-by-hand pass that found 28 — humans/agents miss entries in long files; a parse finds every one.
- **Routing (bounded judgment, gated):** classify each extracted record into `scope` + `destinations[].target` + `change_kind` against the routing schema below. This is real judgment but bounded (choose from an enumerated set of existing wikis / agent prompts / hooks). Haiku is acceptable here ONLY behind the Phase 5 verify gate; for small deltas (≤ ~30 records) the EM does routing directly.

### Central mode — extraction step

For each surviving repo, produce **two** extractions — a full one (the verify oracle for Phase 5) and a delta-filtered one (the router input). The script returns in ms, so this is cheap:

```bash
# Full extraction — the verify-gate oracle. Always run, no --since.
bin/extract-lessons.py extract <repo>/tasks/lessons.md --shortname <shortname> \
  -o ~/.claude/tasks/learn-lessons-YYYY-MM-DD/<shortname>-extracted-full.yaml

# Delta extraction — the router input, filtered to the window since the last central run.
bin/extract-lessons.py extract <repo>/tasks/lessons.md --shortname <shortname> \
  --since <last-central-run-date> \
  -o ~/.claude/tasks/learn-lessons-YYYY-MM-DD/<shortname>-extracted-delta.yaml
```

**Why two extractions:** the verify gate asks "is the cited source line a real entry, period" — undated real entries should pass that question (they exist in source). `--since` belongs on the router's input view, not the verification oracle; if the gate used a `--since`-filtered oracle it would reject any record routing an undated real lesson, even though the cite is genuine. Run the full extraction once per repo; reuse it for verify across the run.

`--since` keeps dated entries in-window and EXCLUDES undated ones (reported in meta as `undated_excluded_under_since: N`) — for a delta router input, that's correct (undated entries can't be proven in-window). To route undated lessons, run a separate non-`--since` routing pass over the full extraction. The extractor assigns deterministic ids of the form `<shortname>-L<line>` (the start-line of the entry's header block in source), which the routing layer must cite verbatim.

### Central mode — routing step

The EM (or a delegated router) reads the per-repo `*-extracted.yaml` files and produces `*-records.yaml` with routing decisions per the schema below. Routing records MUST set `id` and `source` to values that exist in the matching extraction (the Phase 5 verify gate rejects fabricated references).

**Routing rules (apply at any altitude — EM-direct, Haiku-router, or Sonnet-router):**

- **Lessons asserting a mechanical contract must cite executable authority, not narrative confidence.** A lesson stating an env-var value, a path resolution rule, an API signature, an exit-code, or any other mechanical fact (vs. an operating discipline) must point at the executable witness — a passing contract test, the live tool's observed behavior, official docs — in its body. When the routing record's source lesson is a mechanical-contract assertion, route as: (a) `wiki-append` with rationale flagging missing-citation if no executable witness is cited but one plausibly exists; (b) `discard` if no executable witness can be located OR an executable witness contradicts the lesson's assertion (the lesson is wrong, not just under-cited). The 2026-05-23 `${CLAUDE_PLUGIN_ROOT}` lesson — exactly backwards for days, would have led the next EM to revert a correct 91-file fix — is the empirical case for the contradiction branch: three independent authorities (Claude Code docs, `test_claude_plugin_root_resolution.py`, the live tool's substitution) converged against the lesson; narrative confidence in a prose log is not evidence. Rule of thumb: if a lesson and a passing contract test disagree on a mechanical fact, correct the lesson, not the test.
- Conservative on domain-specific candidates — `retag-local` is the safer default for entries that look universal-tagged but are really domain (UE / game-dev / web-dev / data-science).
- **NEVER use `change_kind: doctrine-edit` or `change_kind: memory-pointer`** — those are
  DoE-only. Route every CLAUDE.md-targeted lesson the source EM proposed to `wiki-append`
  (preferred) or `wiki-new` instead. If you genuinely believe the DoE should reconsider
  CLAUDE.md placement, set `doe_escalation: true` on the wiki-* record with a one-line
  `escalation_reason:` — the wiki edit still lands; escalation is just a DoE attention flag.
  Records with `doctrine-edit` or `memory-pointer` from a worker are treated as routing errors
  and downgraded.

If a Haiku/Sonnet router is dispatched, the dispatch prompt MUST include the verify-gate clause: *"Every routing record's `id` MUST appear in the cited `*-extracted.yaml`. Inventing a record under a fabricated id will be caught by `extract-lessons.py verify` at Phase 5 and fail the run."* The gate is mechanical (Phase 5); the prompt clause is the design-as-offers framing that lets the router self-check before producing output.

### Local mode

Same two layers, scoped to one repo:

```bash
bin/extract-lessons.py extract tasks/lessons.md --shortname <repo> \
  -o tasks/learn-lessons-YYYY-MM-DD/extracted.yaml
```

EM produces `records.yaml` inline from the extraction (no router dispatch — local-mode deltas are always small enough for EM-direct routing).

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

### Verify-gate pre-flight (mechanical, before any apply)

For every `*-records.yaml` produced in Phase 2, run the fabrication gate against its matching extraction. **Two dispatch shapes** depending on whether the routing file is per-shortname or multi-repo:

```bash
# Single-shortname routing (one extraction, one routing file):
bin/extract-lessons.py verify \
  ~/.claude/tasks/learn-lessons-YYYY-MM-DD/<shortname>-extracted-full.yaml \
  ~/.claude/tasks/learn-lessons-YYYY-MM-DD/<shortname>-records.yaml

# Multi-repo routing (one routing file with records from N shortnames):
# Pass the run directory as the extraction arg; verify auto-discovers every
# <shortname>-extracted-full.yaml inside it and dispatches each routing record
# to its matching extraction by id-prefix (<shortname>-L<N>).
bin/extract-lessons.py verify \
  ~/.claude/tasks/learn-lessons-YYYY-MM-DD/ \
  ~/.claude/tasks/learn-lessons-YYYY-MM-DD/records-net-new.yaml
```

The gate asserts that every routing record cites a `source:` line number that a real extracted entry occupies, and that every cited `id` of the form `<shortname>-L<N>` exists in the extraction. **The full (non-`--since`) extraction is the verify oracle** — see the "Why two extractions" note above. **Exit 1 fails the apply phase loud** — ungrounded references are fabrication suspects and MUST be triaged (router error or extraction-vs-routing mismatch) before any wiki/queue write proceeds. The gate is the mechanical backstop that lets Haiku/Sonnet routers be used safely on backlogs: extraction is unforgeable (script, not LLM), and routing fakery is detectable (verify rejects it). Empirically the gate also catches Opus hand-routing line-citation drift — its first dogfood (2026-05-24) caught 2 ungrounded references in a 28-record hand-routing batch.

**When to use multi-repo mode.** A second-pass Sonnet router classifying records across N source repos in one yaml (the 2026-05-24 `records-net-new.yaml` shape) used to require splitting per-shortname and running `verify` N times. Pass the run-dir directly instead — multi-repo mode auto-engaged on directory arg. Multiple `<shortname>-extracted-full.*` files for the same shortname surface as an explicit operator error (exit 2), never silently picked.

EM-direct routing on a small delta still runs the gate — it catches typos and stale source-line references that would otherwise propagate to applied wiki sections citing the wrong source.

### When the gate fails — recovery playbook

A non-zero exit is not a dead end; the stderr output names every ungrounded record. Don't proceed to apply until grounded. The gate fails in one of four shapes; the recovery differs:

1. **Stale extraction.** The routing file was produced against an older extraction of a `lessons.md` that has since been edited (a concurrent EM session reordered or appended entries). Re-run `extract` to refresh `<shortname>-extracted-full.yaml`, then re-run `verify`. If the routing record's cited line now lands on a different real entry whose `title` no longer overlaps the routing summary, this is actually shape (2).
2. **Router inventing (LLM fabrication).** A Haiku/Sonnet router cited an id or line that never existed. Re-dispatch the router with two amendments: (a) attach the failing-ids list inline so the router sees specifically what was rejected; (b) re-emphasise the verify-gate clause from the original dispatch prompt. Do NOT hand-correct the router's output — that launders the fabrication into the audit trail.
3. **Summary-swap (subtle fabrication).** Line and id ground but the routing summary describes a different entry's content. The title-overlap check catches this. Same recovery as (2) — re-dispatch the router; do not hand-edit.
4. **EM hand-routing drift.** EM-direct routing on a small delta cited a line off by N (concurrent edits to source shifted line numbers, or the EM transcribed wrong). EM corrects the routing file in place against current extraction; re-run verify.

Re-run `verify` to green before proceeding to apply. Treat persistent gate failures (≥2 re-dispatches of the same router still failing) as a signal to drop to EM-direct routing for the affected slice; the model isn't going to converge on a corpus it can't ground in.

### Concurrent-edit guard

Before applying any queue entry, re-Read the queue from disk to catch concurrent edits since Phase 3 routing.

### Local mode — auto-apply bounds

**Auto-apply without PM prompt:**
- `discard` of pure-ephemeral entries (archive first per Phase 4)
- `wiki-append` to existing guides — **mandatory same-run apply when destination is named**
- `wiki-new` when (a) destination filename is named, (b) substance is concrete enough for an executor draft, and (c) the new file does not cross into doctrine surfaces. Add `DIRECTORY_GUIDE.md` entry in same executor dispatch. Surface to PM only when the wiki home is itself an unresolved design question.
- `retag-local` within the same file
- Dedupe of obvious duplicates

**Same-run apply is the default.** When a record lands in the auto-apply bucket, dispatch the apply this run. "Next local pass should fold these" is the defer-chain anti-pattern. If parallel-dispatch budget is tight, serialize — do not defer.

**Surface to PM (do not auto-apply):**
- `doctrine-edit`, `memory-pointer` — **DoE-only.** Downgrade worker-proposed records to `wiki-*` + `doe_escalation: true` before surfacing. The DoE authors a real `doctrine-edit` plan only after reviewing the escalation bucket, clearing the four-check gate, and clearing the char-budget pre-flight.
- `doe_escalation: true` records — surface as a separate "DoE reconsideration" bucket. The wiki edit auto-applies; the escalation flag is a DoE attention notice, NOT a blocker.
- `agent-prompt-edit`, `hook-edit`, `script-edit`, `snippet-sync-update`
- `project-structural` outside the same repo
- `strip-local` of `[universal]`-tagged entries (cross-repo promotion needed first)

**Universals-pending escalation.** If ≥ 20 unactioned `[universal]`-tagged entries have accumulated since the last central-mode commit, surface the count to the PM: *"Backlog of N universals — invoke central mode now?"* — and wait. Do not launder the backlog into another "next pass" notice. Emit a one-screen PM summary with surfaced records and a "run /learn-lessons --mode=central" pointer.

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

The same gate applies whether the target is `~/.claude/CLAUDE.md`, `plugins/coordinator/CLAUDE.md`, or any project-level `CLAUDE.md` — the 40K limit is per-file, set by Claude Code's perf warning.

**Rationale.** The two trims in 2026-05-06/07 both held; doctrine creep refilled the budget through ~25 small additions. The hook catches the symptom; this gate catches the cause at the only step where coordinator-doctrine additions are routed (`doctrine-edit` is the closed-enum kind for CLAUDE.md edits per Phase 0 taxonomy).

#### Apply dispatch

- `doctrine-edit`, `memory-pointer` → **DoE-only.** Workers MUST NOT reach this branch —
  worker records arriving with either change-kind are downgraded to `wiki-*` +
  `doe_escalation: true` at consolidation. Only DoE-authored plans (drafted after reviewing
  the escalation bucket, clearing the four-check justification gate, and clearing the
  char-budget pre-flight) reach this dispatch step. Plan → the Staff Engineer review → integrator →
  executor.
- `wiki-new`, `agent-prompt-edit`, `hook-edit`, `script-edit` → write focused plan, dispatch
  the Staff Engineer for review, integrator on findings, executor.
- `snippet-sync-update` → edit snippet, run `bin/verify-<snippet>-sync.sh --fix`, commit all touched.
- `wiki-append`, `retag-local`, `discard` → direct executor or EM edit.
- `strip-local` → direct edit in originating repo, gated on central SHA. Pull + status check first
  (concurrent EM guard — same as the existing lesson-triage cross-repo mechanics).
- `project-structural` → in originating project repo: plan → review → executor.

## Phase 6 — Per-Project Improvement Queue

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
3. **Structural-enforcement verification** (for each pending lesson naming a tripwire, wiki, or script artifact): check whether a completion entry citing the artifact exists since the lesson's capture date:
   ```bash
   bin/query-records --type completion --where "title~<tripwire-name>" --since "<lesson-date>"
   ```
   A returned record = structurally enforced — exclude from delta count, log as `[enforced]`. Absence = still ambient — count normally.
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
- S records surfaced for DoE reconsideration (doe_escalation: true):
    <list each escalated record: id — wiki target — escalation_reason>
- T worker-emitted doctrine-edit/memory-pointer records downgraded to wiki-* before surfacing:
    <list each downgrade: id — original target → wiki target>
```

The recurrence list is the pressure signal. PM acts or defers — no automatic block.
The `doe_escalation` and downgrade lists are inputs to the DoE's separate doctrine-edit
review pass; they are not actionable in the current run beyond surfacing.

**Forbidden report shapes.** The end-of-run report MUST NOT include defer-chain language ("N candidates for next pass", "run /learn-lessons later to action these", "scope limited to this pass"). Records belong in one of three buckets: (a) applied this run, (b) PM-surfaced with a decision request, (c) mode escalated. Any record that fits none is a routing error — fix the routing, not the report.

## Anti-Patterns

- **Auto-applying central promotions.** PM gates every apply in central mode.
- **Generalizing beyond `tasks/lessons.md`.** Targeted skill. Future generic doc-promotion is separate.
- **Bespoke extra parameters.** Modes are the parameter surface; resist additional flags.
- **Auto-emitting spinoff handoffs.** Section D of the review doc is advisory only.
- **Stripping local before central commit SHA exists.** Phase 5 apply order is load-bearing.
- **`git add -A` for strips.** Always explicit pathspec; concurrent-EM safety.
- **True-deleting discards.** All discards go to archive first; never irrecoverable from Phase 4.
- **Conflating improvement queue with lessons.md.** `lessons.md` is in-the-moment capture; `learn-lessons` is the periodic process that classifies and routes.
- **Same-session capture-and-validate-as-resolved (or as-universal).** Central-mode runs that capture AND validate a lesson in the same pass create unverified-resolution noise or self-confirming-universal loops — the session that surfaced the pattern is the same session asserting its generality. Capture this run; validate in a later run once the pattern has survived a context boundary and recurred in a different context.
- **Default-routing to CLAUDE.md or a CLAUDE.md pointer.** Wikis are the default; `doctrine-edit` and `memory-pointer` are DoE-only and must clear the four-check gate (§ Routing Bias). "It's small, it'll fit" is not a justification — the prior-art-checker surfaces wiki-only lessons when relevant, so a CLAUDE.md pointer per lesson is the same pollution as inlining the rule.
- **Worker proposing `change_kind: doctrine-edit` or `change_kind: memory-pointer`.** Routing error — downgrade to `wiki-*` + `doe_escalation: true` before the record reaches the PM gate. The wiki edit is the load-bearing change; any CLAUDE.md edit is a separate downstream DoE-authored plan.
- **Archiving a lesson because its proposed target violates policy.** Substance and proposed target are independent. A `proposed target: CLAUDE.md` that fails the gate is a routing problem, not a substance problem — reroute to the right wiki / agent prompt / hook / script. `discard` only when the substance itself is ephemeral, already covered, or wrong.
- **Defer-chaining wiki promotions or end-of-run "candidates for next pass."** A run that classifies records with named wiki destinations and defers them is the pattern this skill exists to prevent. Wiki-append/wiki-new with named destinations apply IN THIS RUN (Phase 5 auto-apply contract). Any Phase 8 report line naming records "to be folded next run" is a doctrine violation — apply them, surface them to the PM with a decision request, or escalate the mode. The three buckets are exhaustive; "informational candidates for later" is not a fourth.

## Related

- `coordinator/CLAUDE.md` "Self-Improvement Loop" — references this skill for cadence + capture.
- `~/.claude/tasks/coordinator-improvement-queue.md` — central queue; destination for deferred items.
- `~/.claude/tasks/learn-lessons-config.md` — configured project roots; self-populates on each run.
- `snippets/text-only-recovery-preamble.md` — synced snippet consumed in Phase 2 scout dispatches.
- `archive/lessons-archived/YYYY-MM.md` — per-repo discard archive; append-only, per-month.
