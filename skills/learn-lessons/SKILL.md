---
name: learn-lessons
description: "Processes state/lessons/ YAML entries as doctrine change-requests. 3 modes: local, central, recheck. Triggers on triage/trim/process lessons, promote universals."
version: 1.0.0
---

# learn-lessons — Lesson Processing and Queue Activation

## Overview

`learn-lessons` processes per-entry `state/lessons/*.yaml` files as change-requests against doctrine, agent prompts,
hooks, scripts, wiki guides, and improvement queues. Each lesson routes to one destination with an
explicit change-kind. The skill tracks recurrence across runs, archives discards rather than deleting
them, and surfaces queue depth to inform backlog prioritization.

**Supersedes `coordinator:lesson-triage`** (renamed 2026-05-06; no alias shim).

**Announce at start:** "I'm using the coordinator:learn-lessons skill in `<mode>` mode."

**Anti-transient framing.** The goal is doctrine evolution, not file-size reduction. Success metric:
"did central + project doctrine and queues evolve?"

**No-defer rule (load-bearing).** A `learn-lessons` run that classifies records and then defers
the actionable subset to "the next pass" is a doctrine violation. The defer-chain pattern —
each run pointing at the next-you to do the wiki work — is how the lessons queue grows without
doctrine evolving. **If a record carries `change_kind: wiki-append` or `change_kind: wiki-new`
with a named destination file + section, apply it in THIS run.** The only legitimate deferrals
are (a) cross-mode handoffs that are structurally required (e.g. `strip-local` gated on a
central commit SHA that does not yet exist) and (b) records surfaced to the PM for product or
architectural authorization. "Time-budget" and "scope of this pass" are not legitimate
reasons to defer wiki promotions — the wiki promotion is the work.

## Routing Bias: Wikis Are the Default, CLAUDE.md Is Exceptional

> **Taxonomy + routing reference:** `docs/wiki/learn-lessons-routing.md` § Routing Bias.
>
> Summary: default destination is a wiki guide (`wiki-append` / `wiki-new`). `doctrine-edit` and
> `memory-pointer` are DoE-only and must clear the four-check justification gate (cross-cutting
> tripwire / boot-time-greppable / no existing wiki / no existing CLAUDE.md section) plus the
> char-budget pre-flight before any apply step. Workers route CLAUDE.md-targeted lessons to
> `wiki-append` / `wiki-new` + `doe_escalation: true`. Substance and proposed-target are
> independent — a routing-policy failure is a reroute, not a discard.

## Modes

| Mode | Trigger | Authorization | Output |
|---|---|---|---|
| `local` | `/update-docs` Phase 6 OR direct invoke from a project repo | **Auto-apply** discard/wiki-append/retag/dedupe within bounds + Phase 4.5 age-sweep; surface structural changes to PM | In-place edits, archive appends, queue appends, age-sweep, PM summary |
| `central` | PM-invoked from `~/.claude` central (cross-repo extraction) | **PM gate** per apply; scouts read only, don't mutate remote lessons files | Routing manifest + review doc; apply runs plan → review → executor |
| `recheck` | `state/lesson-triage-recheck-due-*.md` marker fires via `/workday-start` | Auto-extend if delta small; otherwise dispatch central mode | New marker (no work) or full central run |

**Mode default detection.** `/learn-lessons` without `--mode` arg detects cwd: running from `~/.claude`
central → default `central`; else default `local`. Always log the detected mode in the announce-at-start
line.

**Morning-brief framing is advisory.** The skill body's mode-default logic above is authoritative — if cwd is a project repo, mode is `local` even if the morning brief surfaced the central queue depth. PM can override explicitly.

## Heavy-Queue Promotion Sprint (central sub-mode)

When the central queue has overflowed — **≥ ~150 entries, or a large fraction never folded into doctrine** — per-record routing (Phase 2) is the wrong tool: it adds N more lines to a graveyard. Run a **promotion sprint** instead. Dogfooded 2026-05-27 (drained 324 → 190, ~49%, in one session); PM-ratified as the standard heavy-queue procedure.

Shape — split → synth → check → DoE-review → EM-prune:

1. **Split-classify (Sonnet ×2+).** Never one agent over ~150 items (truncation/miss risk). Split the queue into disjoint line-ranges + the delta extraction; each Sonnet emits a flat `L## | bucket | one-liner | target` classification (no dup-grouping — that needs a global view). Buckets are the recurring theme-clusters the EM names from a first read (concurrent-EM git / verify-against-disk / cross-repo-hypothesis / test-discipline / bug-class-sweeps are the empirically dominant five) + a RESIDUAL bucket sub-tagged `code-fix` / `already-shipped` / `project-specific` / `singleton`.
2. **Combine deterministically (EM, not an agent).** `grep`-concatenate the classifications into one manifest per bucket. Mechanizing the merge removes the fabrication risk of a third LLM pass; dup-grouping moves into the synthesizer (which reads full bucket content anyway).
3. **Synthesize (Opus ×1 per doctrine bucket, parallel, DISJOINT wikis).** Each synthesizer consolidates its cluster into wiki append/new (may write a plan), reports the EXACT absorbed queue-line numbers, kicks back items whose home is an agent-prompt/skill/other-wiki (do NOT prune those), flags the Staff Engineer-worthiness, recommends CLAUDE.md pointers (DoE decides). Assign disjoint wiki sets so parallel writes never collide; EM commits serially.
4. **Verify mechanically (EM + Sonnet).** EM: confirm absorbed-lines ⊆ each synthesizer's manifest (no straying) and no cross-bucket line collisions. Sonnet quality-check pass on the diffs: internal dedup, broken cross-links, RAG-bait header quality, out-of-assigned-file edits, truncation. Then **DoE/Opus self-review** of the actual wiki edits for coherence — this replaces a the Staff Engineer pass for *consolidation of already-vetted lessons* (the Staff Engineer is over-spec; reserve him for novel architecture).
5. **EM-serial prune.** `git rm` the absorbed lines. **HARD: re-verify the queue is byte-identical to classification time before pruning by line number** — a concurrent EM's `workstream-complete` commit can append/insert lines and shift every number (the line-number-keyed-drift hazard; → `cleanup-sweep-hazards.md`). Cross-check each absorbed line's current content against its manifest one-liner; if anything shifted mid-file, prune by content, not number. Commit wikis first (durable value), then the prune + `DIRECTORY_GUIDE` + the run-dir audit trail (classify manifests + per-bucket reports + quality-check + pruned-line snapshot) so `git log` carries the full line→wiki provenance.

RESIDUAL is **not** sprint material — singletons don't consolidate. Surface the residual disposition to the PM as an explicit decision; do not silently re-queue (defer-chain anti-pattern). Disposition by sub-tag:

