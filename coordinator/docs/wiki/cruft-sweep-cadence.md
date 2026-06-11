# Cruft-sweep cadence

<!-- Spec backlink: docs/plans/2026-06-09-distill-cruft-sweep.md § C5 -->

Filesystem hygiene is a distinct lifecycle from knowledge extraction (`/distill`) and artifact pruning (`/update-docs` Phase 8b). `/distill` extracts actionable signal from completed work; Phase 8b prunes stale plan/report artifacts from `tasks/`; neither touches the three classes of filesystem residue that accumulate silently between sessions — harness state under `~/.claude/`, in-repo scratch dirs created by agents, and parent-folder orphans at `X:\` / `E:\dev\`. The cruft-sweep system handles these with a two-layer design: a non-agentic script (Layer 1) that runs on a scheduler and covers mechanical age + name + fingerprint cases without requiring PM attention, and an on-demand skill (Layer 2) that handles judgment-needed cases and the broader registry-diff scan.

## Three classes of cruft

**Class 1 — Harness state.** Files under `~/.claude/projects/<repo>/<uuid>/`, `*.jsonl` transcripts, and `~/.claude/file-history/<uuid>/`. These accumulate boundlessly — each Claude Code session writes a UUID directory; a week of fan-out dispatches can produce hundreds. The 14-day default retention is the non-negotiable floor; the only gate is a pre-flight check that skips any UUID cited as `predecessor:` in an active handoff.

**Class 2 — In-repo scratch.** Agent-created directories with cruft-name anchors inside a repo tree: `tmp-cc/`, `nonexistent/`, `fake/`, single-character names `[a-z]/`, and chain'd identical-segment paths like `z/z/z/`. These are name-anchored (identity is in the name, not the content) and age-gated (> 7 days mtime). The gate also requires the path to be git-untracked and not inside a `.git/` boundary. Confirm-needed names (`tmp/`, `scratch/`, `output/`) are context-dependent — Layer 1 reports them; Layer 2 confirms.

**Class 3 — Parent-folder orphans.** Directories at `X:\` and `E:\dev\` that exist because an agent ran `mkdir -p nonexistent/...` from inside a repo, escaping the repo tree. These require a **conjoint gate**: name must match the literal cruft list AND contents must fingerprint as sonnet defaults (`vector/store/chroma.sqlite3`, `project/Saved/ProjectRag/vector_store/chroma.sqlite3`, lone `mcp_queries.jsonl`). Broader registry-diff (detecting dirs that are neither sibling repos nor known working areas) is a Layer 2 judgment operation — Layer 1 touches only the fingerprint-confirmed cases.

## Two-layer design

**Layer 1 — `bin/cruft-sweep.sh` (non-negotiable floor).** A non-agentic bash script that runs on mechanical criteria: age, name, and content fingerprint. It is cron-safe, macOS bash 3.2 + BSD coreutils portable, lock-protected against concurrent invocations, and idempotent. It runs from `/workday-start` Step 1.11 in advisory mode (dry-run, surfaces a one-line summary) and can be scheduled at `--apply --quiet` on a separate threshold without PM involvement. Layer 1 is the backstop that ensures boundless accumulation cannot occur even when the PM does not invoke the skill.

**Layer 2 — `/cruft-sweep` skill (on-demand judgment layer).** A skill that dispatches a read-only Sonnet scout for confirm-needed items (Class 2 `tmp/`, `scratch/`, `output/` — context-dependent) and for the broader Class 3 registry-diff scan against `~/.claude/CLAUDE.local.md § Sibling repos`. Findings are surfaced via batched `AskUserQuestion` in offer-shape: each finding leads with the reclaim opportunity (_"Reclaim 240 MB by pruning `X:\nonexistent\` (sonnet-fingerprint vector store, mtime 8d)? [y/N/inspect]"_) — not with a violation warning. Layer 2 reads the Layer 1 sweep log to surface cadence context; it does NOT re-walk the tree — it consumes the `--dry-run --json` JSONL wire output from Layer 1.

Layer 2 NEVER substitutes for Layer 1. The skill requires PM invocation; the script does not. Boundless accumulation under normal use demands the non-agentic backstop.

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
- `archive/` trees
- Any directory containing `CLAUDE.md` or `CLAUDE.local.md` at its root
- `$RECYCLE.BIN`, `System Volume Information`
- `.github-private`
- Any path in the machine-local whitelist key `cruft_sweep.parent_whitelist`

This mirrors the `cleanup-sweep-hazards.md` doctrine: load-bearing substrate (`state/`, `docs/wiki/`, `archive/`) is never swept regardless of what name-matching or fingerprint-matching returns.

## Cadence

**Two-tier staleness thresholds** — the advisory threshold differs from the weekly verification threshold by design:

<!-- Review: Slice C reviewer F1 — two-tier threshold documented; asymmetry rationale explicit -->
| Surface | Threshold | Rationale |
|---|---|---|
| `/workday-start` Step 1.11 advisory | reclaimable > 1 GB OR mtime-staleness > 14d | daily ceremony catches fast drift |
| `/workweek-complete` Step 4 verification | reclaimable > 2 GB OR mtime-staleness > 21d | weekly horizon — coarser by design |

**`/workday-start` Step 1.11** — advisory threshold: surface one-line `Cruft sweep candidates: <N reclaimable>, last sweep <YYYY-MM-DD>` when reclaimable > 1 GB OR staleness > 14d. PM-actioned. The dry-run output is non-blocking; the workday continues. Layer 1 can be separately configured to auto-apply on a higher reclaimable threshold via `--apply --quiet` on a scheduler.

**`/workweek-complete` Step 4** — includes a verification line: "Cruft-sweep last run: `<YYYY-MM-DD>`; reclaimable: `<N MB>`". Read from sweep log; no write.

**Sweep log** — Layer 1 appends to `~/.claude/state/cruft-sweep-log.md` on every `--apply` run (timestamp + class + reclaimed bytes + counts). Never appended on `--dry-run`. The log lives in `state/`, not `tasks/` — it is load-bearing cadence input read by Layer 2 and by the `/workday-start` advisory; `tasks/` is aggressively swept by `/distill` and `/update-docs` per the tasks-state-split rule.

**Sweep log row format** — each row written by `bin/cruft-sweep.sh --apply` is pipe-delimited markdown table syntax:

<!-- Review: Slice C reviewer F4 — actual format confirmed by reading bin/cruft-sweep.sh printf lines 552, 867, 1092 -->
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

The 2026-06-02 one-off sweep established the scale of the problem:

| Surface | Before | After | Recovered |
|---|---|---|---|
| `~/.claude/projects/` total | 5.2 GB | — | — |
| `~/.claude/file-history/` | 620 MB | — | — |
| Total (all classes) | 6.0 GB | 3.4 GB | 2.6 GB |

The 2.6 GB recovered came almost entirely from the 14-day harness prune (Class 1). Class 3 fixtures confirmed in the sweep:

- `X:\nonexistent\` — sonnet vector-store fingerprint (`vector/store/chroma.sqlite3`), chain'd `z/z/z/` subdirectory
- `X:\rename-to-unreal-daemon.md` — orphan markdown at parent altitude (confirm-needed; not auto-pruned)
- `X:\working-memory.md` — same shape as above

The orphan markdown cases illustrate why Layer 2 exists: they do not match the fingerprint gate, so Layer 1 skips them. Layer 2's registry-diff surfaces them as candidates for PM-confirmed deletion.

## Why Layer 1 is non-negotiable

Without a non-agentic backstop, a single heavy fan-out session can write dozens of UUID harness directories totalling hundreds of megabytes. The harness's own 30-day rotation window means stale sessions accumulate across a full month before the harness touches them; at normal coordinator usage rates, weeks pass with no cleanup. Layer 2 (the skill) requires an explicit PM invocation — if the PM does not invoke `/cruft-sweep`, accumulation continues unchecked. Layer 1 runs from `/workday-start` automatically and can be scheduled independently; the PM does not need to be in the loop every time. The empirical baseline (2.6 GB reclaimed on the first run after months of accumulated harness state) demonstrates what "boundless accumulation" looks like in practice. Layer 1 is the mechanism that prevents that baseline from being the norm.

---

*See also:*
- `/distill` — knowledge extraction, distinct lifecycle (no filesystem prune)
- `/update-docs` Phase 8b — artifact pruning in `tasks/`, distinct blast radius
- `cleanup-sweep-hazards.md` — parent doctrine on never sweeping `state/`, `docs/wiki/`, `archive/`
