# Cruft-sweep cadence

<!-- distilled: run 2026-07-19-synth; sources: 2026-06-09-distill-cruft-sweep.md, archive/specs/2026-06/2026-06-15-workstream-complete-self-clean.md -->

<!-- Spec backlink: archive/specs/2026-06/2026-06-09-distill-cruft-sweep.md § C5 -->

Filesystem hygiene is a distinct lifecycle from knowledge extraction (`/distill`) and artifact pruning (`/update-docs` Phase 8b). `/distill` extracts actionable signal from completed work; Phase 8b prunes stale plan/report artifacts from `tasks/`; neither touches the three classes of filesystem residue that accumulate silently between sessions — harness state under `~/.claude/`, in-repo scratch dirs created by agents, and parent-folder orphans at `X:\` / `E:\dev\`. <!-- foreign-path-ok: naming the Class 3 detection shape this system targets --> The cruft-sweep system handles these with a **three-layer design**: a non-agentic script (Layer 1) that runs on a scheduler and covers mechanical age + name + fingerprint cases without requiring PM attention, an on-demand skill (Layer 2) that handles judgment-needed cases and the broader registry-diff scan, and a front-line EM-judgment step (Layer 3) at `/workstream-complete` that disposes of session-authored scratch with fresh context, before Layers 1 and 2 ever see it.

## Three classes of cruft

**Class 1 — Harness state.** Files under `~/.claude/projects/<repo>/<uuid>/`, `*.jsonl` transcripts, and `~/.claude/file-history/<uuid>/`. These accumulate boundlessly — each Claude Code session writes a UUID directory; a week of fan-out dispatches can produce hundreds. The 14-day default retention is the non-negotiable floor; the only gate is a pre-flight check that skips any UUID cited as `predecessor:` in an active handoff.

**Class 2 — In-repo scratch.** Agent-created directories with cruft-name anchors inside a repo tree: `tmp-cc/`, `nonexistent/`, `fake/`, single-character names `[a-z]/`, and chain'd identical-segment paths like `z/z/z/`. These are name-anchored (identity is in the name, not the content) and age-gated (> 7 days mtime). The gate also requires the path to be git-untracked and not inside a `.git/` boundary. Confirm-needed names (`tmp/`, `scratch/`, `output/`) are context-dependent — Layer 1 reports them; Layer 2 confirms.

**Class 3 — Parent-folder orphans.** Directories at `X:\` and `E:\dev\` <!-- foreign-path-ok: naming the Class 3 detection shape --> that exist because an agent ran `mkdir -p nonexistent/...` from inside a repo, escaping the repo tree. These require a **conjoint gate**: name must match the literal cruft list AND contents must fingerprint as sonnet defaults (`vector/store/chroma.sqlite3`, `project/Saved/ProjectRag/vector_store/chroma.sqlite3`, lone `mcp_queries.jsonl`). Broader registry-diff (detecting dirs that are neither sibling repos nor known working areas) is a Layer 2 judgment operation — Layer 1 touches only the fingerprint-confirmed cases.

## Three-layer design

**Layer 1 — claude-klabauter `coordinator/bin/cruft-sweep` (non-negotiable floor).** A non-agentic naked-Python script (bash-to-Python port, 2026-07 de-bash campaign) that runs on mechanical criteria: age, name, and content fingerprint. It is cron-safe, pure-stdlib cross-platform portable (Windows/.cmd launcher, macOS, Linux), lock-protected against concurrent invocations, and idempotent. Two install legs ship with the coordinator: `/workday-start` Step 1.11 runs `--dry-run --quiet` to surface the morning advisory, and `/workday-complete` Step 1.5 runs `--apply --quiet` to sweep the mechanical floor at end-of-day. Operators may additionally schedule `--apply --quiet` on a higher threshold via cron / Task Scheduler for days when Claude Code is not opened, but that is optional layering on top of the in-session install. Layer 1 is the backstop that ensures boundless accumulation cannot occur even when the PM does not invoke the skill.

**Layer 2 — `/cruft-sweep` skill (on-demand judgment layer).** A skill that dispatches a read-only Sonnet scout for confirm-needed items (Class 2 `tmp/`, `scratch/`, `output/` — context-dependent) and for the broader Class 3 registry-diff scan against `the sibling-repo registry (`machine-local get repos.<key>`)`. Findings are surfaced via batched `AskUserQuestion` in offer-shape: each finding leads with the reclaim opportunity (_"Reclaim 240 MB by pruning `X:\nonexistent\` (sonnet-fingerprint vector store, mtime 8d)? [y/N/inspect]"_) — not with a violation warning. <!-- foreign-path-ok: illustrative offer-shape banner text, not a live path --> Layer 2 reads the Layer 1 sweep log to surface cadence context; it does NOT re-walk the tree — it consumes the `--dry-run --json` JSONL wire output from Layer 1.

<!-- src: plan15-035 -->
**Layer 1 → Layer 2 wire contract.** Each `--dry-run --json` invocation emits one JSONL row per candidate with the fields `{class, path, name, size_bytes, mtime, disposition, evidence}`, where `disposition ∈ {auto-prune, confirm-needed, skip}`. Layer 2 consumes this stream directly and dispatches its confirm-needed judgment pass only on rows where `disposition == confirm-needed` — it never re-derives class/name/fingerprint membership itself. This keeps the two layers from drifting on what counts as a candidate: Layer 1 owns candidate identification, Layer 2 owns judgment on the subset Layer 1 flags as ambiguous.

**Layer 3 — EM self-clean at `/workstream-complete` (front-line judgment, fresh context).** The EM authored the session's transient artifacts and has the freshest context on what's trash vs. potentially-useful. `/workstream-complete`'s `scratch-disposition-per-file` judgment point + `d-deletion-blocks` directive make Layer 3 a **hard step**: enumerate session-authored scratch via the operational predicate (mtime since session-start + provenance check + Step 3.0 case-(b) exclusion), `git rm` by default, name deletions and justify-keeps in the session commit body (validated by `bin/check-workstream-complete-deletion-blocks.py`) so `git log -- <path>` is the recovery substrate. Layer 3 is judgment-bound, scoped to THIS session, and runs FIRST in lifecycle order — it operates on residue before Layer 1 or Layer 2 ever see it. It does NOT walk the tree, does NOT touch unattributable files (Step 3.0 owns case (c)), and does NOT delete keep-list paths (plan files under `docs/plans/`, `archive/completed/**`, `state/**` allowlist, archived handoffs, `cross-repo/inbox|archive/**`).

<!-- src: plan18-005, plan18-006 -->
**Session-authored predicate (precise form).** A candidate qualifies as "session-authored" only if BOTH hold: (1) the file appears in `git status` (tracked-modified or untracked), AND (2) either it was created this session (confirmed via `git log` — first commit touching the path postdates the session start) OR it is untracked with `mtime > SESSION_START_TIME` AND is not owned by a concurrent session (concurrent-session ownership is checked before disposition — a file another live session wrote in the same window is never Layer-3-deleted by this session). This predicate is what "mtime since session-start + provenance check" cashes out to operationally.

**Keep-list (full).** `docs/plans/*`, `tasks/<feature>/todo.md`, `archive/completed/**`, `state/**`, `archive/handoffs/**`, `cross-repo/inbox|archive/**`, and any path currently owned by a concurrent session. This is the complete negative-spec for Layer 3 — a candidate matching any of these is never deleted regardless of mtime or provenance.

The ordinal reads bottom-up: Layer 1 is the mechanical floor (must hold even when no session ever completes), Layer 2 is the on-demand judgment skill (PM-invoked sweeps), Layer 3 is fresh-context judgment at `/workstream-complete` — the work-boxed session terminator (see `ceremony-calibration.md` § Session terminators; highest altitude because the EM that just shipped the work has the best disposition). Layer 3 runs first in lifecycle order; Layer 1 is the mechanical backstop for what Layer 3 missed or what no session ever owned.

**Non-substitution across layers.** Layer 3 is NOT substitutable by Layer 1 (mechanical name + age can't replace fresh judgment on session-authored scratch). Layer 1 is NOT substitutable by Layer 3 (EM judgment can't backstop accumulation across never-completed sessions; many sessions crash or never reach `/workstream-complete`). Layer 2 is NOT substitutable by Layer 1 (registry-diff judgment is on-demand, not mechanical). `/distill` and `/update-docs` are NOT a substitute for any layer — they extract knowledge and index canonical artifacts; cleanup is for **concision and clarity, not cleanliness**.

## Class 4 — empty top-level directories

`--class empty-dirs` targets depth-1 children of the repo root containing zero files anywhere in
the subtree, older than a 24h mtime floor, not git-ignored, not hard-excluded/whitelisted/
dot-prefixed. Detection is structural, not name-based — this is the gap the other three classes
cannot see: git is blind to a file-free directory tree (`git status --untracked-files=all` is
silent, `.gitignore` never gets a say). Fails closed: no git work tree, no git binary, or an
unreadable nested subtree all mean skip-and-delete-nothing. Reclaim bytes are always 0 by
construction — an empty subtree has nothing to reclaim; the item count is the whole signal, never
present this class as an MB opportunity.

## Extended disposition set

Beyond `{auto-prune, confirm-needed, skip}` (§ wire contract above), two more dispositions appear
in `--dry-run --json` output:

- **`duplicate-of-scratch`** — Phase B (scratch, name-anchored, floor `max(scratch_age_days,
  24h)`) and Phase E (empty-dirs, structural, flat 24h floor) can match the same path since their
  floors are not nested. Rather than silently under-report a Phase-E-exclusive catch (age between
  24h and `scratch_age_days`), Phase E relabels: when the name is also in Phase B's vocabulary,
  the `empty-dirs` record carries `duplicate-of-scratch` and the authoritative `auto-prune` record
  lives on the `scratch` record for the same path. Never a finding, never counted — the engine
  already guarantees one record per physical directory; summing `disposition == auto-prune` is
  double-count-free by construction.
- **`prune-failed`** — an apply-mode delete that did not confirm removal (permission denied,
  wedged path). Not counted as reclaimed. The difference between *attempted* and *actually
  removed*.

## Registry-diff scout (Class 3 broader scan)

For candidates where Layer 1 skipped a name match for lack of a fingerprint match, Layer 2
dispatches a read-only `Explore` scout to enumerate top-level children at this machine's resolved
dev roots (distinct parent dirs of the non-empty `repos.*` `machine-local` entries — registry-
derived, never a hardcoded platform path) and cross-reference against the sibling-repo registry.
No dev root present on a given machine means the scan is skipped entirely, logged, not treated as
a failure. The scout is read-only and returns inline JSON; no write-capable subagent type is ever
appropriate here.

## Offer-shape confirmation

Layer 2's `AskUserQuestion` batch leads with the reclaim value, never a violation/warning frame:
_"Reclaim N MB by pruning `<path>` (`<evidence>`, mtime `<mtime>`)? [y/N/inspect]"_. Batch related
items from the same class into one question where practical (e.g. all `tmp/` dirs in one repo).
Auto-pruned items are never asked about — informational only.

## Guard-rail rationale

Four hardcoded refusals hold regardless of what the Layer 1 JSONL says, because each is a
highest-blast-radius case:

- A `.git/`-boundary path retains full history inside `.git/`; pruning is irreversible.
- The parent-folder scan never expands past this machine's resolved dev roots; speculative root
  discovery is unpredictable blast radius, not this skill's remit.
- Git-untracked is necessary but not sufficient for cruft — a new unregistered repo, a
  this-session working area, or intentionally-unversioned content all look untracked too.
- A session UUID cited as `predecessor:` in any active handoff is never auto-pruned; the pre-flight
  block-list check that covers Layer 1 must be honored by any confirm-needed item this skill
  surfaces too.

## Name list (Layer 1 auto-prune)

| Class | Auto-prune names | Age gate | Extra conditions |
|---|---|---|---|
| Class 1 (harness) | `<uuid>/`, `<uuid>.jsonl`, `file-history/<uuid>/` | > 14d (configurable via `--days`) | Not cited as `predecessor:` in an active handoff |
| Class 2 (in-repo scratch) | `tmp-cc/`, `nonexistent/`, `fake/`, single-char `[a-z]/`, chain'd identical-segment paths (`z/z/z/`) | > 7d | git-untracked; not inside `.git/`; not in negative-spec list |
| Class 2 (confirm-needed) | `tmp/`, `scratch/`, `output/` | any | Report-only from Layer 1; Layer 2 handles confirm |
| Class 3 (parent-folder) | `nonexistent/`, `tmp/`, `tmp-cc/`, `fake/`, `null/`, `undefined/`, `untitled*/`, single-char dirs | any | Conjoint gate: name match AND fingerprint match required |

**Negative-spec (Class 2 skip list):** `archive/`, `tasks/`, `state/`, `docs/`, `node_modules/`, `.venv/`, `__pycache__/`, `_*`-prefixed dirs, `*.bak*` / `*-bak-*` suffixed dirs.

## Content-fingerprint patterns

Layer 1 uses these fingerprints as the conjoint Class 3 gate — a name match alone is insufficient:

- `vector/store/chroma.sqlite3` — sonnet vector store (relative path from candidate dir root)
- `project/Saved/ProjectRag/vector_store/chroma.sqlite3` — project-rag UE vector store (relative path from candidate dir root)
- lone `mcp_queries.jsonl` at candidate dir root — MCP query log with no other files present

If none of these fingerprints match, Layer 1 skips the candidate regardless of name. Layer 2 handles the broader case.

## Hard-exclude (never swept)

These surfaces are excluded at all layers, regardless of name or fingerprint match:

- Dirs whose path contains a `state/` segment
- `docs/` and `docs/wiki/` trees
- `docs/research/*-workdir/` — explicit (transitively covered by the `docs/` rule above; named here as belt-and-suspenders so future contributors don't introduce a sweep that re-enters the kill-zone via a refactor of the `docs/` rule). See RD-1 in `docs/plans/2026-06-14-deep-research-workdir-out-of-killzone.md`.
- `archive/` trees
- Any directory containing `CLAUDE.md` at its root (the sibling `CLAUDE.local.md` file class this
  exclusion once also named has since been retired)
- `$RECYCLE.BIN`, `System Volume Information`
- `.github-private`
- Any path in the machine-local whitelist key `cruft_sweep.parent_whitelist`

This mirrors the `cleanup-sweep-hazards.md` doctrine: load-bearing substrate (`state/`, `docs/wiki/`, `archive/`) is never swept regardless of what name-matching or fingerprint-matching returns.

## Mtime floor (mechanical liveness gate)

<!-- Review: Slice B reviewer F6 — clarified dual-protection structure; deep-research workdir is protected by hard-exclude (above), NOT by mtime gating -->
Sweep tooling that operates inside `tasks/scratch/` MUST check candidate mtime and skip if `now - mtime < 86400` (24h). This mirrors the established `handoff-archival.md` § 'Mechanical mtime veto' neighbor pattern — same mechanism class, same wiki neighborhood, same 24h threshold. Rationale: in-flight scratch can remain load-bearing across handoff/pickup gaps and EM-step-away windows; the 24h floor catches the slow-tail failure mode (an observed incident: 56 min from specialist convergence to deletion discovery, on a survivable run; multi-session runs can exceed hours).

**Dual-protection structure — deep-research workdir is NOT in this mtime gate's blast radius.** Deep-research in-flight working directories at `docs/research/*-workdir/` are protected by the **hard-exclude rule** in § Hard-exclude above — they are excluded at all layers regardless of name or age. The mtime floor applies to belt-and-suspenders liveness protection for any current or future skill that writes scratch under `tasks/scratch/`. A reader should not conclude that deep-research is protected by mtime gating alone; it is excluded structurally before any age check runs.

## Cadence

**Two-tier staleness thresholds** — the advisory threshold differs from the weekly verification threshold by design:

<!-- Review: Slice C reviewer F1 — two-tier threshold documented; asymmetry rationale explicit -->
| Surface | Threshold | Rationale |
|---|---|---|
| `/workday-start` Step 1.11 advisory | reclaimable > 1 GB OR mtime-staleness > 14d | daily ceremony catches fast drift |
| `/workday-complete` Step 1.5 apply | unconditional (every workday wrap) | mechanical floor — no threshold; the floor IS the cadence |
| `/workweek-complete` Step 4 verification | reclaimable > 2 GB OR mtime-staleness > 21d | weekly horizon — coarser by design |

**`/workday-start` Step 1.11** — advisory threshold: surface one-line `Cruft sweep candidates: <N reclaimable>, last sweep <YYYY-MM-DD>` when reclaimable > 1 GB OR staleness > 14d. PM-actioned. The dry-run output is non-blocking; the workday continues.

**`/workday-complete` Step 1.5** — runs `cruft-sweep --class all --apply --quiet` unconditionally after Step 1 validate. Non-blocking (a sweep error never halts the workday wrap). This is the in-session install path that closes the doctrine-vs-impl gap the morning advisory alone leaves open — between morning surface and evening sweep, the mechanical floor runs every workday without PM involvement. An out-of-session scheduler (cron / Windows Task Scheduler) on a higher reclaimable threshold is the recommended layering for machines where Claude Code is not opened every day.

**`/workweek-complete` Step 4** — includes a verification line: "Cruft-sweep last run: `<YYYY-MM-DD>`; reclaimable: `<N MB>`". Read from sweep log; no write.

**Concurrency guard** — Layer 1 acquires an exclusive lock via `mkdir` at `~/.claude/state/cruft-sweep.lock.d/` before any sweep pass. `mkdir` is atomic on both POSIX and Windows filesystems, so this is portable lock-acquisition without a third-party dependency. On contention (lock dir already exists), the invocation exits 0 silently — a concurrent sweep is not an error condition, it's expected when `/workday-start` and `/workday-complete` legs or a manual `/cruft-sweep` overlap. Sweep-log appends happen inside the lock, which prevents interleaved writes from producing a torn row in `cruft-sweep-log.md`.

<!-- src: plan15-034 -->

**Sweep log** — Layer 1 appends to `cruft-sweep-log.md` on every `--apply` run (timestamp + class + reclaimed bytes + counts); this file lives in claude-klabauter at `$(python3 <claude-klabauter>/coordinator/lib/coordinator-state-root.py --central)/cruft-sweep-log.md` (see `state-placement-law.md`). Never appended on `--dry-run`. The log lives in `state/`, not `tasks/` — it is load-bearing cadence input read by Layer 2 and by the `/workday-start` advisory; `tasks/` is aggressively swept by `/distill` and `/update-docs` per the tasks-state-split rule.

**Sweep log row format** — each row written by claude-klabauter `coordinator/bin/cruft-sweep --apply` is pipe-delimited markdown table syntax:

<!-- Review: Slice C reviewer F4 — actual format confirmed by reading cruft-sweep _emit_jsonl/_append_log_row -->
```
| 2026-06-09T11:00:00Z | harness | <N> bytes | <M> items |
```

Columns (1-indexed, pipe-delimited): `| timestamp | class | bytes | items |`. To parse the timestamp from the log, use `awk -F'|' '{gsub(/ /, "", $2); print $2}'` — NOT `awk '{print $1}'` (which returns the leading `|` literal, not the timestamp). This is the **canonical staleness parse method** used by both `/workday-start` Step 1.11 and `/workweek-complete` Step 4.

**`--quiet` output contract** — when invoked with `--quiet`, the script suppresses human-readable per-class banners. The grand-total summary is emitted to stderr:

<!-- Review: Slice C reviewer F7 — --quiet contract documented per script behavior; stderr routing per Slice A F13 fix -->
```
[cruft-sweep] grand total: ~N MB reclaimable across all classes
```

When `--dry-run --quiet` is combined, this one stderr line is the only output. This is the signal read by `/workday-start` Step 1.11 for the `> 1 GB` threshold check.

## Empirical baseline

A one-off sweep measured the scale of the problem:

| Surface | Before | After | Recovered |
|---|---|---|---|
| `~/.claude/projects/` total | 5.2 GB | — | — |
| `~/.claude/file-history/` | 620 MB | — | — |
| Total (all classes) | 6.0 GB | 3.4 GB | 2.6 GB |

The 2.6 GB recovered came almost entirely from the 14-day harness prune (Class 1). Class 3 fixtures confirmed in the sweep:

- `X:\nonexistent\` — sonnet vector-store fingerprint (`vector/store/chroma.sqlite3`), chain'd `z/z/z/` subdirectory <!-- foreign-path-ok: historical fixture from a real Class 3 sweep -->
- `X:\rename-to-unreal-daemon.md` — orphan markdown at parent altitude (confirm-needed; not auto-pruned) <!-- foreign-path-ok: historical fixture from a real Class 3 sweep -->
- `X:\working-memory.md` — same shape as above <!-- foreign-path-ok: historical fixture from a real Class 3 sweep -->

The orphan markdown cases illustrate why Layer 2 exists: they do not match the fingerprint gate, so Layer 1 skips them. Layer 2's registry-diff surfaces them as candidates for PM-confirmed deletion.

## Why Layer 1 is non-negotiable

Without a non-agentic backstop, a single heavy fan-out session can write dozens of UUID harness directories totalling hundreds of megabytes. The harness's own 30-day rotation window means stale sessions accumulate across a full month before the harness touches them; at normal coordinator usage rates, weeks pass with no cleanup. Layer 2 (the skill) requires an explicit PM invocation — if the PM does not invoke `/cruft-sweep`, accumulation continues unchecked. Layer 1 runs in-session every workday: `/workday-start` Step 1.11 surfaces the dry-run advisory, and `/workday-complete` Step 1.5 runs the `--apply` sweep. Together the two legs are the install path — the PM does not need to be in the loop, and no out-of-session scheduler is required for the floor to hold. The empirical baseline (2.6 GB reclaimed on the first run after months of accumulated harness state) demonstrates what "boundless accumulation" looks like in practice. Layer 1 is the mechanism that prevents that baseline from being the norm.

---

*See also:*
- `/distill` — knowledge extraction, distinct lifecycle (no filesystem prune)
- `/update-docs` Phase 8b — artifact pruning in `tasks/`, distinct blast radius
- `cleanup-sweep-hazards.md` — parent doctrine on never sweeping `state/`, `docs/wiki/`, `archive/`

## Harness state retention windows

Claude Code retains three accumulating substrates outside the repo working tree:

- session transcripts at `~/.claude/projects/<repo>/<uuid>.jsonl`,
- sub-agent tool-result captures at
  `~/.claude/projects/<repo>/<uuid>/subagents/` and `tool-results/`,
- file-state caches at `~/.claude/file-history/<uuid>/`.

Baseline measurements (`2026-06-02`, Machine-a): **5.2 GB in `projects/`** (2.1 GB
in `X--project-rag/` alone, with single session dirs at 262 MB); **620 MB in
`file-history/`** (~1800 session dirs from `2026-05-03` onward). The first cleanup
recovered 6.2 GB.

**Default retention: 14 days.** PM-configurable via
`~/.claude/machine-local/registry.local.toml` key
`cruft_sweep.harness_retention_days`.

**Pre-flight guard:** skip any session-dir UUID still referenced in an active
handoff `predecessor:` field — grep `tasks/handoffs/*.md` and
`state/handoffs/*.md` before deletion. Active session UUIDs are
checkpoint anchors; sweeping them breaks lineage queries.

**Sonnet-scratch name patterns (Layer 1 auto-prune candidates).** Default
agent-created cruft names: `tmp/`, `tmp-cc/`, `nonexistent/`, `fake/`,
`scratch/`, `test-output/`, `untitled*/`, `output/`, single-char `[a-z]/`,
chain'd identical `z/z/z/`. Also parent-folder orphans at `X:\` / `E:\dev\` <!-- foreign-path-ok: naming the Class 3 detection shape -->
with fingerprints like `vector/store/chroma.sqlite3` and lone
`mcp_queries.jsonl`. **Auto-prune gate is class-specific — see § Name list
(Layer 1 auto-prune) above for the authoritative table; this paragraph does
not restate it.** In brief: Class 2 in-repo scratch auto-prunes on
strict-name-match AND age > 7 d AND git-untracked; Class 3 parent-folder
orphans auto-prune on the **conjoint** name-match AND content-fingerprint
gate (§ Content-fingerprint patterns) with no age requirement — fingerprint
match is mandatory for Class 3 and is never dropped in favor of an age
threshold. **Confirm before delete:** `tmp/`, `scratch/`,
`output/` (sometimes legitimate), Class 2 candidates < 7 d old, anything
containing `.git/`. **Always skip:** `.gitignore`-honored paths with mtime <
24 h, `archive/`, `tasks/`, `docs/`, `node_modules/`, `.venv/`,
`__pycache__/`, anything inside a `.git/` boundary.