- `singleton` → individual wiki folds, or defer to next central run (PM's call).
- `code-fix` → `state/bug-backlog.md` (self/central-owned) — actionable code, wrong surface for the doctrine-promotion queue.
- `project-specific` → the **owning repo's** live backlog.
- `already-shipped` → discard-archive.

**HARD — re-home before you prune; a removed entry must land in a live, actionable home, not only an archive file.** Before `git rm`-ing any residual entry, classify whether it still has a live home:
- **Has a live home** (sourced from the owning repo's `state/lessons/` dir, which that repo's own local `/learn-lessons` re-surfaces; or already tracked in a sibling queue/backlog) → safe to prune from central; the central line was a redundant pointer.
- **No live home** (sourced from a code file, plan doc, or review-findings artifact — the central queue line was the *only* live tracker) → **route it to its owning repo's backlog/inbox BEFORE pruning.** For a sibling repo, deliver via `cross-repo-memo` (or hand-write the single-delivery inbox memo if the CLI is down) and hand the PM the receiver path. Pruning a no-live-home entry into only the run-dir archive snapshot is **data loss disguised as cleanup** — the archive file is provenance, not an actionable home, and nobody triages it. The 2026-05-27 dogfood hit exactly this: 3 of 7 sibling entries (code/plan-sourced) had no lessons home and were bare-pruned; caught on PM review, re-homed via hand-written inbox memos. Make the live-home classification a per-entry gate, not an afterthought.

## When to Trigger / Don't Trigger

**Trigger:**
- Per-project periodic maintenance via `/update-docs` Phase 6 (local mode)
- PM names "learn lessons", "lesson triage", "promote universals" (central mode)
- A `state/lesson-triage-recheck-due-*.md` marker fires (recheck mode)
- A project's `state/lessons/` directory exceeds ~50 entries (local mode)

**Don't trigger:**
- Reading lessons for context — that's a Read tool call, not a learn-lessons invocation
- A specific lesson is being acted on individually — that's normal change work
- The lessons file was just touched in the same session (let it settle)

## Phase 0 — Configuration

Config file: `learn-lessons-config.md` under central state (resolves via `coordinator_state_root --central`; central state lives in example-orchestration-hub — see `docs/wiki/state-placement-law.md`).

**Discovery roots come from the machine-local registry, not a committed list.** Roots are derived
PER-MACHINE by `${CLAUDE_PLUGIN_ROOT}/bin/learn-lessons-roots.sh` — it emits `$CLAUDE_HOME` plus each
registered `machine-local get repos.*` that resolves on disk (skip-absent), minus publish-target/mirror
repos (a publish target is an OUTWARD mirror, never a lessons source). A machine with only a subset of
repos on disk is normal — absent repos are silently skipped, never an error. This helper is the single
source of truth for "which repos does learn-lessons process here," and it works on any machine that
installs coordinator-claude, including a fresh install with nothing registered (emits just `$CLAUDE_HOME`).

### Registering a repo

There is no committed roots list to hand-edit. The old absolute-path sentinel was retired 2026-06-19 —
it baked one machine's paths into a git-tracked file and did not survive a machine change (and its
self-population append was silently broken). To make a repo's lessons visible to central runs, register it
once in the machine-local registry: `machine-local set repos.<slug> <path>`.
`${CLAUDE_PLUGIN_ROOT}/bin/learn-lessons-config-update.sh` (invoked at Phase 0) is now an idempotent no-op
that prints exactly this hint when run from an unregistered repo; it never mutates a tracked file.

### Skip-absent (replaces the old stale-entry prune)

The registry helper already skip-absents unresolvable roots, so there is **no config-prune step in any
mode**. The registry — not a config sentinel — is the prunable SSoT: a genuinely retired repo is removed
via `machine-local` (a registry concern), not by learn-lessons.

### Fallback chain

1. **Registry helper** `${CLAUDE_PLUGIN_ROOT}/bin/learn-lessons-roots.sh` (primary).
2. **Optional supplemental sentinel** in `state/learn-lessons-config.md`
   (`<!-- BEGIN learn-lessons-roots -->` … `<!-- END learn-lessons-roots -->`), empty by default — for
   non-registry roots only.
3. **Default:** `$CLAUDE_HOME` only (the helper emits it unconditionally even with an empty registry — the
   OSS fresh-install case).

`state/learn-lessons-config.md` retains only the `central_volume_threshold` knob plus the optional
supplemental sentinel. No hardcoded machine-specific paths.

## Per-Lesson Routing Schema and Change-Kind Taxonomy

<!-- Negative-spec: Lesson facets (trigger/why/how_to_apply) are author-supplied at capture
     time — do NOT post-hoc LLM-extract them from a lesson's existing prose body (same
     fabrication hazard the routing verify-gate guards against). See docs/wiki/lessons-schema.md
     § Structured Facets for the full convention and required:/optional: rationale. -->

> **Full schema + closed-enum taxonomy:** `docs/wiki/learn-lessons-routing.md`
> §§ Per-Lesson Routing Schema, Change-Kind Taxonomy, Lesson Scope Classification.
>
> Key fields: `scope` (universal | project | wiki-only | discard), `change_kind` (closed enum
> — see wiki), `doe_escalation` (worker flag; wiki edit lands regardless; DoE attention only).
> Workers MUST NOT emit `change_kind: doctrine-edit` or `change_kind: memory-pointer` — those
> are routing errors; downgrade to `wiki-*` + `doe_escalation: true` at consolidation.

## Phase 0.5 — Dedupe Pass (central mode only)

Re-Read the queue from disk; build a hash-set of normalized one-line summaries; flag entries with semantic-duplicate matches for merge before Phase 3 routes them as independent entries.

## Phase 1 — Discovery

Enumerate roots via `${CLAUDE_PLUGIN_ROOT}/bin/learn-lessons-roots.sh` (per-machine, registry-derived;
see Phase 0 — NOT a committed sentinel). For each `state/lessons/` directory found under those roots, capture:
- Total entry count (number of `.yaml` files in `state/lessons/`)
- Tagged universal entry count (`query-records.js --type lesson --where scope=universal` count)
- Status breakdown (open/deferred/applied/triaged, from YAML `status:` fields)

Apply skip threshold: skip repos with zero universals AND fewer than 30 entries — diminishing returns.

Log skipped repos with a one-line reason each. Apply self-exclusion for the central lessons directory (`$(coordinator_state_root --central)/lessons/`, example-orchestration-hub-resident — see `docs/wiki/state-placement-law.md`)
in central mode (central is the doctrine target, not a promotion source).

## Phase 2 — Routing

**Routing has two layers, split along the determinism seam:**

