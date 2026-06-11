---
name: cruft-sweep
description: Layer 2 cruft-sweep skill — dispatches read-only scout for confirm-needed scratch items and parent-folder registry-diff. Wraps bin/cruft-sweep.sh for filesystem hygiene.
allowed-tools: ["Read", "Bash", "Glob", "Grep", "Agent", "AskUserQuestion"]
argument-hint: "[--dry-run|--apply] [--class harness|scratch|orphans|all]"
---

# Cruft Sweep — Layer 2 Skill

Spec backlink: `docs/plans/2026-06-09-distill-cruft-sweep.md` § C3

Consume the JSONL wire output of `bin/cruft-sweep.sh` to surface `confirm-needed` findings and parent-folder orphans for PM review. Present reclaim opportunities in offer-shape — never violation framing. Apply only after explicit confirmation.

**Destructive-action prohibition:** This skill dispatches read-only scouts. The only write path is `bin/cruft-sweep.sh --apply` after explicit `AskUserQuestion` confirmation. Scouts MUST NOT modify files, commit, or push.

---

## Three classes of cruft

The Layer 1 script handles three distinct classes, each with its own auto-prune and confirm-needed thresholds:

- **Class 1 — Harness state in `~/.claude/`**
  Session UUID directories (`projects/<repo>/<uuid>/`), transcript `.jsonl` files, and `file-history/<uuid>/` directories older than the retention threshold (default 14 days). Auto-pruned by Layer 1 when outside the active-handoff UUID block-list.

- **Class 2 — In-repo scratch dirs**
  Name-anchored directories inside the current git repo (`tmp-cc/`, `nonexistent/`, `fake/`, single-char `[a-z]/`, chained identical dirs). Auto-pruned by Layer 1 when untracked, older than 7 days, and outside the negative-spec list. Confirm-needed names (`tmp/`, `scratch/`, `output/`) are surfaced here for PM confirmation.