- **Extraction (deterministic, no LLM):** enumerate each `state/lessons/` directory into verbatim records via `bin/extract-lessons.py`. Faithful extraction of source text is a parse, not a judgment call — running it through an LLM is what produced the 2026-05-24 fabrication failure (3/3 Haiku scouts invented plausible-but-nonexistent records to fill the routing shape we'd demanded). With a parser, fabrication of source content is *structurally impossible*, not just less likely. The script also empirically out-performs hand extraction: on the 2026-05-24 dogfood it found 77 dated delta entries vs. an Opus-by-hand pass that found 28 — humans/agents miss entries in long files; a parse finds every one.
- **Routing (bounded judgment, gated):** classify each extracted record into `scope` + `destinations[].target` + `change_kind` against the routing schema below. This is real judgment but bounded (choose from an enumerated set of existing wikis / agent prompts / hooks). Haiku is acceptable here ONLY behind the Phase 5 verify gate; for small deltas (≤ ~30 records) the EM does routing directly.

### Central mode — extraction step

For each surviving repo, produce **two** extractions — a full one (the verify oracle for Phase 5) and a delta-filtered one (the router input). The script returns in ms, so this is cheap:

```bash
# Full extraction — the verify-gate oracle. Always run, no --since.
bin/extract-lessons.py extract <repo>/state/lessons/ --shortname <shortname> \
  -o ~/.claude/tasks/learn-lessons-YYYY-MM-DD/<shortname>-extracted-full.yaml

# Delta extraction — the router input, filtered to the window since the last central run.
bin/extract-lessons.py extract <repo>/state/lessons/ --shortname <shortname> \
  --since <last-central-run-date> \
  -o ~/.claude/tasks/learn-lessons-YYYY-MM-DD/<shortname>-extracted-delta.yaml
```

**Why two extractions:** full (no `--since`) = verify oracle (undated real entries must pass it); delta (`--since`) = router input. `--since` excludes undated entries (`undated_excluded_under_since: N` in meta) — route undated lessons via a separate non-`--since` pass over the full extraction. Ids are `<shortname>-L<line>` (header start-line); the routing layer must cite them verbatim.

### Central mode — routing step

The EM (or a delegated router) reads the per-repo `*-extracted.yaml` files and produces `*-records.yaml` with routing decisions per the schema below. Routing records MUST set `id` and `source` to values that exist in the matching extraction (the Phase 5 verify gate rejects fabricated references).

**Routing rules (apply at any altitude — EM-direct, Haiku-router, or Sonnet-router):**

- **Lessons asserting a mechanical contract must cite executable authority, not narrative confidence.** A lesson stating an env-var value, a path resolution rule, an API signature, an exit-code, or any other mechanical fact (vs. an operating discipline) must point at the executable witness — a passing contract test, the live tool's observed behavior, official docs — in its body. When the routing record's source lesson is a mechanical-contract assertion, route as: (a) `wiki-append` with rationale flagging missing-citation if no executable witness is cited but one plausibly exists; (b) `discard` if no executable witness can be located OR an executable witness contradicts the lesson's assertion (the lesson is wrong, not just under-cited). The 2026-05-23 `${CLAUDE_PLUGIN_ROOT}` lesson — exactly backwards for days, would have led the next EM to revert a correct 91-file fix — is the empirical case for the contradiction branch: three independent authorities (Claude Code docs, `test_claude_plugin_root_resolution.py`, the live tool's substitution) converged against the lesson; narrative confidence in a prose log is not evidence. Rule of thumb: if a lesson and a passing contract test disagree on a mechanical fact, correct the lesson, not the test.
- Conservative on domain-specific candidates — `retag-local` is the safer default for entries that look universal-tagged but are really domain (UE / game-dev / web-dev / data-science). **Caveat when applying `retag-local`:** do NOT blind string-replace `[universal]` → `[domain]` — a naive replace corrupts prior retag-history comments and any in-body `[universal]` reference. Edit only the tag on the entry's header line. Note also that `extract-lessons.py` sets `tag_universal` if `[universal]` appears *anywhere* in the block, so a leftover in-body mention keeps an entry classified universal after a header-only retag — strip stray in-body occurrences too.
- **NEVER use `change_kind: doctrine-edit` or `change_kind: memory-pointer`** — DoE-only.
  Route CLAUDE.md-targeted lessons to `wiki-append`/`wiki-new` + `doe_escalation: true`.
  See § Routing Bias (`docs/wiki/learn-lessons-routing.md` § Routing Bias).
- **`wiki-append`/`wiki-new` destinations must be reachable, not merely exist.** Placement in a wiki file is not sufficient — a lesson is only "routed" if its target wiki is reachable from at least one surface an agent actually traverses: the `docs/wiki/DIRECTORY_GUIDE.md` index, a skill step, a dispatch preamble, or the prior-art-checker corpus. An orphan wiki (file exists but is unlinked from every traversal surface) is functionally a discarded lesson with file-bloat — the doctrine inside it is never recalled. Before routing to a `wiki-append`/`wiki-new` target, verify the wiki appears in `DIRECTORY_GUIDE.md` or is referenced from a skill/agent/hook surface. If the target wiki is orphaned, either (a) link it from `DIRECTORY_GUIDE.md` as part of the same apply, or (b) reroute to an existing linked wiki. This mirrors the "enumerate contact-points" rule for adding a convention (→ coordinator `CLAUDE.md` § Adding a Convention to the Coordinator System) — a lesson that reaches no contact-point has no more impact than a deleted one.

If a Haiku/Sonnet router is dispatched, the dispatch prompt MUST include the verify-gate clause: *"Every routing record's `id` MUST appear in the cited `*-extracted.yaml`. Inventing a record under a fabricated id will be caught by `extract-lessons.py verify` at Phase 5 and fail the run."* The gate is mechanical (Phase 5); the prompt clause is the design-as-offers framing that lets the router self-check before producing output.

### Central mode — undated-pass (required after delta routing)

After the delta routing pass lands, run a second routing pass per repo for undated `[universal]` entries. `--since` excludes them from the delta extraction (`undated_excluded_under_since: N` in extraction meta), so without this pass every undated universal accrued in a project's lessons silently leak past central promotion. The 2026-06-14 central run is the empirical case: 53 dated records routed in delta, 7 undated+universal records left unrouted, 1 stripped without routing (doctrine loss recoverable from `git show 434365dcb^:state/lessons.md`). The Phase 8 `undated_universal_remaining` counter (below) is the fail-close that surfaces a leak before `COMPLETE` lands. This Phase promotes the passing acknowledgement at the "Why two extractions" note above to a checkable Phase step.

**Placed in Phase 2 (not Phase 4.x):** undated records ARE routing input — they consume the same router → verify-gate → apply pipeline as delta records. A post-archive home would run after the archive pass that depends on routed records and would create a circular dependency with Phase 8's `COMPLETE`-sentinel fail-close.

```bash
# VERBATIM filter: select undated+universal records from full extraction (per repo).
# extract-lessons.py already emits per-record `undated` + `tag_universal`; no API change.
# stdin-streaming form — avoids Windows/Git-Bash msys path resolution mismatches that
# break Python stdlib open() on `/c/Users/...` paths.
python3 -c "
import yaml, sys
data = yaml.safe_load(sys.stdin)
records = [r for r in data.get('records', []) if r.get('undated') and r.get('tag_universal')]
data['records'] = records
yaml.safe_dump(data, sys.stdout, sort_keys=False)
" < "${RUN}/<shortname>-extracted-full.yaml" > "${RUN}/<shortname>-extracted-undated-universal.yaml"
```

The filtered extraction then flows through the **same** router → Phase 5 verify-gate → apply pipeline as the delta records. If a Haiku/Sonnet router is dispatched on this pass, the dispatch prompt MUST cite the verify-gate clause above. Output artifact naming: `<shortname>-extracted-undated-universal.yaml` per repo (established by 2026-06-14 run).

### Local mode

Same two layers, scoped to one repo:

```bash
bin/extract-lessons.py extract state/lessons/ --shortname <repo> \
  -o tasks/learn-lessons-YYYY-MM-DD/extracted.yaml
```

EM produces `records.yaml` inline from the extraction (no router dispatch — local-mode deltas are always small enough for EM-direct routing).

## Phase 2.6 — Lessons-Outbox Drain (Central Mode Only)

<!-- Spec backlink: archive/specs/2026-06/2026-06-15-universal-lesson-routing-mechanical-capture.md § C4 -->
<!-- Negative-spec: Do NOT read outbox YAMLs during local-mode runs — the outbox drain is a
     DoE-owned central-mode operation only. Local-mode routing writes TO the outbox via
     coordinator-lesson-promote; Phase 2.6 reads FROM the outbox. -->

**Purpose:** After the delta-routing and undated passes above, the central run drains any structured
YAML entries already queued in peer-repo outboxes by prior `coordinator-lesson-promote` invocations.
These entries were produced by local-mode runs on machines that had `[universal]` + central-wiki-target
lessons and called the CLI rather than appending to their improvement queues.
Schema reference: `docs/wiki/lessons-outbox-schema.md`.

### Step 1 — Enumerate peer repos