- **Class 3 — Parent-folder orphans at `X:\` and `E:\dev\`**
  Top-level children at the parent roots whose names match the literal cruft list AND whose contents match a sonnet-default fingerprint (`vector/store/chroma.sqlite3`, lone `mcp_queries.jsonl`, etc.). Broader registry-diff against the canonical sibling-repo list is Layer 2's responsibility — Layer 1 auto-prunes only the name+fingerprint conjoint gate.

---

## Out-of-scope actions

The following are out of scope for this skill — do NOT attempt them:

- Cleanup of `~/.claude/plugins/cache/` (harness owns).
- `git clean -fd` style worktree cleanup.
- Auto-deletion of orphan markdown at parent altitude (always confirm-needed).
- Anything Layer 1 already auto-prunes (do not re-walk the tree; consume `cruft-sweep.sh --dry-run --json` output instead).

### Guard rails (from spec)

<!-- Review: Slice C reviewer F3 — four anti-scope items from handoff Anti-scope #3, #5, #6, #7 -->
These are the highest-blast-radius cases — hardcoded refusals regardless of what the Layer 1 JSONL output says:

- **Do NOT auto-prune any directory whose path contains a `.git/` boundary** (handoff Anti-scope #3). A parent-altitude `nonexistent/` that is itself a git repo retains all history inside `.git/`; pruning would be irreversible and catastrophic. Check: `[[ -d "$candidate/.git" ]]` before any prune call.
- **Do NOT expand the parent-folder scan beyond `X:\` and `E:\dev\`** (handoff Anti-scope #5). Speculative discovery of additional parent roots is not the skill's remit. The canonical roots are fixed in `~/.claude/CLAUDE.local.md § Sibling repos`; deviating from them without PM direction introduces unpredictable blast radius.
- **Do NOT conflate "untracked" with "cruft"** (handoff Anti-scope #6). A directory that is git-untracked is not automatically cruft — it may be a new repo not yet registered, a working area created this session, or intentionally unversioned. Untracked status is a necessary but not sufficient condition for any prune action.
- **Do NOT auto-prune a session directory whose UUID is referenced as `predecessor:` in any active handoff** (handoff Anti-scope #7). The pre-flight UUID block-list check in `cruft-sweep.sh` covers Layer 1; the skill must honor the same constraint for any confirm-needed item it surfaces. If a PM confirms deletion of a UUID dir, verify against the active-handoff block-list before invoking `--apply`.

---

## Steps

### Step 0 — Surface last sweep staleness

Read `~/.claude/state/cruft-sweep-log.md` to surface when the last sweep ran. Staleness is computed from the log's most recent row timestamp, not from a separate recheck file.

```bash
tail -5 ~/.claude/state/cruft-sweep-log.md 2>/dev/null || echo "(no sweep log — first run)"
```

Report the last sweep date to the PM as a one-liner: _"Last sweep: YYYY-MM-DD (N days ago)."_

### Step 1 — Run Layer 1 dry-run and parse JSONL

Invoke the script with `--dry-run --json --class all` and capture the JSONL records:

```bash
~/.claude/plugins/coordinator/bin/cruft-sweep.sh --dry-run --json --class all
```

Parse the JSONL stdout. Separate records by `disposition`:

- `auto-prune` — Layer 1 will handle these autonomously; present a summary count only.
- `confirm-needed` — surface to PM via `AskUserQuestion` (offer-shape, see Step 2).
- `skip` — informational only; do not surface unless PM asks.

Compute total reclaimable MB across `auto-prune` + `confirm-needed` records.

### Step 2 — Scout parent-altitude orphans (Class 3 registry-diff)

For candidates where `class == "orphans"` and `disposition == "skip"` (name matched but no sonnet fingerprint — Layer 2 broader scan), dispatch a read-only `Explore` agent to enumerate parent-altitude children at the canonical roots against the sibling-repo registry in `~/.claude/CLAUDE.local.md` § Sibling repos.

<!-- Review: Slice C reviewer F6 — explicit dispatch shape added; Explore agent; no acceptEdits needed (read-only) -->
Dispatch shape:

```
Agent(
  subagent_type: "Explore",
  description: "Cruft-sweep Class 3 parent-altitude registry-diff scan",
  prompt: """
    Do NOT modify files, commit, or push. Read-only.

    Enumerate top-level children of X:\\ and E:\\dev\\. For each child:
    1. Check whether its name appears in ~/.claude/CLAUDE.local.md § Sibling repos bullet list.
    2. If NOT in the registry AND NOT matching the Layer 1 auto-prune conjoint gate
       (name match + fingerprint match), include it in the result.

    Reply with a JSON list of {path, name, mtime_iso, evidence} for each candidate.
    Evidence should name why it is suspicious (e.g., "not in sibling-repo registry",
    "no fingerprint match — fingerprint gate skipped it", etc.).
  """
)
```

No `mode: acceptEdits` is needed — this agent is read-only and produces inline JSON output for the skill to parse. Do not use `general-purpose` or any write-capable subagent type.

The scout enumerates top-level children at `X:\` and `E:\dev\`, cross-references against the registry, and returns candidates for PM review.

### Step 3 — Present confirm-needed items via offer-shape AskUserQuestion

When the Layer 1 dry-run and scout produce `confirm-needed` findings, present them via batched `AskUserQuestion`. The lead-with-reclaim wording is non-negotiable — never frame as a violation or warning.

Canonical template:

> _"Reclaim N MB by pruning `<path>` (`<evidence>`, mtime `<mtime>`)? [y/N/inspect]"_

Where:
- `N MB` — the reclaim opportunity (lead with the value).
- `<path>` — the candidate path.
- `<evidence>` — one-line reason (sonnet-fingerprint match / orphan dir not in registry / name in confirm-list, etc.).
- `<mtime>` — `YYYY-MM-DD` for the freshness signal.

Batch related items from the same class into a single question where practical (e.g. all `tmp/` dirs in the same repo). Never ask about items already handled by Layer 1 auto-prune — those are informational only.

### Step 4 — Apply after confirmation

After PM confirmation on selected items, invoke `bin/cruft-sweep.sh --apply` scoped to the confirmed classes:

```bash
~/.claude/plugins/coordinator/bin/cruft-sweep.sh --apply --class <selected>
```

For Class 3 registry-diff orphans confirmed by the PM, pass the appropriate `--parent-root` overrides if the default roots differ. The script appends to `~/.claude/state/cruft-sweep-log.md` on apply — no separate log write needed from the skill.

### Step 5 — Report

Summarise: classes swept, items removed, MB reclaimed, items deferred. Note any items the PM declined to remove for the session record.

---

## Cadence note

Staleness is computed from the sweep log mtime (the most recent row timestamp in `~/.claude/state/cruft-sweep-log.md`), not from a separate recheck file. The `/workday-start` Step 1.11 advisory surfaces a one-liner when reclaimable > 1 GB OR staleness > 14 days — the PM invokes `/cruft-sweep` on that advisory; the skill does not auto-apply.

---

## Negative-spec

- Does NOT re-walk the filesystem independently — Layer 2 consumes `cruft-sweep.sh --dry-run --json` output.
- Does NOT dispatch parallel scouts — sequential by design; N is small and each candidate is judgment-bearing.
- Does NOT write outside `~/.claude/state/cruft-sweep-log.md` (which the script owns via `--apply`).
- Does NOT auto-prune on the PM's behalf — every deletion requires explicit `AskUserQuestion` confirmation or Layer 1 auto-prune eligibility.