Read the `[repos]` table from `~/.claude/machine-local/registry.local.toml`. This is the canonical
source for all registered peer repos on this machine — the same registry that Phase 0/1 discovery roots
derive from via `${CLAUDE_PLUGIN_ROOT}/bin/learn-lessons-roots.sh` (the helper centralizes this read;
the raw enumeration is shown here because the drain also needs each peer's outbox path, not just its root).

```bash
# Enumerate registered peers. machine-local keys returns dotted keys; resolve each to its filesystem path:
machine-local keys | grep '^repos\.' | while IFS= read -r key; do
  machine-local get "$key"   # filesystem path to peer repo
done
```

### Step 2 — Sync each peer repo (skip-with-warning if absent)

For each registered peer repo path:

1. **Verify on-disk.** If the peer path does not resolve on this machine, emit a warning and skip:
   `"outbox-drain: peer <shortname> not on disk — skipping (DoE drain runs from Striker)"`.
   Do NOT error-exit on absent peers; the drain is designed to run from a machine with all repos
   checked out (typically Striker) but must degrade gracefully elsewhere.

2. **Fetch and pull** to ensure the outbox is current:

   ```bash
   git -C "<peer-path>" fetch
   git -C "<peer-path>" pull --ff-only
   ```

   If `pull --ff-only` fails (non-fast-forward), emit a warning and skip that peer:
   `"outbox-drain: peer <shortname> non-FF pull — skipping"`. Do NOT force-merge.

3. **Precheck for uncommitted state-tree modifications** (required by the DoE-owned cross-repo
   state drain contract — see `docs/wiki/cross-repo-communication.md`
   § Doctrine seeding vs. code/install-surface change > DoE-owned cross-repo state drain (third axis)):

   ```bash
   git -C "<peer-path>" status --porcelain --untracked-files=no
   ```

   If the output is non-empty (peer has uncommitted state-tree modifications), emit a warning and
   skip: `"outbox-drain: peer <shortname> has uncommitted modifications — skipping writeback;
   drain routing will proceed but writeback is deferred"`. The routing pass still runs on the
   already-fetched outbox content; only the writeback (Step 6) is deferred for this peer.

### Step 3 — Read peer outbox entries

For each peer that passed Step 2, glob `<peer-path>/state/lessons-outbox/*.yaml` excluding the
`drained/` subdirectory:

```bash
find "<peer-path>/state/lessons-outbox/" -maxdepth 1 -name "*.yaml" -not -path "*/drained/*"
```

Parse each YAML file per the schema at `docs/wiki/lessons-outbox-schema.md`. Required fields:
`id`, `created`, `from_repo`, `title`, `body`, `change_kind`, `target_wiki`.
Entries with `target_wiki: unknown` are queued for manual triage — do NOT route them through
the apply pipeline; surface them to the PM in the Phase 8 report.

### Step 4 — Deduplicate across repos

Build a dedup index keyed on the triple `(title, change_kind, target_wiki)`.

- **Multiple entries sharing the same triple from different repos are NOT a collision** — they are
  a convergence signal. Record the `from_repo` values as a priority annotation on the merged entry.
  Apply the merged entry once with elevated confidence, noting the source repos in the provenance.
- **Entries with unique triples** proceed independently.

Log the dedup results: `"outbox-drain: N entries across M repos → K unique after dedup (J convergence signals)"`.

### Step 5 — Apply via existing central-mode pipeline

Route each deduplicated entry (and each convergence-merged entry) through the **existing** central-mode
router → Phase 5 verify-gate → apply pipeline, as if they were delta-routing records from Phase 2.
Use the outbox `body` field as the lesson content and `target_wiki` as the destination.
The `change_kind` field maps directly to the Phase 2 routing schema (see `docs/wiki/lessons-outbox-schema.md`
§ Change-kind enum).

`target_wiki: unknown` entries are surfaced to the PM for manual triage; do NOT pass them to the
apply pipeline.

For each entry routed successfully through the apply pipeline, append its source YAML path to a
`$drained_paths` list. Entries that fail apply (verify-gate red or apply error) are NOT added to
`$drained_paths` and are left in place in the peer's outbox for the next drain cycle.

### Step 6 — Writeback (DoE-owned cross-repo state drain)

> Authority: `docs/wiki/cross-repo-communication.md` § Doctrine seeding vs. code/install-surface
> change — **DoE-owned cross-repo state drain (third axis)**. The outbox YAMLs are physically
> distributed instances of DoE-owned state; the drain confirmation (`git mv` to `drained/`) is
> DoE-owned state management, not a content addition to peer-owned surfaces.

For each peer repo where Step 3 found entries AND Step 2 precheck passed (no uncommitted
state-tree modifications), perform the following writeback:

1. **Determine branch base.** Use the peer's `main` branch as the cut point:

   ```bash
   git -C "<peer-path>" fetch origin main
   # Branch cut point = origin/main (never the peer's active workstream branch)
   ```

2. **Create drain branch on peer repo:**

   ```bash
   DRAIN_DATE=$(date +%Y-%m-%d)
   git -C "<peer-path>" checkout -b "drain/${DRAIN_DATE}-doe-pull" origin/main
   ```

3. **Move drained entries from `state/lessons-outbox/` to `state/lessons-outbox/drained/`:**

   ```bash
   mkdir -p "<peer-path>/state/lessons-outbox/drained/"
   for yaml_file in $drained_paths; do
     git -C "<peer-path>" mv "state/lessons-outbox/$(basename $yaml_file)" \
       "state/lessons-outbox/drained/$(basename $yaml_file)"
   done
   ```

4. **Create the DoE-side drain manifest BEFORE the first peer commit.** Write
   `$(coordinator_state_root --central)/lessons-outbox-drained-manifest.<DRAIN_DATE>.json` (central
   state lives in example-orchestration-hub — see `docs/wiki/state-placement-law.md`) enumerating all drained
   entries as `[{peer, filename, id, title}]`. The manifest must exist on disk before any peer
   commit can cite its path in the commit message. If creation fails, abort the drain — do NOT
   commit on any peer.

5. **Commit on the peer repo's drain branch.** Commit message MUST carry:
   - `[doe-state-drain]` prefix
   - Name the DoE-side drain ledger: `$(coordinator_state_root --central)/lessons-outbox-drained-manifest.<date>.json`

   ```bash
   git -C "<peer-path>" commit -m "[doe-state-drain] drain <N> outbox entries to drained/ — manifest: $(coordinator_state_root --central)/lessons-outbox-drained-manifest.${DRAIN_DATE}.json"
   ```

6. **Do NOT push the drain branch.** The branch is created locally on the DoE machine. The peer EM
   pulls and merges on their own schedule. Record the local branch name in the Phase 8 report under
   the drain summary.

7. **Return to peer's previous branch** to leave the peer repo in a clean state:

   ```bash
   git -C "<peer-path>" checkout -
   ```

   If `git checkout -` fails (e.g., peer was in detached HEAD or mid-rebase before drain —
   `git status --porcelain --untracked-files=no` does NOT detect mid-rebase state), record the
   error in the Phase 8 drain summary AND leave a
   `DRAIN-CHECKOUT-FAILED-<DRAIN_DATE>` breadcrumb file in the peer's
   `state/lessons-outbox/drained/` so the next drain cycle can adjudicate.

**Writeback skipped (Step 2 precheck failed):** record in the Phase 8 drain summary with reason.
The PM may re-run the drain pass after the peer's concurrent work settles; the outbox entries
remain in `state/lessons-outbox/` and will be picked up on the next central run.

### Phase 2.6 end-of-step summary (feeds Phase 8 report)

Record the following for the Phase 8 end-of-run report:

```
outbox-drain summary:
- Peers enumerated: N  (M on disk, K skipped-absent, J skipped-non-ff, L skipped-dirty-tree)
- Outbox entries read: N total (before dedup)
- After dedup: K unique entries (J convergence-merged from multiple repos)
- target_wiki: unknown (manual triage): U entries
- Entries routed through apply pipeline: R
- Writeback branches created: W  (<shortname>: drain/<date>-doe-pull, ...)
- Writeback deferred (dirty tree): D peers
- DoE drain manifest: $(coordinator_state_root --central)/lessons-outbox-drained-manifest.<date>.json
```

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

Before removing any YAML entry from `state/lessons/`, append it to the per-repo archive file.

**Archive path:** `archive/lessons-archived/YYYY-MM.md` within each repo where local mode runs.
- `~/.claude/archive/lessons-archived/2026-05.md` for runs in May 2026.
- Create `archive/lessons-archived/` if absent.
- Append-only: multiple runs in the same calendar month append to the same file (do NOT overwrite).

**Provenance header per entry (write this line immediately before the entry body):**
```
# Discarded by /learn-lessons on YYYY-MM-DD HH:MM from state/lessons/<filename>.yaml
```

EM judges discard inline — no PM confirmation gate. Archive is recoverable (grep by date/source/line) but not surfaced by default.

**Reversed-lesson annotation (do NOT delete — annotate instead).** When a `[universal]` or doctrine-targeted lesson is overturned, annotate in place rather than deleting:

```
> **INVERTED 2026-05-14:** <one-line reason for reversal> (replaced by: <new doctrine pointer>)
```

Place the blockquote directly under the lesson body. Deletion reserved for lessons that were factually wrong from the start or exact duplicates — not for "we changed our minds" reversals.

## Phase 4.5 — Local-Mode Age-Sweep (Bound the File)

**Local mode only.** `state/lessons/*.yaml` entries are enumerated by `/learn-lessons`, the central-mode strip-local
pull-pass, and `/workstream-start` — NOT at normal session open (it's a capture queue, not Tier 0).
Without this sweep, local repos accumulate 200–350 KB in a month of high-volume capture
(empirical: three sibling repos at 193/266/107 entries after a month). `[universal]` entries
promoted to central wikis have their durable home there; once older than the last completed central
run they're redundant in `state/lessons/`. Age-sweep archives them; keep everything else.

**Mechanism — `bin/age-sweep-lessons.py`** (deterministic; reuses `extract-lessons.py`'s entry-boundary
parser so cuts land on identical boundaries; default dry-run):

```bash
# 1. Cutoff = most recent COMPLETED central run. Central mode writes a `COMPLETE`
#    sentinel in its run dir on success (Phase 8); a dir WITHOUT it is in-progress or
#    aborted and MUST NOT become the cutoff (a half-finished run never promoted its
#    entries, so sweeping against it would archive un-promoted universals).
cutoff=$(for d in ~/.claude/tasks/learn-lessons-20*/; do
           [ -f "${d}COMPLETE" ] && basename "$d" | sed 's#learn-lessons-##'
         done | sort | tail -1)
# 2. No completed central run reachable → SKIP the age-sweep (do NOT guess a cutoff;
#    the script also fail-closes on a blank --before). A sibling that can't reach
#    central must not have its boot blocked or its universals swept on a guess.
if [ -z "$cutoff" ]; then
  echo "age-sweep: no completed central run reachable — skipping"
else
  bin/age-sweep-lessons.py <repo-root> --before "$cutoff"            # dry-run preview
  bin/age-sweep-lessons.py <repo-root> --before "$cutoff" --apply    # apply
fi
```

**Partition** (per entry, on the CURRENT file — drift-safe under concurrent edits):
ARCHIVE iff `[universal]`-tagged AND dated AND `date < cutoff`; KEEP everything else
(project-specific entries — no central home, any age; undated entries — can't prove aged; universals
within the window — may not be promoted yet).

**Cutoff is event-based, not age-based.** `--days N` is the wrong tool for high-volume repos (a month of entries in a month = `--days 30` no-ops). The safe cutoff = "had a central run" = last completed central run date. `--days N` exists only as a fallback when no central-run history is reachable; prefer `--before <last-central-run-date>`.

**Auto-apply in local mode** (reversible — archive file + git history are the recovery net). Run on a
clean tree; commit with an explicit pathspec (`git rm -- state/lessons/<swept-files>.yaml && git add -- archive/lessons-archived/<month>.md`)
— never `git add -A` (concurrent-EM safety). Report the archived count in the Phase 8 summary.

**Do NOT run the bulk age-sweep against a sibling repo from a central-mode run.** Bulk-sweeping
another repo's `state/lessons/` directory centrally — every aged universal at once — races that repo's own
in-flight local runs (the 2026-05-27 collision: a sibling's `state/lessons/` was being modified mid-trim while
central considered sweeping it). Each repo's *own* local-mode run handles its bulk age-sweep.

This prohibition bans **bulk** age-sweep only — NOT the **targeted strip-local** that central applies as the second half of each promotion (§ Phase 5 Apply order). Targeted strip is bounded by the promotion set and yields to drift; central promotes and strips-just-promoted; local mode bulk-bounds the residue.

**Reverse race (local age-sweep vs. in-flight central run):** the `COMPLETE`-sentinel cutoff handles it — an in-flight run hasn't written `COMPLETE` yet, so the local sweep's cutoff resolves to the prior completed run and leaves the current window untouched. Sentinel is the sync primitive; no manual coordination needed.

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

**Multi-repo mode:** pass the run-dir as the extraction arg — auto-engaged when multiple `*-extracted-full.yaml` files are present; multiple files for the same shortname = exit 2 (operator error). EM-direct routing on small deltas still runs the gate — catches typos and stale line-citation drift.

### When the gate fails — recovery playbook

A non-zero exit is not a dead end; the stderr output names every ungrounded record. Don't proceed to apply until grounded. The gate fails in one of four shapes; the recovery differs:

1. **Stale extraction.** The routing file was produced against an older enumeration of a `state/lessons/` directory that has since been modified (a concurrent EM session added or removed entries). Re-run `extract` to refresh `<shortname>-extracted-full.yaml`, then re-run `verify`. If the routing record's cited line now lands on a different real entry whose `title` no longer overlaps the routing summary, this is actually shape (2).
2. **Router inventing (LLM fabrication).** A Haiku/Sonnet router cited an id or line that never existed. Re-dispatch the router with two amendments: (a) attach the failing-ids list inline so the router sees specifically what was rejected; (b) re-emphasise the verify-gate clause from the original dispatch prompt. Do NOT hand-correct the router's output — that launders the fabrication into the audit trail.
3. **Summary-swap (subtle fabrication).** Line and id ground but the routing summary describes a different entry's content. The title-overlap check catches this. Same recovery as (2) — re-dispatch the router; do not hand-edit.
4. **EM hand-routing drift.** EM-direct routing on a small delta cited a line off by N (concurrent edits to source shifted line numbers, or the EM transcribed wrong). EM corrects the routing file in place against current extraction; re-run verify.

Re-run `verify` to green before proceeding to apply. Treat persistent gate failures (≥2 re-dispatches of the same router still failing) as a signal to drop to EM-direct routing for the affected slice; the model isn't going to converge on a corpus it can't ground in.

### Concurrent-edit guard

Before applying any queue entry, re-Read the queue from disk to catch concurrent edits since Phase 3 routing.

### Local mode — auto-apply bounds

> **Full auto-apply vs. PM-surface routing table:**
> `docs/wiki/learn-lessons-routing.md` § Local Mode — Auto-Apply Bounds.
>
> Auto-apply: `discard`, `wiki-append` (mandatory same-run), `wiki-new` (named destination),
> `retag-local`, dedupes, Phase 4.5 age-sweep.
> PM-surface: `doctrine-edit`, `memory-pointer`, `doe_escalation: true` records,
> `agent-prompt-edit`, `hook-edit`, `script-edit`, `snippet-sync-update`, `project-structural`.
> `strip-local` is NOT PM-surface — auto-applies as second half of the central chain.
> Universals-pending: if ≥ 20 unactioned `[universal]` entries, surface to PM before proceeding.

### Central mode — PM gate

Present review doc to the PM. Per record, PM authorizes:
- **(a) apply now** — proceed to apply cycle (plan → reviewer → executor)
- **(b) defer to improvement queue** — append a main-line-only entry to
  the central improvement queue (`$(coordinator_state_root --central)/coordinator-improvement-queue.md`;
  central state lives in example-orchestration-hub — see `docs/wiki/state-placement-law.md`; DR-056 amended 2026-05-17 —
  no `recurring:` / `resolution:` sub-lines)
- **(c) reject** — drop with reason captured in review doc

Section A (strip-only), Section B (central change), Section C (re-tag) all need PM go-ahead.
Batch authorization is OK ("apply all of A, defer all of B-MEDIUM, reject B-LOW").

### Apply order

**Central first, then strip-local — both in the same run, both DoE-applied.** Strip-local records have `depends_on` pointing at the central change; do not strip until the central commit SHA exists. Once that SHA lands, the DoE applies the strip in the sibling repo in the same central run — do **not** defer to "the sibling's next local-mode age-sweep" (deferral is the boot-tax pattern; every day the redundant entry remains it costs every consumer that enumerates `state/lessons/`). Concurrent-edit safety: pull-then-content-match-then-prune; skip-and-warn on drift; age-sweep catches residue.

### Strip-list orphan-rejection (mechanical, before strip-executor dispatch)

Every `id` in the strip-list MUST correspond to a record in `records.yaml` whose `change_kind` routes to a real destination (NOT `discard`). Reject any strip-line lacking a corresponding routed record — that is the 2026-06-14-shape mistake (strip without route, doctrine loss). This actions the 2026-05-30 improvement-queue entry on `bulk strip-universals.py` assuming-all-promoted false-on-heavy-capture-days. Implementation is a short inline Python check from the dispatching skill; do NOT add a new bin script:

```bash
# VERBATIM: reject orphan strip-lines.
# Streamed via shell pipelines — avoids Windows/Git-Bash msys path resolution
# mismatches that break Python stdlib open() on `/c/Users/...` paths.
routed_ids=$(python3 -c "
import yaml, sys
records = yaml.safe_load(sys.stdin).get('records', [])
for r in records:
    if r.get('change_kind') and r['change_kind'] != 'discard':
        print(r['id'])
" < "${RUN}/records.yaml")

orphans=$(python3 -c "
import yaml, sys, os
routed = set(os.environ['ROUTED_IDS'].split())
strip_list = yaml.safe_load(sys.stdin).get('strip', [])
for s in strip_list:
    if s.get('id') not in routed:
        print(f\"  {s.get('id')} — in strip-list, no routed record\")
" ROUTED_IDS="$routed_ids" < "${RUN}/strip-list.yaml")

if [ -n "$orphans" ]; then
    echo "STRIP-ORPHAN-REJECT:" >&2
    echo "$orphans" >&2
    exit 1
fi
```

**Placement at Phase 5 § Apply order (not Phase 5 verify-gate pre-flight) is load-bearing** — verify-gate catches fabrication of source references (cited id doesn't exist in extraction); orphan-rejection catches routing-set gaps (cited id exists but has no routed sibling). Both are necessary because they fail on different invariants. Complementary to `docs/wiki/learn-lessons-routing.md` § "Cross-Repo Strip — Content-Signature Matching, Not Line-Number Partition", which guards the strip mechanism against source-file drift; this check guards against routing-set gaps. Both fire at strip dispatch time.

### Per-record apply dispatch

> **Full dispatch table + CLAUDE.md pre-flight gates:**
> `docs/wiki/learn-lessons-routing.md` § Per-Record Apply Dispatch.
>
> Includes: CLAUDE.md justification pre-flight (four-check gate), char-budget pre-flight
> (≤36K / 36-38K / 38-40K / >40K thresholds), and the per-change-kind dispatch table.
> `strip-local` procedure: pull-then-content-match-then-Edit + explicit-pathspec commit,
> gated on central commit SHA; skip on non-FF pull, dirty tree, zero-match, or multi-match.

## Phase 6 — Per-Project Improvement Queue

**Create-if-absent.** If `state/improvement-queue.md` does not exist in the current project repo,
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

### Universal-routing classifier branch

When the classifier returns a `[universal]`-tagged entry, apply this routing fork before any queue append:

**Case A — `[universal]` + central-wiki target** (`target_wiki` resolves to a path under `~/.claude/docs/wiki/`, NOT under the project's own `docs/wiki/`): invoke `coordinator-lesson-promote` mechanically with the classifier's structured fields. Do NOT append to `state/improvement-queue.md` for this case.

```bash
# TEMPLATE: adapt paths/values
coordinator-lesson-promote \
  --title "<classifier.title>" \
  --body "<classifier.body>" \
  --change-kind "<classifier.change_kind>" \
  --target-wiki "<classifier.target_wiki>" \
  --evidence "<source-lesson-file>:<line>"
```

The CLI writes a schema-conforming YAML to `state/lessons-outbox/<ISO-ts>-<slug>.yaml`. Schema reference: `docs/wiki/lessons-outbox-schema.md`. The DoE drains the outbox on the next central run — see `coordinator/CLAUDE.md § Improvement Queue` for the full routing contract.

**Case B — `[universal]` + project-local wiki target** (`target_wiki` resolves to a path under the project's own `docs/wiki/`, or is a local-wiki name): auto-apply locally as today — unchanged.

**Case C — project-scope entries** (classifier returns `scope: project`): route to `state/improvement-queue.md` markdown — unchanged.

**Routing:** scope → queue mapping in `docs/wiki/learn-lessons-routing.md` § Lesson Scope Classification.

## Phase 7 — Recheck Marker

Drop `state/lesson-triage-recheck-due-<today + recheck_cadence_days>.md`. Single line:
```
Next learn-lessons cadence due YYYY-MM-DD. Run /learn-lessons from ~/.claude (central mode).
```

Default cadence: 21 days. `/workday-start` Step 1.7 globs `state/lesson-triage-recheck-due-*.md`.

**Volume trigger (companion to the date cadence).** A fixed date cadence under-runs in busy weeks —
exactly when the sibling lessons-queue floor (bounded by Phase 4.5 at `rate × days-since-last-central-run`)
balloons fastest. So `/workday-start` Step 1.75 also runs `central-run-due.sh`, which counts `[universal]`
entries accrued across the configured roots since the last **COMPLETE** central run and surfaces a
"central run due (volume)" nudge at `central_volume_threshold` (config, default 150). Whichever fires
first — date or volume — surfaces the nudge; both are PM-actioned, never auto-dispatched. This bounds the
universal floor adaptively. (It does NOT bound project-specific entries — those have no central home and
are the sibling local-mode's fold-to-wiki / discard concern, not the central run's.)

### Recheck mode behavior

1. Run Phase 1 discovery across all configured roots.
2. Compute delta: new `[universal]`-tagged entries since prior cadence (via `query-records.js --type lesson --since <prior-cadence-date>` across configured roots, or `git log state/lessons/` per root).
3. **Structural-enforcement verification** (for each pending lesson naming a tripwire, wiki, or script artifact): check whether a completion entry citing the artifact exists since the lesson's capture date:
   ```bash
   _cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
   _cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
   _cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
   _cc_trusted=0
   case "$_cc_root" in
     "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
   esac
   [ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
   case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
   [ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
   [ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
   [ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
   "$_cc_root/bin/query-records.sh" --type completion --where "title~<tripwire-name>" --since "<lesson-date>"
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
- U strip-local applied (central mode only): <total> entries removed across N sibling repos
    <per-repo breakdown: <shortname>: <count> stripped, <count> skipped-on-drift>
    <list skipped: id — reason (pull-not-ff / content-no-match / multi-match / dirty-tree)>
    If skipped > 0: surface to PM — "Re-run `/learn-lessons --mode central` targeting these
    ids after the affected sibling's concurrent work settles. Age-sweep will NOT catch them
    in the current window (just-promoted entries are inside the cutoff date)."
- V undated_universal_remaining: <count> across N repos
    <per-repo breakdown for repos with >0>
```

**Fail-close on undated leak.** If `undated_universal_remaining > 0`, the run MUST NOT write the `COMPLETE` sentinel — surface the per-repo breakdown to the PM via the existing Phase 5 § "Central mode — PM gate" channel (the same gate that handles deferred records today) and stop. The undated-pass is mandatory; a non-zero remainder is a SKILL failure. `undated_universal_remaining` is the count of undated `[universal]` records that have neither been **applied** this run, **deferred** to the improvement queue, nor **rejected** — records under PM disposition (a/b/c) decrement the counter (a fully-deferred batch does NOT spuriously block COMPLETE). PM disposition follows the established central-mode triad: (a) apply now (route the undated batch in-run), (b) defer to improvement queue with PM-recorded reason, (c) reject. Only after every undated `[universal]` record has a (a)/(b)/(c) decision may COMPLETE land. This deliberately re-uses the existing parameter surface rather than introducing a `--allow-undated-leak` flag — see Anti-Patterns § "Bespoke extra parameters" below: modes are the parameter surface; the PM gate is the escape hatch. The sentinel is the contract Phase 4.5 reads to pick its cutoff (this file § Phase 4.5 "Cutoff is event-based, not age-based") — writing it on a leaky run silently certifies promotion completion for entries that were never routed.

**Other COMPLETE-sentinel consumers:** `bin/central-run-due.sh` (Phase 7 volume-trigger nudge at `/workday-start` Step 1.75) reads the sentinel to compute its cutoff. The fail-close strengthens sentinel semantics monotonically — sentinel presence now also implies "undated `[universal]` records were dispositioned" — so the central-run-due cutoff becomes more reliable. No consumer-side change needed.

The recurrence list is the pressure signal. PM acts or defers — no automatic block.
The `doe_escalation` and downgrade lists are inputs to the DoE's separate doctrine-edit
review pass; they are not actionable in the current run beyond surfacing.

**Central mode — write the completion sentinel.** On successful completion of a central run,
`touch ~/.claude/tasks/learn-lessons-YYYY-MM-DD/COMPLETE`. This is the signal Phase 4.5's local-mode
age-sweep reads to pick its cutoff: a run dir WITHOUT `COMPLETE` is in-progress or aborted and must
never become a sweep cutoff (it never promoted its entries). Write it last, after all applies/commits
land — it certifies "every universal up to this date had its promotion opportunity."

**Forbidden report shapes.** The end-of-run report MUST NOT include defer-chain language ("N candidates for next pass", "run /learn-lessons later to action these", "scope limited to this pass"). Records belong in one of three buckets: (a) applied this run, (b) PM-surfaced with a decision request, (c) mode escalated. Any record that fits none is a routing error — fix the routing, not the report.

**Local-mode exhaustivity goal (non-universal entries too).** The goal of a local-mode run is to drain `state/lessons/` of every entry, not only `[universal]`-tagged ones. Every non-`[universal]` entry should exit via one of: (a) `wiki-append` to a project wiki, (b) `improvement-queue` append, (c) `discard` to `archive/lessons-archived/YYYY-MM.md` with rationale, or (d) `retag-local` if mis-tagged. The three-bucket exhaustivity rule applies to every entry — "the universals are handled, we're done" is the doctrine violation this clause closes.

The goal is aspirational because the queue can exceed what fits in one context window. When it does, the carryover is legitimate IFF it is **explicitly enumerated** in the end-of-run report with the reason: `context-window-bound: N entries remain — recommend follow-up /learn-lessons run`, alongside any `[universal]` strip-local residue from a concurrent central run. A silent residue (entries left without enumeration or reason) is the failure mode; an enumerated residue with a follow-up signal is acceptable triage. The Phase 8 report should enumerate each remaining non-universal entry with its disposition (applied / queued / discarded / retagged / skipped-with-reason / carryover-context-bound); a bare entry-count line is insufficient — the disposition list is the audit trail.

*Empirical case (2026-06-14, project-rag):* a local-mode run terminated reporting "no additional work needed" after a peer central run's `[universal]` strip, while ~26 project-specific entries (registry/gate-test coupling, NDCG scorer-bug discipline, fusion-weight bugs, sidecar-restart ordering, …) sat un-routed. The skill's abstract three-bucket rule covered this in principle; the absent explicit local-mode floor let the residue pass.

## Anti-Patterns

- **Auto-applying central promotions.** PM gates every apply in central mode.
- **Generalizing beyond `state/lessons/`.** Targeted skill. Future generic doc-promotion is separate.
- **Bespoke extra parameters.** Modes are the parameter surface; resist additional flags.
- **Auto-emitting spinoff handoffs.** Section D of the review doc is advisory only.
- **Stripping local before central commit SHA exists.** Phase 5 apply order is load-bearing.
- **Deferring strip-local from the central run to the sibling's next local-mode age-sweep.** The age-sweep is the backstop, not the primary mechanism. Every day of deferral grows the lessons queue (200–350 KB across `state/lessons/` in roughly a month) for the consumers that DO enumerate it in full: `/learn-lessons`, the central strip-pass, and `/workstream-start`. Central promotes AND strips-just-promoted, in the same run.
- **`git add -A` for strips.** Always explicit pathspec; concurrent-EM safety.
- **True-deleting discards.** All discards go to archive first; never irrecoverable from Phase 4.
- **Conflating improvement queue with `state/lessons/`.** `state/lessons/` is the capture queue; `learn-lessons` is the periodic process that classifies and routes.
- **Same-session capture-and-validate-as-resolved (or as-universal).** Central-mode runs that capture AND validate a lesson in the same pass create unverified-resolution noise or self-confirming-universal loops — the session that surfaced the pattern is the same session asserting its generality. Capture this run; validate in a later run once the pattern has survived a context boundary and recurred in a different context.
- **Default-routing to CLAUDE.md or a CLAUDE.md pointer.** Wikis are the default; `doctrine-edit` and `memory-pointer` are DoE-only and must clear the four-check gate (§ Routing Bias). "It's small, it'll fit" is not a justification — the prior-art-checker surfaces wiki-only lessons when relevant, so a CLAUDE.md pointer per lesson is the same pollution as inlining the rule.
- **Worker proposing `change_kind: doctrine-edit` or `change_kind: memory-pointer`.** Routing error — downgrade to `wiki-*` + `doe_escalation: true` before the record reaches the PM gate. The wiki edit is the load-bearing change; any CLAUDE.md edit is a separate downstream DoE-authored plan.
- **Archiving a lesson because its proposed target violates policy.** Substance and proposed target are independent. A `proposed target: CLAUDE.md` that fails the gate is a routing problem, not a substance problem — reroute to the right wiki / agent prompt / hook / script. `discard` only when the substance itself is ephemeral, already covered, or wrong.
- **Defer-chaining wiki promotions or end-of-run "candidates for next pass."** A run that classifies records with named wiki destinations and defers them is the pattern this skill exists to prevent. Wiki-append/wiki-new with named destinations apply IN THIS RUN (Phase 5 auto-apply contract). Any Phase 8 report line naming records "to be folded next run" is a doctrine violation — apply them, surface them to the PM with a decision request, or escalate the mode. The three buckets are exhaustive; "informational candidates for later" is not a fourth.
- **Declaring "no additional work needed" while project-specific entries remain.** The local-mode three-bucket exhaustivity rule (applied / PM-surfaced / mode-escalated) applies to every entry, not only to `[universal]`-tagged ones. A run that proudly reports queue-empty after a peer's `[universal]` strip but leaves project-specific entries un-routed is the doctrine violation this skill exists to prevent. The `[universal]` subset is the central run's scope by design; the project-specific tail is the local run's responsibility. Same boundless-accumulation hazard the cruft-sweep cadence floor (Layer 1) prevents for filesystem hygiene — same shape, different surface.

## Related

- `coordinator/CLAUDE.md` "Self-Improvement Loop" — references this skill for cadence + capture.
- `docs/wiki/consumer-self-evolution-loop.md` — for a **downstream consumer** (non-meta-repo install), local mode is a complete self-evolution loop against their own `$GIT_ROOT/state/` (never `~/.claude`); DoE's central queue is fleet-private and does not ship to them (accepted, by-design dogfooding-blindness).
- Central improvement queue (`$(coordinator_state_root --central)/coordinator-improvement-queue.md`, example-orchestration-hub-resident — see `docs/wiki/state-placement-law.md`) — central queue; destination for deferred items.
- Central config (`$(coordinator_state_root --central)/learn-lessons-config.md`) — optional supplemental-roots sentinel (empty by default) + `central_volume_threshold` knob. Discovery roots are registry-derived via `bin/learn-lessons-roots.sh`, NOT written here.
- `snippets/text-only-recovery-preamble.md` — synced snippet consumed in Phase 2 scout dispatches.
- `archive/lessons-archived/YYYY-MM.md` — per-repo discard + age-sweep archive; append-only, per-month.
- `bin/age-sweep-lessons.py` — Phase 4.5 mechanism; reuses `extract-lessons.py`'s parser; archives aged `[universal]` entries to bound `state/lessons/`. Requires an explicit cutoff (`--before <last-central-run>`).
- `central-run-due.sh` — Phase 7 volume trigger; counts `[universal]` accrued since the last `COMPLETE` central run across the configured roots and nudges a central run at `central_volume_threshold`. Surfaced by `/workday-start` Step 1.75.
